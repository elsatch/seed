/**
 * Hugo Site Importer
 *
 * Imports Hugo static site content into Seed hypermedia.
 * Handles Hugo's content folder structure, frontmatter, and markdown.
 */

import {readFile, readdir, stat} from 'fs/promises'
import {join, relative, dirname, basename, extname} from 'path'
import matter from 'gray-matter'

export interface HugoFrontmatter {
  title?: string
  date?: string
  draft?: boolean
  description?: string
  summary?: string
  tags?: string[]
  categories?: string[]
  weight?: number
  slug?: string
  aliases?: string[]
  cover?: {
    image?: string
    alt?: string
    caption?: string
  }
  [key: string]: unknown
}

export interface HugoPage {
  /** Relative path from content dir (e.g., "posts/my-post.md") */
  relativePath: string
  /** Full file path */
  filePath: string
  /** Directory containing this file */
  directoryPath: string
  /** Parsed frontmatter */
  frontmatter: HugoFrontmatter
  /** Markdown content (without frontmatter) */
  content: string
  /** Document path in Seed (e.g., ["posts", "my-post"]) */
  seedPath: string[]
  /** Whether this is an _index.md (section page) */
  isSection: boolean
  /** Document title */
  title: string
}

export interface HugoImportResult {
  pages: HugoPage[]
  /** Mapping of Hugo paths to Seed paths for link resolution */
  pathMap: Map<string, {name: string; path: string}>
  /** Statistics */
  stats: {
    total: number
    drafts: number
    sections: number
  }
}

/**
 * Scans a Hugo content directory and returns all importable pages
 */
export async function scanHugoContent(
  contentPath: string,
  options: {
    includeDrafts?: boolean
  } = {},
): Promise<HugoImportResult> {
  const {includeDrafts = false} = options
  const pages: HugoPage[] = []
  const pathMap = new Map<string, {name: string; path: string}>()
  const stats = {total: 0, drafts: 0, sections: 0}

  async function walkDir(dir: string) {
    const entries = await readdir(dir, {withFileTypes: true})

    for (const entry of entries) {
      const fullPath = join(dir, entry.name)

      if (entry.isDirectory()) {
        await walkDir(fullPath)
      } else if (
        entry.isFile() &&
        (entry.name.endsWith('.md') || entry.name.endsWith('.markdown'))
      ) {
        const page = await parseHugoPage(contentPath, fullPath)
        if (page) {
          stats.total++

          if (page.frontmatter.draft) {
            stats.drafts++
            if (!includeDrafts) continue
          }

          if (page.isSection) {
            stats.sections++
          }

          pages.push(page)

          // Build path mapping for link resolution
          // Hugo links may use various formats
          const hugoPath = '/' + page.relativePath.replace(/\.md$/, '/')
          const hugoPathNoSlash = '/' + page.relativePath.replace(/\.md$/, '')
          const seedPathStr = '/' + page.seedPath.join('/')

          pathMap.set(hugoPath, {name: page.title, path: seedPathStr})
          pathMap.set(hugoPathNoSlash, {name: page.title, path: seedPathStr})
          pathMap.set(page.relativePath, {name: page.title, path: seedPathStr})
        }
      }
    }
  }

  await walkDir(contentPath)

  // Sort pages: sections first, then by path depth
  pages.sort((a, b) => {
    if (a.isSection && !b.isSection) return -1
    if (!a.isSection && b.isSection) return 1
    return a.seedPath.length - b.seedPath.length
  })

  return {pages, pathMap, stats}
}

/**
 * Parses a single Hugo markdown file
 */
async function parseHugoPage(
  contentRoot: string,
  filePath: string,
): Promise<HugoPage | null> {
  try {
    const fileContent = await readFile(filePath, 'utf-8')
    const {data: frontmatter, content} = matter(fileContent)

    const relativePath = relative(contentRoot, filePath)
    const directoryPath = dirname(filePath)
    const fileName = basename(filePath, extname(filePath))
    const isSection = fileName === '_index'

    // Build Seed path from Hugo structure
    const seedPath = buildSeedPath(relativePath, frontmatter as HugoFrontmatter)

    // Determine title with fallback chain
    const title = resolveTitle(
      frontmatter as HugoFrontmatter,
      content,
      fileName,
    )

    return {
      relativePath,
      filePath,
      directoryPath,
      frontmatter: frontmatter as HugoFrontmatter,
      content,
      seedPath,
      isSection,
      title,
    }
  } catch (error) {
    console.error(`Error parsing Hugo page ${filePath}:`, error)
    return null
  }
}

/**
 * Builds Seed document path from Hugo file path
 */
