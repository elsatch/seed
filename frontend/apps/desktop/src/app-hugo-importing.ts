/**
 * Hugo Site Importing API
 *
 * tRPC endpoints for importing Hugo static sites into Seed.
 */

import {dialog} from 'electron'
import {nanoid} from 'nanoid'
import {join} from 'path'
import {existsSync} from 'fs'
import z from 'zod'
import {t} from './app-trpc'
import {
  scanHugoContent,
  hugoPageToImportedDocument,
  processHugoLinks,
  HugoImportResult,
  HugoPage,
} from './hugo-importer'
import {uploadLocalFile} from './app-web-importing'
import {grpcClient} from './app-grpc'
import {
  processMediaMarkdown,
  processLinkMarkdown,
} from '@shm/editor/blocknote/core/extensions/Markdown/MarkdownToBlocks'
import {htmlToBlocks} from '@shm/shared/html-to-blocks'
import {DocumentChange} from '@shm/shared/client/grpc-types'
import {unpackHmId} from '@shm/shared/utils/entity-id-url'
import {hmIdPathToEntityQueryPath} from '@shm/shared/utils/path-api'
import {HMBlockNode} from '@shm/shared/hm-types'
import {unified} from 'unified'
import remarkParse from 'remark-parse'
import remarkRehype from 'remark-rehype'
import rehypeStringify from 'rehype-stringify'

type HugoImportStatus =
  | {mode: 'scanning'}
  | {mode: 'error'; error: string}
  | {
      mode: 'ready'
      result: HugoImportResult
      contentPath: string
    }
  | {
      mode: 'importing'
      progress: {current: number; total: number; currentPage: string}
    }
  | {mode: 'complete'; imported: number}

const importingStatus: Record<string, HugoImportStatus> = {}

