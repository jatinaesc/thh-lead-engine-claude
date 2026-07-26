"""
thh-lead-engine MCP — Ops Deck (Bugs & Tasks) bridge for Claude.

Wraps the `/api/tech-tasks` API so:
  - QA files a well-structured bug/task in ONE tool call (no form copy-paste).
  - Developers pull their assigned issues cheaply (thin list -> full card only
    when they commit to one).

Token rule: tool output is compact text with int-enums already decoded to
short labels. No raw JSON envelopes, no null-field noise. QA pays once writing
a structured card; every later read is near-free.

Auth: logs in once with a service account, keeps the `lead_engine_session`
cookie, re-logs-in transparently on 401. Creds come from .env (gitignored).

Run:  python server.py   (stdio MCP; register in Claude Code config)
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Keep stdio clean: httpx/httpcore INFO lines would otherwise spam stderr.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

load_dotenv(Path(__file__).with_name(".env"))

BASE_URL = os.environ.get("LEAD_ENGINE_BASE_URL", "https://leads.thehirehub.ai/api").rstrip("/")
EMAIL = os.environ.get("LEAD_ENGINE_EMAIL", "")
PASSWORD = os.environ.get("LEAD_ENGINE_PASSWORD", "")

# --- enum label <-> int maps (source of truth: services/common/enums.py) ---
KIND = {"task": 0, "bug": 1, "feature_request": 2, "idea": 3, "incident": 4,
        "tech_debt": 5, "spike": 6, "improvement": 7}
STATUS = {"todo": 0, "in_progress": 1, "dev_pushed": 2, "dev_qa_passed": 3,
          "prod_pushed": 4, "prod_qa_passed": 5, "done": 6}
PRIORITY = {"low": 0, "med": 1, "high": 2, "urgent": 3}
SEVERITY = {"trivial": 0, "minor": 1, "major": 2, "critical": 3}
EFFORT = {"XS": 1, "S": 2, "M": 3, "L": 5, "XL": 8}


def _pick(m: dict[str, int], label: Optional[str], field: str) -> Optional[int]:
    """Map a human label to its int, raising a clear error listing valid values."""
    if label is None:
        return None
    key = str(label).strip().lower()
    # SEVERITY/PRIORITY keys are lowercase; EFFORT keys are upper — normalise both ways.
    for k, v in m.items():
        if k.lower() == key:
            return v
    raise ValueError(f"invalid {field} '{label}' — use one of: {', '.join(m)}")


# --- HTTP client with transparent re-login ---
class Client:
    def __init__(self) -> None:
        self._c = httpx.Client(base_url=BASE_URL, timeout=30.0, follow_redirects=True)
        self._logged_in = False

    def _login(self) -> None:
        r = self._c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            raise RuntimeError(f"login failed ({r.status_code}): {r.text[:200]}")
        self._logged_in = True  # cookie now stored on self._c

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        if not self._logged_in:
            self._login()
        r = self._c.request(method, path, **kw)
        if r.status_code == 401:  # token expired / revoked -> one retry
            self._login()
            r = self._c.request(method, path, **kw)
        return r

    def json(self, method: str, path: str, **kw) -> dict:
        r = self.request(method, path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()


_client: Optional[Client] = None


def api() -> Client:
    global _client
    if _client is None:
        _client = Client()
    return _client


# --- compact renderers (the token lever) ---
def _fmt_card_line(c: dict) -> str:
    """One tight line per card for list output."""
    bits = [f"#{c['id']}", c["kind_label"]]
    if c.get("severity_label"):
        bits.append(c["severity_label"])
    if c.get("priority_label"):
        bits.append(c["priority_label"])
    tier = "P1" if c.get("is_p1") else "P2" if c.get("is_p2") else "P3" if c.get("is_p3") else ""
    if tier:
        bits.append(tier)
    if c.get("is_blocked"):
        bits.append("BLOCKED")
    tag = "/".join(bits)
    cc = c.get("comment_count", 0)
    extra = f" ({cc}c)" if cc else ""
    return f"{tag} [{c['status_label']}] {c['title']}{extra}"


def _fmt_detail(d: dict) -> str:
    """Full card, compact. Skips empty fields to save tokens."""
    out = [_fmt_card_line(d)]
    meta = []
    if d.get("assignee_user_ids"):
        meta.append(f"assignees={d['assignee_user_ids']}")
    if d.get("created_by_user_id"):
        meta.append(f"creator={d['created_by_user_id']}")
    if d.get("due_at"):
        meta.append(f"due={d['due_at']}")
    if d.get("effort_label"):
        meta.append(f"effort={d['effort_label']}")
    if d.get("tags"):
        meta.append(f"tags={d['tags']}")
    if meta:
        out.append("  " + " ".join(meta))
    out.append("")
    out.append(d.get("description") or "(no description)")
    if d.get("error_text"):
        out.append("\n-- error_text --\n" + d["error_text"])
    if d.get("attachment_urls"):
        out.append("\n-- attachments --\n" + "\n".join(d["attachment_urls"]))
    comments = d.get("comments") or []
    if comments:
        out.append(f"\n-- comments ({len(comments)}) --")
        for cm in comments:
            flag = " [QA-REMARK]" if cm.get("is_qa_remark") else ""
            out.append(f"  u{cm.get('author_user_id')}{flag}: {cm.get('body')}")
    return "\n".join(out)


def _compose_bug_body(problem: str, steps: Optional[list[str]],
                      expected: Optional[str], actual: Optional[str],
                      environment: Optional[str]) -> str:
    """Assemble Gunjit's house format from structured slots."""
    parts = [problem.strip()]
    if steps:
        parts.append("\nSteps to Reproduce\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
    if expected:
        parts.append("\nExpected Result\n" + expected.strip())
    if actual:
        parts.append("\nActual Result\n" + actual.strip())
    if environment:
        parts.append(f"\nEnvironment: {environment.strip()}")
    return "\n".join(parts)


mcp = FastMCP("thh-lead-engine")


# ============================ READ TOOLS ============================
@mcp.tool()
def list_my_tickets(statuses: Optional[list[str]] = None,
                    kinds: Optional[list[str]] = None,
                    include_archived: bool = False) -> str:
    """List tickets assigned to the MCP service account's teammates? No —
    lists tickets assigned to the *current logged-in user* (the mcp account).
    For a specific developer use `list_tickets(assignee_ids=[id])`.

    Returns a thin one-line-per-card list. Cheap — call `get_ticket(id)` for
    full detail only on the one you pick.

    statuses/kinds: optional label filters, e.g. statuses=["todo","in_progress"].
    """
    return list_tickets(assignee="me", statuses=statuses, kinds=kinds,
                        include_archived=include_archived)


@mcp.tool()
def list_tickets(assignee: Optional[str] = None,
                 assignee_ids: Optional[list[int]] = None,
                 creator_ids: Optional[list[int]] = None,
                 statuses: Optional[list[str]] = None,
                 kinds: Optional[list[str]] = None,
                 q: Optional[str] = None,
                 include_archived: bool = False,
                 limit: int = 100) -> str:
    """Flexible board fetch — thin one-line-per-card output.

    assignee: shorthand "me" or "unassigned".
    assignee_ids: filter by developer user id(s).
    creator_ids: filter by who opened the ticket (e.g. [15] for Gunjit).
    statuses/kinds: label filters (see STATUS/KIND).
    q: free-text search over title+description.
    """
    params: list[tuple[str, str]] = []
    if assignee:
        params.append(("assignee", assignee))
    for i in (assignee_ids or []):
        params.append(("assignee", str(i)))
    for i in (creator_ids or []):
        params.append(("creator", str(i)))
    for s in (statuses or []):
        params.append(("statuses", str(_pick(STATUS, s, "status"))))
    for k in (kinds or []):
        params.append(("kinds", str(_pick(KIND, k, "kind"))))
    if q:
        params.append(("q", q))
    if include_archived:
        params.append(("include_archived", "true"))
    params.append(("limit", str(max(1, min(limit, 500)))))

    data = api().json("GET", "/tech-tasks", params=params)["data"]
    items = data.get("items", [])
    if not items:
        return "no tickets match."
    head = f"{len(items)} ticket(s):"
    return head + "\n" + "\n".join(_fmt_card_line(c) for c in items)


@mcp.tool()
def get_ticket(task_id: int) -> str:
    """Full detail for one ticket: description, error_text, attachments,
    comments (incl. QA remarks) — compact. Call this only for the card a dev
    actually picks."""
    d = api().json("GET", f"/tech-tasks/{task_id}")["data"]
    return _fmt_detail(d)


@mcp.tool()
def list_users() -> str:
    """Roster of taggable users: `id  name  (role)`. Use to resolve names to
    ids for assignees / mentions / creator filters."""
    items = api().json("GET", "/tech-tasks/mentionable-users")["data"]["items"]
    lines = []
    for u in items:
        name = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x)
        lines.append(f"{u['id']}  {name}  ({u.get('role_label')})")
    return "\n".join(lines)


