# thh-lead-engine-claude

Claude toolkit for the **thh-lead-engine** Ops Deck (Bugs & Tasks kanban).
One clone gives QA and developers both pieces:

- **`mcp/`** — a stdio MCP server wrapping `/api/tech-tasks`. Lets Claude list,
  read, create, move, and QA-reject tickets. Output is token-light.
- **`skills/lead-engine-ops/`** — a Claude skill that teaches the house issue
  format and the read/write token discipline.

## Quick start

```bash
git clone <this repo>
cd thh-lead-engine-claude/mcp
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
#   source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
cp .env.example .env        # fill LEAD_ENGINE_PASSWORD (ask an admin)
```

Register the MCP:

```bash
claude mcp add lead-engine -- "<abs path>/.venv/Scripts/python.exe" "<abs path>/mcp/server.py"
```

Install the skill — copy it where Claude looks for skills:

```bash
cp -r skills/lead-engine-ops ~/.claude/skills/        # user-wide
#   or into a project's .claude/skills/
```

## What it's for

- **QA**: describe a bug once; Claude files it structured (Problem → Steps →
  Expected → Actual → severity/env) in one call. No form copy-paste.
- **Developers**: `list_my_tickets` → pick → `get_ticket` → work. The card is
  already structured, so Claude spends almost nothing understanding it.

See `mcp/README.md` for the full tool list and `skills/lead-engine-ops/SKILL.md`
for the rules.

## Security

- Creds live only in `mcp/.env` (gitignored). Never commit them.
- The MCP service account is `mcp@thehirehub.ai`. Rotate its password if a
  clone or transcript is ever shared outside the team.
