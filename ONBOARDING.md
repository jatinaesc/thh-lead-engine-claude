# Onboarding — lead-engine MCP + skill

Gets you (dev or QA) filing and working Ops Deck tickets through Claude.

## Before you start
- **Repo access**: you can clone this repo (ask the admin if `git clone` 403s).
- **Your own leads.thehirehub.ai login** — the email + password you sign in with.
  The MCP acts *as you*: comments and QA remarks show your name. Do **not** use a
  shared/bot account.
- **Python 3.10+** and **Claude Code** installed.

## Fastest path — one command

```bash
git clone https://github.com/jatinaesc/thh-lead-engine-claude.git
cd thh-lead-engine-claude
python setup_mcp.py --email you@thehirehub.ai --password "<your leads password>"
```

That creates the venv, installs deps, writes your `mcp/.env`, installs the
`lead-engine-ops` skill, and registers the MCP user-wide. **Restart Claude**, then:

```bash
claude mcp list        # expect: lead-engine  ✔ Connected
```

Prefer not to pass your password on the command line? Run `python setup_mcp.py`
bare, then edit `mcp/.env` and set `LEAD_ENGINE_EMAIL` / `LEAD_ENGINE_PASSWORD`.

## Or: let your Claude do it

Open Claude Code inside the cloned repo and paste:

```
Run python setup_mcp.py in this repo to set up the lead-engine MCP.
Ask me for my leads.thehirehub.ai email and password for the .env — don't guess them.
Then show me `claude mcp list` and confirm lead-engine is Connected.
```

## Using it

Ask Claude naturally — the `lead-engine-ops` skill guides the rest:

- **QA**: "File a bug: on prod, paused jobs open the pre-screening page instead of
  job details. Steps: … Expected: … Actual: … severity major." → Claude calls
  `create_bug` in the house format, one shot. Attach a screenshot? Point Claude at
  the image file; it uploads and attaches it.
- **Dev**: "What lead-engine tickets are assigned to me?" → thin list →
  "open #367" → Claude pulls the full card and starts. Move it with
  "mark #367 in progress" / "push #367 to dev".
- **QA reject**: "Reject #364 — the credit cap still overshoots on retry." →
  `add_qa_remark`, which @mentions the dev + sends the card back.

## Security
- Your password lives only in `mcp/.env` (gitignored). Never commit it.
- If you leave the team, an admin disables your leads account — that revokes MCP
  access automatically.

## Troubleshooting
- `lead-engine` not Connected → check `mcp/.env` creds; run
  `mcp/.venv/Scripts/python.exe mcp/server.py` (Windows) and read the error.
- Tools missing in Claude → you didn't restart Claude after registering.
- `claude` not found → install Claude Code / add it to PATH, then re-run
  `python setup_mcp.py --skip-register` is *not* needed; just re-run the script.