# ============================ WRITE TOOLS ============================
@mcp.tool()
def create_bug(title: str, problem: str,
               severity: str,
               steps: Optional[list[str]] = None,
               expected: Optional[str] = None,
               actual: Optional[str] = None,
               environment: Optional[str] = None,
               error_text: Optional[str] = None,
               assignee_ids: Optional[list[int]] = None,
               attachment_urls: Optional[list[str]] = None,
               priority: Optional[str] = None) -> str:
    """File a bug in the house format, one call.

    title: concise; prefix with (Env/Area) if useful, e.g. "(Prod) JD gen slow".
    problem: 1-2 sentence summary of what's wrong.
    severity: trivial|minor|major|critical.
    steps: ordered repro steps.  expected/actual: the two outcomes.
    environment: dev|staging|prod.  error_text: stack/technical detail.
    assignee_ids: developer ids (see list_users). attachment_urls: from upload_screenshot.
    """
    body = _compose_bug_body(problem, steps, expected, actual, environment)
    payload = {
        "kind": KIND["bug"],
        "title": title,
        "description": body,
        "severity": _pick(SEVERITY, severity, "severity"),
        "priority": _pick(PRIORITY, priority, "priority"),
        "error_text": error_text,
        "assignee_user_ids": assignee_ids,
        "attachment_urls": attachment_urls or [],
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    d = api().json("POST", "/tech-tasks", json=payload)["data"]
    return f"created bug #{d['id']}: {d['title']}"


@mcp.tool()
def create_task(title: str, description: str,
                priority: Optional[str] = "med",
                steps: Optional[list[str]] = None,
                effort: Optional[str] = None,
                assignee_ids: Optional[list[int]] = None,
                attachment_urls: Optional[list[str]] = None,
                is_p1: bool = False) -> str:
    """Create a task (non-bug work item).

    priority: low|med|high|urgent (default med).  effort: XS|S|M|L|XL.
    steps: optional 'Steps to Reproduce'-style pointer. is_p1: team-priority flag.
    """
    body = description.strip()
    if steps:
        body += "\n\nSteps\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    payload = {
        "kind": KIND["task"],
        "title": title,
        "description": body,
        "priority": _pick(PRIORITY, priority, "priority"),
        "effort": _pick(EFFORT, effort, "effort"),
        "assignee_user_ids": assignee_ids,
        "attachment_urls": attachment_urls or [],
        "is_p1": is_p1,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    d = api().json("POST", "/tech-tasks", json=payload)["data"]
    return f"created task #{d['id']}: {d['title']}"


@mcp.tool()
def move_status(task_id: int, status: str) -> str:
    """Move a card to a new lifecycle stage.
    status: todo|in_progress|dev_pushed|dev_qa_passed|prod_pushed|prod_qa_passed|done.
    """
    payload = {"status": _pick(STATUS, status, "status")}
    d = api().json("PATCH", f"/tech-tasks/{task_id}", json=payload)["data"]
    return f"#{task_id} -> {d['status_label']}"


@mcp.tool()
def assign(task_id: int, assignee_ids: list[int]) -> str:
    """Replace a ticket's assignees (send [] to clear). See list_users for ids."""
    d = api().json("PATCH", f"/tech-tasks/{task_id}",
                   json={"assignee_user_ids": assignee_ids})["data"]
    return f"#{task_id} assignees -> {d.get('assignee_user_ids')}"


@mcp.tool()
def add_qa_remark(task_id: int, body: str) -> str:
    """QA reject: post a QA remark. Auto-@mentions assignee+creator and kicks
    the card back from a *_qa_passed stage to the matching *_pushed stage.
    This is the QA 'send it back' button."""
    payload = {"body": body, "is_qa_remark": True}
    api().json("POST", f"/tech-tasks/{task_id}/comments", json=payload)
    return f"QA remark posted on #{task_id} (assignee+creator mentioned, lifecycle kicked back)."


@mcp.tool()
def comment(task_id: int, body: str, mention_ids: Optional[list[int]] = None) -> str:
    """Add a plain comment, optionally @mentioning user ids."""
    payload = {"body": body, "mentioned_user_ids": mention_ids or []}
    c = api().json("POST", f"/tech-tasks/{task_id}/comments", json=payload)["data"]
    return f"commented on #{task_id} (comment {c.get('id')})."


@mcp.tool()
def get_attachment(url: str) -> str:
    """Download a ticket attachment (image) to a local file and return its path.

    Dev read-flow: `get_ticket` lists attachment URLs; call this on one to pull
    it local, then open the returned path with the Read tool to actually SEE the
    screenshot. Public CDN URL — no auth needed. Cached by URL, so re-calling is
    cheap and won't re-download.
    """
    r = httpx.get(url, timeout=30.0, follow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"download failed {r.status_code}: {url}")
    ext = os.path.splitext(url.split("?")[0])[1] or ".png"
    name = hashlib.sha1(url.encode()).hexdigest()[:16] + ext
    cache = Path(tempfile.gettempdir()) / "lead_engine_attachments"
    cache.mkdir(parents=True, exist_ok=True)
    p = cache / name
    p.write_bytes(r.content)
    return str(p)


@mcp.tool()
def upload_screenshot(file_path: str) -> str:
    """Upload an image (<=5MB) and return its URL for attachment_urls."""
    p = Path(file_path)
    if not p.is_file():
        raise ValueError(f"no such file: {file_path}")
    with p.open("rb") as f:
        r = api().request("POST", "/tech-tasks/upload-screenshot",
                          files={"file": (p.name, f)})
    if r.status_code >= 400:
        raise RuntimeError(f"upload failed {r.status_code}: {r.text[:200]}")
    return r.json()["data"]["url"]


if __name__ == "__main__":
    mcp.run()