function buildSeedPath(
  relativePath: string,
  frontmatter: HugoFrontmatter,
): string[] {
  // Remove .md extension
  let pathStr = relativePath.replace(/\.(md|markdown)$/, '')

  // Handle _index.md - represents the parent directory
  if (pathStr.endsWith('/_index') || pathStr === '_index') {
    pathStr = pathStr.replace(/\/?_index$/, '')
  }

  // Use slug from frontmatter if available
  if (frontmatter.slug) {
    const dir = dirname(pathStr)
    pathStr = dir === '.' ? frontmatter.slug : join(dir, frontmatter.slug)
  }

  // Split into path segments, filter empty
  return pathStr.split('/').filter((s) => s.length > 0)
}

/**
 * Resolves document title with fallback chain:
 * 1. frontmatter.title
 * 2. First H1 in content
 * 3. File name (titlecased)
 */
function resolveTitle(
  frontmatter: HugoFrontmatter,
  content: string,
  fileName: string,
): string {
  if (frontmatter.title) {
    return frontmatter.title
  }

  // Check for first H1
  const h1Match = content.match(/^#\s+(.+)$/m)
  if (h1Match) {
    return h1Match[1].trim()
  }

  // Fallback to filename
  if (fileName === '_index') {
    return 'Index'
  }

  // Title-case the filename
  return fileName
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/**
 * Converts Hugo page to ImportedDocument format for existing import flow
 */
export function hugoPageToImportedDocument(page: HugoPage): {
  markdownContent: string
  title: string
  directoryPath: string
  path: string[]
  metadata: {
    name: string
    displayPublishTime?: string
    summary?: string
  }
} {
  let markdownContent = page.content

  // If title came from H1, remove it from content to avoid duplication
  if (!page.frontmatter.title) {
    const lines = markdownContent.split('\n')
    const firstNonEmptyIndex = lines.findIndex((line) => line.trim() !== '')
    if (
      firstNonEmptyIndex !== -1 &&
      lines[firstNonEmptyIndex]?.startsWith('# ')
    ) {
      lines.splice(firstNonEmptyIndex, 1)
      markdownContent = lines.join('\n')
    }
  }

  // Build metadata
  const metadata: {name: string; displayPublishTime?: string; summary?: string} =
    {
      name: page.title,
    }

  // Convert date to displayPublishTime
  if (page.frontmatter.date) {
    try {
      const date = new Date(page.frontmatter.date)
      metadata.displayPublishTime = date.toISOString()
    } catch {
      // Invalid date, skip
    }
  }

  // Use description or summary
  if (page.frontmatter.description || page.frontmatter.summary) {
    metadata.summary =
      page.frontmatter.description || page.frontmatter.summary || undefined
  }

  return {
    markdownContent,
    title: page.title,
    directoryPath: page.directoryPath,
    path: page.seedPath,
    metadata,
  }
}

/**
 * Processes Hugo-style internal links in markdown
 * Converts Hugo ref/relref shortcodes and relative links
 */
export function processHugoLinks(
  markdown: string,
  pathMap: Map<string, {name: string; path: string}>,
): string {
  let processed = markdown

  // Handle Hugo ref shortcode: {{< ref "path" >}}
  processed = processed.replace(
    /\{\{<\s*ref\s+"([^"]+)"\s*>\}\}/g,
    (match, refPath) => {
      const resolved = pathMap.get(refPath) || pathMap.get('/' + refPath)
      return resolved ? resolved.path : refPath
    },
  )

  // Handle Hugo relref shortcode: {{< relref "path" >}}
  processed = processed.replace(
    /\{\{<\s*relref\s+"([^"]+)"\s*>\}\}/g,
    (match, refPath) => {
      const resolved = pathMap.get(refPath) || pathMap.get('/' + refPath)
      return resolved ? resolved.path : refPath
    },
  )

  // Handle markdown links with .md extension
  processed = processed.replace(
    /\[([^\]]+)\]\(([^)]+\.md)\)/g,
    (match, text, href) => {
      const normalized = href.replace(/\.md$/, '')
      const resolved = pathMap.get(href) || pathMap.get(normalized)
      if (resolved) {
        return `[${text}](${resolved.path})`
      }
      return match
    },
  )

  return processed
}

/**
 * Extracts and resolves cover image from Hugo frontmatter
 */
export function resolveCoverImage(
  page: HugoPage,
): {imagePath: string; alt?: string; caption?: string} | null {
  const cover = page.frontmatter.cover
  if (!cover?.image) return null

  let imagePath = cover.image

  // If relative path, resolve from page directory
  if (!imagePath.startsWith('/') && !imagePath.startsWith('http')) {
    imagePath = join(page.directoryPath, imagePath)
  }

  return {
    imagePath,
    alt: cover.alt,
    caption: cover.caption,
  }
}
