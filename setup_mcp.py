#!/usr/bin/env python3
"""
One-shot setup for the lead-engine MCP + skill. Cross-platform (Windows/macOS/Linux).

Does, from a fresh clone:
  1. create mcp/.venv and install requirements
  2. create mcp/.env  (from --email/--password, env vars, or a copy of .env.example)
  3. install the lead-engine-ops skill into ~/.claude/skills/
  4. register the MCP user-scoped with the `claude` CLI

Run:
  python setup_mcp.py --email you@thehirehub.ai --password "<your leads.thehirehub.ai password>"
  # or run bare and edit mcp/.env yourself afterwards:
  python setup_mcp.py

Use YOUR OWN leads.thehirehub.ai login — comments and QA remarks are attributed
to whoever the MCP is authenticated as.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MCP = ROOT / "mcp"
VENV = MCP / ".venv"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.check_call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--base-url", default="https://leads.thehirehub.ai/api")
    ap.add_argument("--skip-register", action="store_true")
    a = ap.parse_args()

    # 1. venv + deps
    if not venv_python().exists():
        print("Creating venv...")
        venv.create(VENV, with_pip=True)
    run([str(venv_python()), "-m", "pip", "install", "-q", "-r", str(MCP / "requirements.txt")])

    # 2. .env — never overwrite an existing one
    env = MCP / ".env"
    if env.exists():
        print(".env already exists — leaving it untouched.")
    else:
        email = a.email or os.environ.get("LEAD_ENGINE_EMAIL")
        pw = a.password or os.environ.get("LEAD_ENGINE_PASSWORD")
        if email and pw:
            env.write_text(
                f"LEAD_ENGINE_BASE_URL={a.base_url}\n"
                f"LEAD_ENGINE_EMAIL={email}\n"
                f"LEAD_ENGINE_PASSWORD={pw}\n",
                encoding="utf-8",
            )
            print("Wrote mcp/.env")
        else:
            shutil.copy(MCP / ".env.example", env)
            print("!! Copied .env.example -> mcp/.env. EDIT IT: set your leads.thehirehub.ai email + password.")

    # 3. install skill
    skills_dir = Path.home() / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    dst = skills_dir / "lead-engine-ops"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(ROOT / "skills" / "lead-engine-ops", dst)
    print(f"Installed skill -> {dst}")

    # 4. register MCP user-scoped
    if not a.skip_register:
        claude = shutil.which("claude")
        reg = ["mcp", "add", "lead-engine", "--scope", "user", "--",
               str(venv_python()), str(MCP / "server.py")]
        if claude:
            try:
                run([claude, *reg])
            except subprocess.CalledProcessError:
                print("MCP register failed (maybe already registered) — re-run manually if needed:")
                print(f'  claude {" ".join(reg)}')
        else:
            print("`claude` CLI not on PATH. Register manually:")
            print(f'  claude {" ".join(reg)}')

    print("\nDone. Restart Claude, then run:  claude mcp list   (expect: lead-engine Connected)")


if __name__ == "__main__":
    sys.exit(main())
