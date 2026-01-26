---
name: read-seed-doc
description: Read and display the full content of any Seed document using its IRI (hm://...). Fetches document metadata, authors, content blocks, and version information.
---

# Read Seed Document

Fetches and displays the complete content of a Seed document using the lightclient gRPC client.

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

When the user provides a Seed document IRI or asks to read a document, use this skill to fetch and display its contents.

### Command Format

```bash
cd /home/julio/Documents/lightclient
python3 client.py --server localhost:58002 document get '<IRI>'
```

Where `<IRI>` is a fully qualified Seed document identifier in the format:
- `hm://<account>/path` (latest version)
- `hm://<account>/path?v=<version>` (specific version)

### Examples

Read a document at latest version:
```bash
python3 client.py --server localhost:58002 document get 'hm://z6MkuMzdbZ3D7D9xgCi2gV2xosPNzzoy467qZugfH4JdUuhM/third-doc/test'
```

Read a specific version:
```bash
python3 client.py --server localhost:58002 document get 'hm://z6MkuMzdbZ3D7D9xgCi2gV2xosPNzzoy467qZugfH4JdUuhM/third-doc/test?v=bafy2bzaced...'
```

## Output Format

The command returns structured document information including:
- **account**: Document owner's account ID
- **path**: Document path within the account
- **metadata**: Document metadata (name, summary, etc.)
- **authors**: List of document authors
- **content**: Document content blocks with:
  - `id`: Block identifier
  - `type`: Block type (Paragraph, Heading, etc.)
  - `text`: Block text content
  - `revision`: Block revision hash
- **create_time**: Document creation timestamp
- **update_time**: Last update timestamp
- **genesis**: Genesis block hash
- **version**: Current version hash
- **generation_info**: Version generation details

## Instructions

When a user asks to read a Seed document:

1. **Extract the IRI**:
   - From user input directly (if they provide `hm://...`)
   - From hybrid search results (use the IRI from search output)
   - If the provided iri is not found, try to remove the version part from the iri and ask just hm://<account>/<path>
   - Ask the user if the IRI is unclear

2. **Execute the command with port fallback**:

   First, try port **58002** (development):
   ```bash
   cd /home/julio/Documents/lightclient
   python3 client.py --server localhost:58002 document get '<IRI>'
   ```

   If you see an error like:
   ```
   get_document error: <_InactiveRpcError of RPC that terminated with:
       status = StatusCode.UNAVAILABLE
       details = "failed to connect to all addresses..."
   ```

   Then try port **56002** (production):
   ```bash
   cd /home/julio/Documents/lightclient
   python3 client.py --server localhost:56002 document get '<IRI>'
   ```

   If **both ports fail**, inform the user:
   > "The Seed daemon is not running on ports 58002 or 56002. Please start the daemon and try again."

3. **Parse and present the output**:
   - Show the document **title** (from metadata.name)
   - Show the document **path**
   - Display the **content blocks** in order, showing:
     - Block text
     - Block type (if not Paragraph)
   - Optionally show metadata like authors, timestamps, version

4. **Handle other errors gracefully**:
   - If document not found, inform the user
   - If IRI is malformed, explain the correct format

## Example Interaction

**User**: "Read the document at hm://z6MkuMzdbZ3D7D9xgCi2gV2xosPNzzoy467qZugfH4JdUuhM/third-doc/test"

**Assistant**: Let me fetch that document for you.

*Executes command and parses output*

**Document: Reusing Path**
Path: `/third-doc/test`
Author: `z6MkuMzdbZ3D7D9xgCi2gV2xosPNzzoy467qZugfH4JdUuhM`

**Content:**
Hello

---
*Version: bafy2bzaceb6ab6jxaahrmtyvgsjeoypfj3ntn6fcga6zt5kjvnwowkwgkfkta*
*Updated: [timestamp]*

## Tips

- When combining with `/hybrid-search`, you can read documents found in search results
- Use the full IRI including the `hm://` prefix
- For debugging, the raw output shows the complete protobuf structure
- The document content is in the `content.block` repeated field
