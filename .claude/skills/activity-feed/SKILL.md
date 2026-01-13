---
name: activity-feed
description: Display Seed network activity feed showing recent events (changes, comments, mentions) in chronological order. Social media-style feed for tracking platform activity.
---

# Activity Feed

Shows recent activity on the Seed network including document changes, comments, mentions, and other events ordered by time.

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

When the user wants to see recent activity, new events, or what's happening on their Seed network, use this skill to fetch and display the activity feed.

### Command Format

```bash
cd /home/julio/Documents/lightclient
python3 client.py --server localhost:58002 activity feed [OPTIONS]
```

**IMPORTANT**: Do NOT use the `--formatted` flag. The raw output preserves full data without trimming.

### Options

- `--page-size`, `-s`: Number of events to fetch (default: 30)
- `--page-token`, `-t`: Pagination token for next page
- `--accounts`, `-a`: Filter events from specific accounts (space-separated)
- `--event-types`, `-e`: Filter by event type (KeyDelegation | Change | Comment | DagPB)
- `--resources`, `-r`: Filter events from specific resource (supports wildcards)

### Examples

Show recent activity:
```bash
python3 client.py --server localhost:58002 activity feed
```

Show last 50 events:
```bash
python3 client.py --server localhost:58002 activity feed -s 50
```

Filter by specific account:
```bash
python3 client.py --server localhost:58002 activity feed -a z6MkuMzdbZ3D7D9xgCi2gV2xosPNzzoy467qZugfH4JdUuhM
```

Filter by event type:
```bash
python3 client.py --server localhost:58002 activity feed -e Comment Change
```

Get next page:
```bash
python3 client.py --server localhost:58002 activity feed -t '<pagination_token>'
```

## Output Format

Each event is displayed with complete information (no trimming):

```
Source: hm://z6MkuMzdbZ3D7D9xgCi2gV2xosPNzzoy467qZugfH4JdUuhM/docs/weekly-update
Target:
Type: Change
Author: z6MkuMzdbZ3D7D9xgCi2gV2xosPNzzoy467qZugfH4JdUuhM
Observed Time: 2026-01-11 23:15:42
Event Time: 2026-01-11 23:15:40
--------------------------------------------------------------------------------
Source: hm://z6MkvBnxK8rZ3D9xgCi2gV2xosPNzzoy467qZugfH4JdXyzA/projects/roadmap
Target: hm://z6MkuMzdbZ3D7D9xgCi2gV2xosPNzzoy467qZugfH4JdUuhM/docs/weekly-update
Type: Comment
Author: z6MkvBnxK8rZ3D9xgCi2gV2xosPNzzoy467qZugfH4JdXyzA
Observed Time: 2026-01-11 23:10:15
Event Time: 2026-01-11 23:10:14
--------------------------------------------------------------------------------
```

After all events:
```
Next Page Token: [<pagination_token_or_empty>]
Elapsed time: 0.123
```

**Field Descriptions:**
- **Source**: The resource where the event originated (always includes full hm:// IRI)
- **Target**: The target resource for mentions/references (empty for standalone events)
- **Type**: Event type (Comment, Change, KeyDelegation, DagPB)
- **Author**: Full account ID that created the event
- **Observed Time**: When the event was observed by your node
- **Event Time**: When the event actually occurred

## Instructions

When a user wants to see activity:

1. **Determine filters** (if user specified):
   - Specific accounts to watch
   - Event types of interest
   - Resource filters
   - Number of events

2. **Execute command with port fallback**:

   First, try port **58002** (development):
   ```bash
   cd /home/julio/Documents/lightclient
   python3 client.py --server localhost:58002 activity feed
   ```

   If you see connection errors:
   ```
   get_feed error: <_InactiveRpcError of RPC that terminated with:
       status = StatusCode.UNAVAILABLE
       details = "failed to connect to all addresses..."
   ```

   Then try port **56002** (production):
   ```bash
   cd /home/julio/Documents/lightclient
   python3 client.py --server localhost:56002 activity feed
   ```

   If **both ports fail**, inform the user:
   > "The Seed daemon is not running on ports 58002 or 56002. Please start the daemon and try again."

3. **Present the output**:
   - Show the complete activity feed with all fields
   - Parse and highlight key information (event types, authors, resources)
   - If there's a next page token, offer to fetch more events
   - Summarize the activity (e.g., "5 new comments, 3 document changes")
   - Extract IRIs from Source and Target fields for further exploration

4. **Combine with content reading skills**:
   - **IMPORTANT**: Activity feed shows WHAT happened, not the content itself
   - Use `/read-seed-doc` to read the actual content of documents mentioned in Source/Target fields
   - Use `/read-seed-comment` to read the content of comments
   - Example workflow:
     1. Run activity feed to see recent events
     2. Identify interesting IRIs in Source/Target fields
     3. Use `/read-seed-doc <IRI>` to read the full content
     4. Use `/read-seed-comment <IRI>` for comment content
   - This two-step approach gives users both the activity stream and detailed content

5. **Handle pagination**:
   - If user wants older events, use the next page token from output
   - Can fetch multiple pages to show more history

6. **Handle errors gracefully**:
   - If no events found, inform the user
   - If filters are too restrictive, suggest broadening them

## Example Interaction

**User**: "Show me recent activity on the network"

**Assistant**: Let me fetch the recent activity feed.

*Executes: `python3 client.py --server localhost:58002 activity feed`*

Here's the recent activity on your Seed network:

**Latest Events:**

1. **Document Change**
   - Resource: `hm://z6MkuMz.../docs/weekly-update`
   - Author: `z6MkuMz...`
   - Time: 2026-01-11 23:15:40

2. **New Comment**
   - On: `hm://z6MkuMz.../docs/weekly-update`
   - From: `z6MkvBn...`
   - Time: 2026-01-11 23:10:14

Found 30 events. Would you like me to read the content of any of these documents or comments?

---

**User**: "Yes, read the weekly update document"

**Assistant**: Let me fetch the full content of that document.

*Uses `/read-seed-doc hm://z6MkuMz.../docs/weekly-update` to get the actual content*

---

**User**: "Show me the latest comment activity and read the most recent comment"

**Assistant**: Let me get the comment activity feed first.

*Executes: `python3 client.py --server localhost:58002 activity feed -e Comment -s 10`*

Found 10 recent comments. Let me read the most recent one.

*Uses `/read-seed-comment <IRI_from_source_field>` to get the comment content*

## Tips

- Raw output preserves complete IRIs and account IDs without trimming
- **Always combine with `/read-seed-doc` or `/read-seed-comment` to get actual content**
- Activity feed is for discovering WHAT happened, content reading is for seeing the details
- Default page size (30) is good for quick overview
- Increase page size to 50-100 for deeper history
- Event times are in local timezone
- Use pagination tokens to browse older activity
- Filter by account to track specific users or projects
- Filter by event type to focus on specific activities (Comments, Changes, etc.)
- The feed is ordered by event time (most recent first)
- Parse Source/Target fields to extract document IRIs for further reading
- For comprehensive activity tracking: feed → identify IRIs → read content with other skills