async function startHugoScan(
  contentPath: string,
  importId: string,
  includeDrafts: boolean,
) {
  importingStatus[importId] = {mode: 'scanning'}

  try {
    const result = await scanHugoContent(contentPath, {includeDrafts})
    importingStatus[importId] = {mode: 'ready', result, contentPath}
  } catch (error) {
    console.error('Error scanning Hugo content:', error)
    importingStatus[importId] = {
      mode: 'error',
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

/**
 * Convert markdown to HMBlockNode array using existing utilities
 */
async function markdownToBlocks(
  markdown: string,
  directoryPath: string,
): Promise<HMBlockNode[]> {
  // Convert markdown to HTML first
  const processor = unified()
    .use(remarkParse)
    .use(remarkRehype)
    .use(rehypeStringify)

  const result = await processor.process(markdown)
  const html = String(result)

  // Use existing htmlToBlocks with local file upload support
  const blocks = await htmlToBlocks(html, directoryPath, {
    uploadLocalFile,
  })

  return blocks
}

/**
 * Generate DocumentChange operations from block nodes
 */
function changesForBlockNodes(
  nodes: HMBlockNode[],
  parentId: string,
): DocumentChange[] {
  const changes: DocumentChange[] = []
  let lastPlacedBlockId = ''

  nodes.forEach((node) => {
    const block = node.block
    changes.push(
      new DocumentChange({
        op: {
          case: 'moveBlock',
          value: {
            blockId: block.id,
            parent: parentId,
            leftSibling: lastPlacedBlockId,
          },
        },
      }),
    )
    changes.push(
      new DocumentChange({
        op: {
          case: 'replaceBlock',
          // @ts-expect-error
          value: block,
        },
      }),
    )
    lastPlacedBlockId = block.id || ''

    if (node.children) {
      changes.push(...changesForBlockNodes(node.children, block.id))
    }
  })

  return changes
}

async function importHugoPage(
  page: HugoPage,
  destinationId: string,
  signAccountUid: string,
  pathMap: Map<string, {name: string; path: string}>,
) {
  const destinationHmId = unpackHmId(destinationId)
  if (!destinationHmId) {
    throw new Error('Invalid destination id')
  }

  // Process Hugo-specific links and shortcodes
  let markdown = processHugoLinks(page.content, pathMap)

  // Process media files (images, videos, files)
  markdown = await processMediaMarkdown(markdown, page.directoryPath)

  // Process internal links using the path map
  markdown = processLinkMarkdown(markdown, pathMap)

  // Convert to blocks
  const blocks = await markdownToBlocks(markdown, page.directoryPath)

  // Build document path
  const docPath = [...(destinationHmId.path || []), ...page.seedPath]

  // Build changes
  const changes: DocumentChange[] = []

  function addChange(op: DocumentChange['op']) {
    changes.push(new DocumentChange({op}))
  }

  // Set document name
  addChange({
    case: 'setMetadata',
    value: {key: 'name', value: page.title},
  })

  // Set displayPublishTime if date exists
  if (page.frontmatter.date) {
    try {
      const date = new Date(page.frontmatter.date)
      addChange({
        case: 'setMetadata',
        value: {key: 'displayPublishTime', value: date.toISOString()},
      })
    } catch {
      // Invalid date, skip
    }
  }

  // Set summary if exists
  if (page.frontmatter.description || page.frontmatter.summary) {
    addChange({
      case: 'setMetadata',
      value: {
        key: 'summary',
        value: (page.frontmatter.description ||
          page.frontmatter.summary) as string,
      },
    })
  }

  // Add block changes
  changes.push(...changesForBlockNodes(blocks, ''))

  // Create document
  const resp = await grpcClient.documents.createDocumentChange({
    signingKeyName: signAccountUid,
    account: destinationHmId.uid,
    path: hmIdPathToEntityQueryPath(docPath),
    changes,
  })

  return resp
}

export const hugoImportingApi = t.router({
  /**
   * Open dialog to select Hugo site folder
   */
  selectHugoFolder: t.procedure.mutation(async () => {
    const result = await dialog.showOpenDialog({
      title: 'Select Hugo Site Folder',
      properties: ['openDirectory'],
      message: 'Select the root folder of your Hugo site (containing content/)',
    })

    if (result.canceled || !result.filePaths[0]) {
      return null
    }

    const selectedPath = result.filePaths[0]

    // Check if this is a Hugo site (has content folder)
    const contentPath = join(selectedPath, 'content')
    if (!existsSync(contentPath)) {
      // Maybe they selected the content folder directly
      if (existsSync(selectedPath)) {
        return {path: selectedPath, type: 'content' as const}
      }
      throw new Error(
        'Selected folder does not appear to be a Hugo site. No content/ folder found.',
      )
    }

    return {path: contentPath, type: 'hugo-root' as const}
  }),

  /**
   * Start scanning a Hugo content folder
   */
  scanHugoSite: t.procedure
    .input(
      z.object({
        contentPath: z.string(),
        includeDrafts: z.boolean().default(false),
      }),
    )
    .mutation(async ({input}) => {
      const importId = nanoid(10)
      startHugoScan(input.contentPath, importId, input.includeDrafts)
      return {importId}
    }),

  /**
   * Get scan/import status
   */
  getHugoImportStatus: t.procedure
    .input(z.string())
    .query(async ({input: importId}) => {
      return importingStatus[importId] || null
    }),

  /**
   * Confirm and start importing pages
   */
  confirmHugoImport: t.procedure
    .input(
      z.object({
        importId: z.string(),
        destinationId: z.string(),
        signAccountUid: z.string(),
        selectedPages: z.array(z.string()).optional(), // relative paths to import, all if not provided
      }),
    )
    .mutation(async ({input}) => {
      const {importId, destinationId, signAccountUid, selectedPages} = input
      const status = importingStatus[importId]

      if (!status || status.mode !== 'ready') {
        throw new Error('Import not ready')
      }

      const {result, contentPath} = status
      let pagesToImport = result.pages

      // Filter by selected pages if provided
      if (selectedPages && selectedPages.length > 0) {
        const selectedSet = new Set(selectedPages)
        pagesToImport = pagesToImport.filter((p) =>
          selectedSet.has(p.relativePath),
        )
      }

      const total = pagesToImport.length
      let imported = 0
      const errors: Array<{page: string; error: string}> = []

      // Import pages in order (sections first due to sorting)
      for (const page of pagesToImport) {
        importingStatus[importId] = {
          mode: 'importing',
          progress: {
            current: imported + 1,
            total,
            currentPage: page.title,
          },
        }

        try {
          await importHugoPage(
            page,
            destinationId,
            signAccountUid,
            result.pathMap,
          )
          imported++
        } catch (error) {
          console.error(`Error importing ${page.relativePath}:`, error)
          errors.push({
            page: page.relativePath,
            error: error instanceof Error ? error.message : String(error),
          })
        }
      }

      importingStatus[importId] = {mode: 'complete', imported}

      return {imported, errors, total}
    }),

  /**
   * Get list of pages from a ready import for user selection
   */
  getHugoPages: t.procedure.input(z.string()).query(async ({input: importId}) => {
    const status = importingStatus[importId]
    if (!status || status.mode !== 'ready') {
      return null
    }

    return status.result.pages.map((page) => ({
      relativePath: page.relativePath,
      title: page.title,
      isSection: page.isSection,
      isDraft: page.frontmatter.draft || false,
      date: page.frontmatter.date,
      seedPath: page.seedPath,
    }))
  }),

  /**
   * Clear import state
   */
  clearHugoImport: t.procedure.input(z.string()).mutation(({input: importId}) => {
    delete importingStatus[importId]
    return true
  }),
})
