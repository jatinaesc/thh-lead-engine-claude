# thh-lead-engine MCP — Ops Deck bridge

Lets Claude read and write the lead-engine **Bugs & Tasks** board (`/api/tech-tasks`)
so QA files structured issues in one call and developers pull assigned issues cheaply.

## Setup

```bash
cd mcp
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
cp .env.example .env      # then fill LEAD_ENGINE_PASSWORD (gitignored)
```

## Register in Claude Code

```bash
claude mcp add lead-engine -- "D:\Athena\thh-lead-engine\mcp\.venv\Scripts\python.exe" "D:\Athena\thh-lead-engine\mcp\server.py"
```

Or add to your MCP config manually:

```json
{
  "mcpServers": {
    "lead-engine": {
      "command": "D:\\Athena\\thh-lead-engine\\mcp\\.venv\\Scripts\\python.exe",
      "args": ["D:\\Athena\\thh-lead-engine\\mcp\\server.py"]
    }
  }
}
```

## Tools

**Read** (cheap): `list_my_tickets`, `list_tickets`, `get_ticket`, `list_users`, `get_attachment`
**Write**: `create_bug`, `create_task`, `move_status`, `assign`, `add_qa_remark`, `comment`, `upload_screenshot`

`get_attachment(url)` downloads a ticket screenshot local so Claude can Read/view it.
`upload_screenshot(path)` uploads an image and returns a URL for `attachment_urls`.

Output is compact text with int-enums decoded to labels — no raw JSON — so reads
stay token-light. Two-step read: `list_*` returns a thin list, `get_ticket`
pulls one full card only when you commit to it.

## Auth

Service account `mcp@thehirehub.ai` (admin). The server logs in once, keeps the
`lead_engine_session` cookie, re-logs-in on 401. Creds live in `.env` only.
**Rotate the password if this repo/transcript is ever shared.**

## Style note

`create_bug` assembles the description in the house format used by QA (Gunjit):
problem → Steps to Reproduce → Expected → Actual → Environment. Pass the slots
as structured params; the tool formats them consistently.
