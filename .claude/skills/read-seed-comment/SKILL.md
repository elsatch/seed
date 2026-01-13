---
name: read-seed-comment
description: Read and display the full content of any Seed comment using its comment IRI (hm://<account>/<tsid>). These comments IRIs are not the same as document IRIs. Fetches comment blocks, embedded links, and timestamps.
---

# Read Seed Comment

Fetches and displays the complete content of a Seed comment using the lightclient gRPC client.

## Prerequisites

The lightclient must be set up with dependencies installed:
```bash
cd ~/Documents/lightclient
pip install -r requirements.txt
```

The Seed daemon must be running and accessible on one of these ports:
- **58002** - Development/test port (try first)
- **56002** - Production port (fallback)

## Usage

When the user provides a Seed comment IRI or asks to read a comment, use this skill to fetch and display its contents.

### Command Format

```bash
cd /home/julio/Documents/lightclient
python3 client.py --server localhost:58002 comment get '<IRI>'
```

Where `<IRI>` is a fully qualified Seed comment identifier in the format:
- `hm://<account>/<tsid>`

### Examples

Read a comment:
```bash
python3 client.py --server localhost:58002 comment get 'hm://z6MktKrLcr23GFXMYtd1qS5a3UHwkHdvmNkptduX2CPjWzYt/z6EdP6AsbyT9zs'
```

## Output Format

The command returns structured comment information including:
- **block**: Main comment block with:
  - `id`: Block identifier
  - `type`: Block type (Embed, Paragraph, etc.)
  - `text`: Block text content (if applicable)
  - `revision`: Block revision
  - `link`: Embedded document/block reference (for Embed types)
  - `attributes`: Block attributes (childrenType, etc.)
- **children**: Nested blocks containing the actual comment content
- **Created at**: Comment creation timestamp
- **Updated at**: Last update timestamp

## Instructions

When a user asks to read a Seed comment:

1. **Extract the IRI**:
   - From user input directly (if they provide `hm://<account>/<tsid>`)
   - From hybrid search results (comments in search have IRIs not confuse with document IRIs)
   - Ask the user if the IRI is unclear. the tsid is an alphanumeric strig of size 14.

2. **Execute the command with port fallback**:

   First, try port **58002** (development):
   ```bash
   cd /home/julio/Documents/lightclient
   python3 client.py --server localhost:58002 comment get '<IRI>'
   ```

   If you see an error like:
   ```
   get_comment error: <_InactiveRpcError of RPC that terminated with:
       status = StatusCode.UNAVAILABLE
       details = "failed to connect to all addresses..."
   ```

   Then try port **56002** (production):
   ```bash
   cd /home/julio/Documents/lightclient
   python3 client.py --server localhost:56002 comment get '<IRI>'
   ```

   If **both ports fail**, inform the user:
   > "The Seed daemon is not running on ports 58002 or 56002. Please start the daemon and try again."

3. **Parse and present the output**:
   - If the comment has an **Embed** block, show what document/block it's commenting on (from `link` field)
   - Display the **children blocks** which contain the actual comment text
   - Show **timestamps** (created/updated)
   - Present nested block structure clearly

4. **Handle other errors gracefully**:
   - If comment not found, inform the user
   - If IRI is malformed, explain the correct format

## Example Interaction

**User**: "Read the comment at hm://z6MktKrLcr23GFXMYtd1qS5a3UHwkHdvmNkptduX2CPjWzYt/z6EdP6AsbyT9zs"

**Assistant**: Let me fetch that comment for you.

*Executes command and parses output*

**Comment on:** hm://z6MkuMzdbZ3D7D9xgCi2gV2xosPNzzoy467qZugfH4JdUuhM/third-doc/test?l#BK-LZH_P

**Content:**
I like it!

---
*Created: 2025-12-22 10:24:10 UTC*
*Updated: 2025-12-22 10:24:10 UTC*

## Comment Structure

Comments in Seed typically have:
- A top-level **Embed** block that links to what's being commented on
- **Children** blocks containing the actual comment text (Paragraphs, etc.)
- Nested structure for threaded replies

## Tips

- When combining with `/hybrid-search`, you can read comments found in search results
- Use the full IRI including the `hm://` prefix
- Comment IRIs are shorter than document IRIs (account + comment ID)
- The `link` field in Embed blocks shows what document/block is being commented on
