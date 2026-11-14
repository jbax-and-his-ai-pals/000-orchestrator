#!/usr/bin/env python
"""Portfolio orchestrator core: state, guardrails, and the CLI every agent uses.

The dashboard imports this module; agents shell out to it. Nothing else writes
orchestrator.db, so the main-branch guard and the taste-profile log live here.

    python _orchestrator/scripts/orch.py --help
"""
from __future__ import annotations

import steering
import uuid
import argparse
import contextlib
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

ORCH = Path(os.environ.get("ORCH_HOME") or Path(__file__).resolve().parents[1])  # env override = tests only
ROOT = Path(os.environ.get("ORCH_ROOT") or ORCH.parent)
STATE = ORCH / "state"
DB_PATH = STATE / "orchestrator.db"
JSON_PATH = STATE / "PORTFOLIO_STATE.json"
TASTE = STATE / "TASTE_PROFILE.md"
CONFIG = ORCH / "config.json"
DOSSIERS = ORCH / "dossiers"
DESIGNS = ORCH / "designs"
WORKTREES = ORCH / "worktrees"
ORG = "jbax-and-his-ai-pals"
SELF_REPO = "000-orchestrator"  # this tool's own GitHub repo: never cloned or treated as a game project

PRIORITIES = ("high", "medium", "low", "skip")
COMPLEXITIES = ("high", "standard")
CATEGORIES = ("fun_gameplay", "visual_craft", "optimization", "tech_audacity", "new_game")
STAGES = ("spark", "hld_draft", "hld_review", "lld_draft", "lld_review",
          "building", "playtest", "done", "rejected")
ASSIGNEES = ("gemma", "codex", "claude", "ide_handoff")
PROTECTED_BRANCHES = {"main", "master", "trunk", "develop"}

# What "Approve / Advance" does from each stage.
ADVANCE = {
    "spark": "hld_draft",
    "hld_draft": "hld_review",   # manual skip; normally the architect attaches an HLD
    "hld_review": "lld_draft",
    "lld_draft": "lld_review",   # manual skip; normally the planner attaches an LLD
    "lld_review": "building",
    "building": "playtest",
    "playtest": "done",
}
# What "Request Revision" sends a card back to.
REVISE = {
    "spark": "spark",
    "hld_draft": "hld_draft",
    "hld_review": "hld_draft",
    "lld_draft": "lld_draft",
    "lld_review": "lld_draft",
    "building": "building",
    "playtest": "building",
}
# Gemma capability contract (see _orchestrator/GEMMA_CAPABILITIES.md). Enforced here, not just in prompts.
GEMMA = {
    "max_files": 2,            # a gemma subtask may list at most this many files
    "max_changed_lines": 150,  # a gemma commit may add+delete at most this many lines
    "max_attempts": 2,         # blocked this many times -> auto-escalate to a frontier model
    "escalate_to": "codex",
    "dossier_headings": ["## Snapshot", "## Player experience", "## Core loop", "## Bottlenecks", "## Visual cohesion",
                         "## Recent activity", "## Smoke test", "## Needs frontier"],
}
SCOUT_ACTORS = {"scout-gemma", "gemma", "scout"}
# Scheduled OpenClaw agents. They must skip anything claimed by an interactive session.
AGENT_ACTORS = SCOUT_ACTORS | {"architect-claude", "planner-codex", "reviewer-gemini", "architect", "planner"}
CLAIM_HOURS = 24

# Entering these stages means "the producer has something to look at".
NOTIFY_STAGES = {"hld_review", "lld_review", "playtest"}

# Curated first-pass facts. The scout refines them; the dashboard edits priority/complexity.
SEED = {
    SELF_REPO: ("Python orchestrator (SQLite + FastAPI dashboard + OpenClaw agents)", "high"),
    "001-tactical-shadowcaster": ("Python / pygame", "standard"),
    "002-wasteball": ("Godot 4.6 / GDScript", "standard"),
    "003-big-city": ("Godot 4.6 / GDScript", "standard"),
    "004-vr-soccer": ("Godot 4.6 / GDScript / OpenXR", "standard"),
    "005-twitch-storyteller": ("Python asyncio + Godot client", "standard"),
    "006-nes-game": ("NES / C + 6502 asm (cc65)", "high"),
    "007-twitch-chatbot-coordinator": ("Kotlin / Ktor / Twitch4J", "standard"),
    "008-mud": ("Python MUD engine + web client", "standard"),
    "009-vr-baseball": ("Godot 4.7 / GDScript / OpenXR", "standard"),
    "010-vr-fever-dream": ("Godot 4.7 / GDScript / OpenXR", "standard"),
    "011-ants": ("Godot 4.7 / GDScript", "standard"),
    "012-rimworld-mod": ("RimWorld 1.6 mod / C#", "standard"),
    "013-street-hugger": ("Godot 4.7 / GDScript", "standard"),
    "014-atari-mega-man": ("Atari 2600 CDFJ+ / C (ARM) + 6507 asm", "high"),
    "015-mmc6-nes": ("Mesen2 fork / C++ mapper (NES hardware)", "high"),
    "016-wow-social-bots": ("AzerothCore 3.3.5a module / C++", "high"),
    "017-rydia": ("SNES FF4 ROM hack / 65816 asm + Lua tooling", "high"),
    "018-dfu-content-engine": ("Daggerfall Unity mod research (no code yet)", "standard"),
    "019-z2-barba": ("NES Zelda II ROM hack / 6502 asm + Python tooling", "high"),
}

DEFAULT_CONFIG = {
    "dashboard": {"host": "127.0.0.1", "port": 8420, "poll_seconds": 4},
    "metrics": ["stack", "player_experience", "playability_score", "visual_maturity", "complexity", "last_scanned_at"],
    "webhooks": {
        "enabled": False,
        "urls": [],
        "events": sorted(NOTIFY_STAGES),
        "_comment": "POSTs JSON {event, initiative, project, title, stage, url} when a card enters one of `events`.",
    },
    "models": {
        "scout": "ollama/gemma4:12b",
        "architect": "anthropic/claude-sonnet-5-5",
        "architect_high": "anthropic/claude-opus-5-5",
        "planner": "openai/gpt-6.1-sol",
    },
}

TASTE_TEMPLATE = """# Taste Profile

Every agent reads this before pitching, designing, planning, or reviewing. It is the producer's voice.
The rejection log at the bottom is appended automatically by the dashboard; treat each entry as a hard signal.

## Creative philosophy

- **Fun first.** Game feel, kinesthetics, juice, and moment-to-moment play beat polygon count or photorealism.
  Pitch the thing a player would grin at in the first 30 seconds.
- **Broad appeal.** Prefer mechanics that read instantly and reward mastery over ones that need a manual.

## Visual quality bar (strict)

- **No generic AI-generated sprite sheets. No programmer art.** If a pitch needs art it cannot honestly produce, it must
  say how the look will be achieved without them.
- Favor **cohesive stylized or retro aesthetics**, **palette discipline** (a named, limited palette per project),
  **shaders and post-processing**, **procedural / vector geometry**, and **crisp typography**.
- A small set of shapes with a strong palette and good motion beats a large set of mismatched assets.

## Technical appetite

- **High enthusiasm for system optimizations**: frame time, memory, load time, cartridge/bank budgets, allocation churn.
- **High enthusiasm for technical audacity**: e.g. cramming rich adventure and dialogue systems into strict NES hardware
  limits, coprocessor tricks, clever banking. Constraints are a feature, not an excuse.

## Working rules for agents

- Read `DOSSIER.md` files, not raw repos, when pitching or designing.
- Never touch `main`/`master`. All code goes on `feat/<slug>` branches in `_orchestrator/worktrees/`.
- Keep pitches short: a hook, why it is fun, how it looks, what it costs.

## Rejection log

_Appended automatically. Format: timestamp | project | initiative | stage rejected at | producer note._

"""


# ---------------------------------------------------------------- utilities

def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:limit].rstrip("-")) or "initiative"


def load_config() -> dict:
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        cfg = {}
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def run(cmd: list[str], cwd: Path | None = None, check: bool = False, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, check=check)


def git(repo: Path, *args: str, check: bool = False) -> str:
    p = run(["git", "-C", str(repo), *args], check=check)
    return p.stdout.strip()


class OrchError(Exception):
    pass


# Test/verify commands are POSIX shell (grep, &&, etc.). On Windows use Git for Windows bash by full path:
# cmd.exe (subprocess shell=True) lacks grep, and shutil.which("bash") can find WSL's System32 bash first.
GIT_BASH = next((p for p in ("C:/Program Files/Git/bin/bash.exe", "C:/Program Files (x86)/Git/bin/bash.exe")
                 if os.path.exists(p)), None)


def sh(cmd: str, cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    # _orchestrator/bin holds tool shims (e.g. `godot`) so verify commands can use plain names.
    cmd = f'export PATH="{(ORCH / "bin").as_posix().replace("C:/", "/c/", 1)}:$PATH"; {cmd}'
    argv = [GIT_BASH, "-lc", cmd] if (os.name == "nt" and GIT_BASH) else ["/bin/sh", "-c", cmd]
    env = {**os.environ, "CHERE_INVOKING": "1"}  # keep bash -l from cd'ing to $HOME
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=env)


# ---------------------------------------------------------------- database

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    repo_name TEXT PRIMARY KEY,
    url TEXT,
    local_path TEXT NOT NULL,
    stack TEXT,
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('high','medium','low','skip')),
    complexity TEXT NOT NULL DEFAULT 'standard' CHECK (complexity IN ('high','standard')),
    playability_score INTEGER,
    visual_maturity INTEGER,
    optimization_notes TEXT,
    last_scanned_at TEXT,
    is_git INTEGER NOT NULL DEFAULT 1,
    default_branch TEXT,
    bottleneck_summary TEXT
);
CREATE TABLE IF NOT EXISTS initiatives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('fun_gameplay','visual_craft','optimization','tech_audacity','new_game')),
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    pitch_summary TEXT,
    stage TEXT NOT NULL DEFAULT 'spark' CHECK (stage IN ('spark','hld_draft','hld_review','lld_draft','lld_review','building','playtest','done','rejected')),
    complexity TEXT NOT NULL DEFAULT 'standard' CHECK (complexity IN ('high','standard')),
    hld_path TEXT,
    lld_path TEXT,
    execution_plan_json TEXT,
    assigned_model TEXT,
    branch_name TEXT,
    worktree_path TEXT,
    revision_note TEXT,
    rejection_reason TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    project_name TEXT,
    initiative_id INTEGER,
    kind TEXT NOT NULL,
    message TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metrics (ts TEXT NOT NULL, source TEXT NOT NULL, key TEXT NOT NULL, value REAL, meta TEXT);
CREATE INDEX IF NOT EXISTS idx_metrics_source_key_ts ON metrics(source,key,ts);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);
CREATE INDEX IF NOT EXISTS idx_init_stage ON initiatives(stage);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""

_lock = threading.RLock()


@contextlib.contextmanager
def db(write: bool = False):
    STATE.mkdir(parents=True, exist_ok=True)
    with _lock:
        con = sqlite3.connect(DB_PATH, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=30000")
        try:
            if write:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if write:
                con.commit()
        except Exception:
            if write:
                con.rollback()
            raise
        finally:
            con.close()
    if write:
        export_json()


def init_db() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    import lane_status
    con.executescript(lane_status.SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(initiatives)")}
    for col in ("claimed_by", "claimed_at", "claim_expires_at", "claim_note"):
        if col not in have:
            con.execute(f"ALTER TABLE initiatives ADD COLUMN {col} TEXT")
    have = {r[1] for r in con.execute("PRAGMA table_info(projects)")}
    for col in ("focus_by", "focus_until", "focus_note", "player_experience"):
        if col not in have:
            con.execute(f"ALTER TABLE projects ADD COLUMN {col} TEXT")
    if "priority" not in {r[1] for r in con.execute("PRAGMA table_info(initiatives)")}:
        con.execute("ALTER TABLE initiatives ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'")
    if "details_json" not in {r[1] for r in con.execute("PRAGMA table_info(events)")}:
        con.execute("ALTER TABLE events ADD COLUMN details_json TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS idx_events_init_id ON events(initiative_id,id)")
    con.commit()
    con.close()


def log_event(con, actor: str, kind: str, message: str = "", project: str | None = None,
              initiative_id: int | None = None, details: dict | None = None) -> None:
    con.execute("INSERT INTO events(ts, actor, project_name, initiative_id, kind, message,details_json) VALUES (?,?,?,?,?,?,?)",
                (now(), actor, project, initiative_id, kind, message, json.dumps(details) if details else None))


def rows(con, sql: str, *params) -> list[dict]:
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def export_json() -> dict:
    with _lock:
        con = sqlite3.connect(DB_PATH, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            state = {
                "generated_at": now(),
                "projects": rows(con, "SELECT * FROM projects ORDER BY repo_name"),
                "initiatives": rows(con, "SELECT * FROM initiatives ORDER BY id"),
                "recent_events": rows(con, "SELECT * FROM events ORDER BY id DESC LIMIT 100"),
            }
        finally:
            con.close()
    for i in state["initiatives"]:
        if i.get("execution_plan_json"):
            with contextlib.suppress(json.JSONDecodeError):
                i["execution_plan_json"] = json.loads(i["execution_plan_json"])
    tmp = JSON_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, JSON_PATH)
    return state


# ---------------------------------------------------------------- projects

def project_dirs() -> list[Path]:
    """Game repos in the container root, plus the orchestrator itself (registered as 000-orchestrator)."""
    games = [p for p in ROOT.iterdir() if p.is_dir() and re.match(r"^\d{3}-", p.name) and p.name != SELF_REPO]
    return sorted(games + ([ORCH] if (ORCH / ".git").exists() else []), key=lambda p: project_name(p))


def project_name(p: Path) -> str:
    return SELF_REPO if p.resolve() == ORCH.resolve() else p.name


def default_branch(repo: Path) -> str | None:
    ref = git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if ref.startswith("origin/"):
        return ref.split("/", 1)[1]
    for b in ("main", "master"):
        if git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{b}"):
            return b
    return None


def seed_projects(actor: str = "orch") -> int:
    added = 0
    with db(write=True) as con:
        for p in project_dirs():
            is_git = (p / ".git").exists()
            url = git(p, "remote", "get-url", "origin") if is_git else ""
            url = re.sub(r"\.git$", "", url) or None
            name = project_name(p)
            stack, cx = SEED.get(name, (None, "standard"))
            exists = con.execute("SELECT 1 FROM projects WHERE repo_name=?", (name,)).fetchone()
            if exists:
                con.execute("UPDATE projects SET url=?, local_path=?, is_git=?, default_branch=? WHERE repo_name=?",
                            (url, str(p), int(is_git), default_branch(p) if is_git else None, name))
                continue
            con.execute(
                "INSERT INTO projects(repo_name,url,local_path,stack,priority,complexity,is_git,default_branch) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (name, url, str(p), stack, "medium", cx, int(is_git), default_branch(p) if is_git else None))
            log_event(con, actor, "project_added", f"Registered {name}", name)
            added += 1
    return added


def get_project(con, name: str) -> dict:
    r = con.execute("SELECT * FROM projects WHERE repo_name=?", (name,)).fetchone()
    if not r:
        raise OrchError(f"unknown project: {name}")
    return dict(r)


PROJECT_FIELDS = {"stack", "priority", "complexity", "playability_score", "visual_maturity",
                  "optimization_notes", "bottleneck_summary", "player_experience"}


def update_project(name: str, fields: dict, actor: str = "dashboard", expected: str | None = None) -> dict:
    bad = set(fields) - PROJECT_FIELDS
    if bad:
        raise OrchError(f"cannot set {sorted(bad)}; allowed: {sorted(PROJECT_FIELDS)}")
    if "priority" in fields and fields["priority"] not in PRIORITIES:
        raise OrchError(f"priority must be one of {PRIORITIES}")
    if "complexity" in fields and fields["complexity"] not in COMPLEXITIES:
        raise OrchError(f"complexity must be one of {COMPLEXITIES}")
    for k in ("playability_score", "visual_maturity"):
        if k in fields and fields[k] in (None, ""):
            fields[k] = None
        elif k in fields:
            v = int(fields[k])
            if not 0 <= v <= 10:
                raise OrchError(f"{k} must be 0-10")
            fields[k] = v
    with db(write=True) as con:
        steering.expect(project_version(get_project(con, name)), expected)
        sets = ", ".join(f"{k}=?" for k in fields)
        con.execute(f"UPDATE projects SET {sets} WHERE repo_name=?", (*fields.values(), name))
        log_event(con, actor, "project_updated", ", ".join(f"{k}={v}" for k, v in fields.items()), name)
        return get_project(con, name)


def sync_repos(dry_run: bool = False) -> list[str]:
    """Clone org repos that are missing locally. Never touches existing checkouts."""
    p = run(["gh", "repo", "list", ORG, "--limit", "200", "--json", "name,url"], check=True)
    cloned = []
    for repo in json.loads(p.stdout):
        dest = ROOT / repo["name"]
        if repo["name"] == SELF_REPO or dest.exists():
            continue
        cloned.append(repo["name"])
        if not dry_run:
            run(["git", "clone", repo["url"], str(dest)], check=True, timeout=1800)
    if not dry_run:
        seed_projects("sync")
    return cloned


# ---------------------------------------------------------------- scanning (deterministic; the scout narrates it)

SKIP_DIRS = {".git", ".godot", ".venv", "venv", "node_modules", "build", "out", ".local", ".gradle", ".kotlin",
             ".idea", "__pycache__", ".runtime", ".tools", "roms", "savestates", "mesen2", "emu-stock", "bin", "obj"}
CODE_EXT = {".py", ".gd", ".cs", ".c", ".h", ".cpp", ".hpp", ".s", ".asm", ".inc", ".kt", ".kts", ".lua",
            ".js", ".ts", ".gdshader", ".shader", ".glsl", ".rs"}


def list_files(repo: Path, is_git: bool) -> list[str]:
    if is_git:
        out = run(["git", "-C", str(repo), "ls-files"]).stdout
        return [l for l in out.splitlines() if l]
    found = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel = Path(dirpath).relative_to(repo)
        found.extend(str(rel / f).replace("\\", "/") for f in filenames)
        if len(found) > 20000:
            break
    return found


def detect_tests(repo: Path, files: list[str]) -> list[str]:
    cmds = []
    names = set(files)
    if "scripts/orch.py" in names:  # the orchestrator itself
        cmds.append("python -m py_compile scripts/orch.py dashboard/app.py scripts/sync_playbooks.py")
    if "run_tests.py" in names:
        cmds.append("python run_tests.py")
    if any(f.startswith("tests/") and f.endswith(".py") for f in files) or "pytest.ini" in names or "pyproject.toml" in names:
        cmds.append("python -m pytest -q")
    if "project.godot" in names:
        cmds.append("godot --headless --quit  # import/parse smoke test (needs godot on PATH)")
    if "Makefile" in names:
        cmds.append("make")
    if "build.gradle" in names or "build.gradle.kts" in names:
        cmds.append("./gradlew test")
    if any(f.endswith(".sln") or f.endswith(".csproj") for f in files):
        cmds.append("dotnet test")
    for f in files:
        if re.search(r"(^|/)(Test|Validate)[^/]*\.(cmd|ps1)$", f):
            cmds.append(f)
    return cmds[:6]


def scan_project(name: str) -> dict:
    with db() as con:
        proj = get_project(con, name)
    repo = Path(proj["local_path"])
    is_git = bool(proj["is_git"])
    files = list_files(repo, is_git)
    ext_counts: dict[str, int] = {}
    loc = 0
    big = []
    for f in files:
        ext = Path(f).suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        fp = repo / f
        if ext in CODE_EXT:
            with contextlib.suppress(OSError):
                size = fp.stat().st_size
                if size < 2_000_000:
                    with open(fp, "rb") as fh:
                        n = fh.read().count(b"\n")
                    loc += n
                    big.append((n, f))
    big.sort(reverse=True)
    facts = {
        "repo": name,
        "local_path": str(repo),
        "scanned_at": now(),
        "is_git": is_git,
        "tracked_files": len(files),
        "top_extensions": dict(sorted(ext_counts.items(), key=lambda kv: -kv[1])[:10]),
        "code_lines": loc,
        "largest_code_files": [{"file": f, "lines": n} for n, f in big[:8]],
        "docs": sorted(f for f in files if f.count("/") == 0 and f.lower().endswith(".md"))[:20],
        "test_commands": detect_tests(repo, files),
    }
    if is_git:
        facts.update({
            "current_branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
            "default_branch": proj["default_branch"],
            "dirty_files": [l for l in git(repo, "status", "--porcelain").splitlines() if l][:20],
            "recent_commits": git(repo, "log", "-12", "--date=short", "--pretty=format:%ad %h %s").splitlines(),
            "commits_last_14d": len(git(repo, "log", "--since=14.days", "--pretty=format:%h").splitlines()),
            "feat_branches": [b.strip("* ").strip() for b in git(repo, "branch", "--list", "feat/*").splitlines()],
        })
    d = DOSSIERS / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SCAN.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    with db(write=True) as con:
        con.execute("UPDATE projects SET last_scanned_at=? WHERE repo_name=?", (facts["scanned_at"], name))
        log_event(con, "scan", "scanned", f"{len(files)} files, {loc} code lines", name)
    return facts


SMOKE_SAFE = ("python -m py_compile scripts/orch.py dashboard/app.py scripts/sync_playbooks.py", "python run_tests.py", "python -m pytest -q", "./gradlew test", "dotnet test", "make")


def smoke(name: str, actor: str = "scout") -> dict:
    """Run the first safe detected test command in a throwaway detached worktree of the default branch.

    Never runs in the user's checkout, never on a branch, never launches GUI/.cmd/.ps1 scripts.
    """
    with db() as con:
        proj = get_project(con, name)
    check_focus(name, actor)
    check_spotlight(name, actor)
    if not proj["is_git"]:
        return {"repo": name, "ran": False, "reason": "not a git repo"}
    repo = Path(proj["local_path"])
    scan_file = DOSSIERS / name / "SCAN.json"
    facts = json.loads(scan_file.read_text(encoding="utf-8")) if scan_file.exists() else scan_project(name)
    cmds = [c for c in facts.get("test_commands", []) if c in SMOKE_SAFE]
    if any(c.startswith("godot") for c in facts.get("test_commands", [])) and (
            shutil.which("godot") or (ORCH / "bin" / "godot").exists()):
        cmds.append("godot --headless --path . --quit")
    result = {"repo": name, "at": now(), "ran": False}
    if not cmds:
        result["reason"] = "no safe headless test command detected"
    else:
        wt = WORKTREES / name / "_smoke"
        base = proj["default_branch"] or "HEAD"
        if wt.exists():
            run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)])
            shutil.rmtree(wt, ignore_errors=True)
            run(["git", "-C", str(repo), "worktree", "prune"])
        wt.parent.mkdir(parents=True, exist_ok=True)
        p = run(["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), base])
        if p.returncode != 0:
            result["reason"] = f"worktree failed: {p.stderr.strip()[:300]}"
        else:
            cmd = cmds[0]
            t0 = dt.datetime.now()
            try:
                q = sh(cmd, wt, 300)
                result.update(ran=True, command=cmd, exit_code=q.returncode, passed=q.returncode == 0,
                              output_tail=(q.stdout + q.stderr)[-3000:])
            except subprocess.TimeoutExpired:
                result.update(ran=True, command=cmd, passed=False, exit_code=None, output_tail="timed out after 300s")
            result["seconds"] = round((dt.datetime.now() - t0).total_seconds(), 1)
            result["likely_env_failure"] = bool(re.search(
                r"ModuleNotFoundError|No module named|is not recognized|command not found|could not find|"
                r"SDK.*not found|JAVA_HOME", result["output_tail"], re.I)) and not result["passed"]
            result["note"] = ("Runs in a clean checkout without the project's local venv/toolchain; "
                              "import/tool errors may be environment, not code.")
    (DOSSIERS / name).mkdir(parents=True, exist_ok=True)
    (DOSSIERS / name / "SMOKE.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with db(write=True) as con:
        msg = (f"{result.get('command')}: {'PASS' if result.get('passed') else 'FAIL'} in {result.get('seconds')}s"
               if result["ran"] else result.get("reason", ""))
        log_event(con, actor, "smoke", msg, name)
    return result


def write_dossier(name: str, text: str, actor: str, fields: dict | None = None) -> Path:
    with db() as con:
        get_project(con, name)
    check_focus(name, actor)
    check_spotlight(name, actor)
    if actor in SCOUT_ACTORS:
        missing = [h for h in GEMMA["dossier_headings"] if h.lower() not in text.lower()]
        if missing:
            raise OrchError(f"dossier rejected: missing headings {missing}. Copy DOSSIER_TEMPLATE.md exactly "
                            "and fill every section (write 'unknown' rather than dropping a heading).")
        if len(text) > 12000:
            raise OrchError("dossier rejected: over 12000 characters. Summarize; the facts live in SCAN.json.")
        fields = fields or {}

        def section(h):
            m = re.search(rf"{re.escape(h)}\s*\n(.*?)(?=\n## |\Z)", text, re.S | re.I)
            return (m.group(1) if m else "").strip().lower()
        exp = section("## Player experience")
        if exp and not exp.startswith("unknown"):
            m = re.search(r"## Player experience\s*\n(.*?)(?=\n## |\Z)", text, re.S | re.I)
            fields["player_experience"] = " ".join(m.group(1).split())[:1200]
        if fields.get("playability_score") is not None and section("## Core loop") in ("", "unknown", "unknown."):
            raise OrchError("dossier rejected: Core loop is unknown, so leave out --playability (no evidence to score).")
        if fields.get("visual_maturity") is not None and section("## Visual cohesion").startswith("no evidence"):
            raise OrchError("dossier rejected: Visual cohesion has no evidence, so leave out --visual.")
        if fields.get("playability_score") == 0 and len(section("## Core loop")) > 40:
            raise OrchError("dossier rejected: playability 0 means nothing runs, but your Core loop describes one. "
                            "Score it 3-10, or leave out --playability.")
    d = DOSSIERS / name
    d.mkdir(parents=True, exist_ok=True)
    path = d / "DOSSIER.md"
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    if fields:
        update_project(name, fields, actor)
    with db(write=True) as con:
        con.execute("UPDATE projects SET last_scanned_at=? WHERE repo_name=?", (now(), name))
        log_event(con, actor, "dossier", "DOSSIER.md updated", name)
    return path


# ---------------------------------------------------------------- initiatives

def get_initiative(con, iid: int) -> dict:
    r = con.execute("SELECT * FROM initiatives WHERE id=?", (iid,)).fetchone()
    if not r:
        raise OrchError(f"unknown initiative: {iid}")
    return dict(r)


def design_dir(init: dict) -> Path:
    d = DESIGNS / f"{init['id']:04d}-{init['slug']}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def add_spark(project: str, category: str, title: str, pitch: str, actor: str,
              complexity: str | None = None, idempotency: str | None = None) -> dict:
    if category not in CATEGORIES:
        raise OrchError(f"category must be one of {CATEGORIES}")
    check_focus(project, actor)
    check_spotlight(project, actor, category)
    with db(write=True) as con:
        receipt = None
        body_hash = steering.version([project,category,title,pitch])
        if idempotency is not None:
            if not re.fullmatch(r"[a-zA-Z0-9-]{8,100}",idempotency): raise OrchError("invalid idempotency key")
            receipt = "idea:"+idempotency
            saved = con.execute("SELECT value FROM settings WHERE key=?",(receipt,)).fetchone()
            if saved:
                data = json.loads(saved[0])
                steering.expect(data["hash"],body_hash)
                return get_initiative(con,data["id"])
        if project != "NEW_CONCEPT":
            proj = get_project(con, project)
            complexity = complexity or proj["complexity"]
        complexity = complexity or "standard"
        if complexity not in COMPLEXITIES:
            raise OrchError(f"complexity must be one of {COMPLEXITIES}")
        dupe = con.execute("SELECT id FROM initiatives WHERE project_name=? AND lower(title)=lower(?)",
                           (project, title)).fetchone()
        if dupe:
            raise OrchError(f"duplicate of initiative #{dupe['id']}")
        ts = now()
        cur = con.execute(
            "INSERT INTO initiatives(project_name,category,title,slug,pitch_summary,stage,complexity,created_by,"
            "created_at,updated_at) VALUES (?,?,?,?,?,'spark',?,?,?,?)",
            (project, category, title, slugify(title), pitch, complexity, actor, ts, ts))
        init = get_initiative(con, cur.lastrowid)
        (design_dir(init) / "PITCH.md").write_text(
            f"# {title}\n\n- **Project:** {project}\n- **Category:** {category}\n- **Complexity:** {complexity}\n"
            f"- **Pitched by:** {actor} at {ts}\n\n{pitch.strip()}\n", encoding="utf-8")
        if receipt:
            con.execute("INSERT INTO settings VALUES (?,?)",(receipt,json.dumps({"id":init["id"],"hash":body_hash,"at":now()})))
            con.execute("DELETE FROM settings WHERE key IN (SELECT key FROM settings WHERE key LIKE 'idea:%' ORDER BY json_extract(value,'$.at') DESC LIMIT -1 OFFSET 100)")
        log_event(con, actor, "spark", title, project, init["id"])
        return init


def _set_stage(con, init: dict, stage: str, actor: str, note: str = "", **extra) -> dict:
    fields = {"stage": stage, "updated_at": now(), **extra}
    sets = ", ".join(f"{k}=?" for k in fields)
    con.execute(f"UPDATE initiatives SET {sets} WHERE id=?", (*fields.values(), init["id"]))
    log_event(con, actor, f"stage:{stage}", note or f"{init['stage']} -> {stage}", init["project_name"], init["id"])
    updated = get_initiative(con, init["id"])
    if stage in NOTIFY_STAGES and stage != init["stage"]:
        t = threading.Thread(target=fire_webhooks, args=(updated,), daemon=True)
        t.start()
        _webhook_threads.append(t)
    return updated


_webhook_threads: list[threading.Thread] = []


def fire_webhooks(init: dict) -> None:
    cfg = load_config().get("webhooks", {})
    if not cfg.get("enabled") or init["stage"] not in cfg.get("events", NOTIFY_STAGES):
        return
    port = load_config()["dashboard"]["port"]
    body = json.dumps({
        "event": f"awaiting_{init['stage']}" if init["stage"] != "playtest" else "entered_playtest",
        "initiative": init["id"], "project": init["project_name"], "title": init["title"],
        "stage": init["stage"], "url": f"http://localhost:{port}/#card-{init['id']}",
        "text": f"[{init['project_name']}] {init['title']} is now in {init['stage']}",
    }).encode()
    for url in cfg.get("urls", []):
        with contextlib.suppress(Exception):
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).close()


# ---------------------------------------------------------------- spotlight (all agents on one project/aspect)

ASPECTS = {
    "design": ["fun_gameplay", "new_game"],
    "content": ["fun_gameplay", "new_game"],
    "graphics": ["visual_craft"],
    "tech": ["tech_audacity", "optimization"],
    "optimization": ["optimization"],
    "any": list(CATEGORIES),
}


INDEFINITE = "9999-12-31T23:59:59+00:00"
ASSIGNEE_OF = {"scout-gemma": "gemma", "gemma": "gemma", "scout": "gemma", "planner-codex": "codex",
               "planner": "codex", "architect-claude": "claude", "architect": "claude"}


def until_from(hours: float | None) -> str:
    """hours None or <= 0 means indefinite (until ended by hand)."""
    if not hours or hours <= 0:
        return INDEFINITE
    return (dt.datetime.now().astimezone() + dt.timedelta(hours=hours)).isoformat(timespec="seconds")


def _load_spotlight_raw() -> dict | None:
    with db() as con:
        r = con.execute("SELECT value FROM settings WHERE key='spotlight'").fetchone()
    return json.loads(r["value"]) if r else None


def _save_spotlight(con, s: dict) -> None:
    con.execute("INSERT INTO settings(key, value) VALUES ('spotlight', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(s),))


def get_spotlight() -> dict | None:
    s = _load_spotlight_raw()
    return s if s and s.get("until", "") > now() else None


def spotlight(project: str, actor: str, aspect: str = "any", hours: float | None = None, note: str = "",
              mode: str = "graceful") -> dict:
    """Point every scheduled agent at one project (optionally one aspect).

    graceful: subtasks already `doing` on other projects may finish first; then their agent writes a handoff note.
    forced:   subtasks `doing` elsewhere are paused now (back to todo, flagged); their agent writes a handoff note first.
    Either way, an agent with an unwritten handoff note gets no spotlight work until it writes it.
    """
    if actor in AGENT_ACTORS:
        raise OrchError("only the producer or a chat session sets the spotlight")
    if aspect not in ASPECTS:
        raise OrchError(f"aspect must be one of {sorted(ASPECTS)}")
    if mode not in ("graceful", "forced"):
        raise OrchError("mode must be graceful or forced")
    with db(write=True) as con:
        get_project(con, project)
        inits = rows(con, "SELECT * FROM initiatives WHERE stage='building' AND project_name != ?", project)
        in_flight = []
        for i in inits:
            plan = json.loads(i["execution_plan_json"] or "{}")
            changed = False
            for s in plan.get("subtasks", []):
                if s.get("status") == "doing" and s.get("assignee") in ("gemma", "codex", "claude"):
                    in_flight.append({"initiative": i["id"], "project": i["project_name"], "sub": s["id"],
                                      "assignee": s["assignee"], "title": s["title"], "handoff_done": False})
                    if mode == "forced":
                        s["status"] = "todo"
                        s["paused_by_spotlight"] = True
                        s["notes"] = (s.get("notes", "") + f"\n[{now()} {actor}] PAUSED by forced spotlight on {project}").strip()
                        changed = True
            if changed:
                con.execute("UPDATE initiatives SET execution_plan_json=?, updated_at=? WHERE id=?",
                            (json.dumps(plan), now(), i["id"]))
        exp = until_from(hours)
        s = {"project": project, "aspect": aspect, "categories": ASPECTS[aspect], "until": exp, "mode": mode,
             "indefinite": exp == INDEFINITE, "note": note, "by": actor, "since": now(), "in_flight": in_flight}
        _save_spotlight(con, s)
        log_event(con, actor, "spotlight",
                  f"{mode} spotlight: all agents on {project} ({aspect}) until {'ended' if exp == INDEFINITE else exp}; "
                  f"{len(in_flight)} in-flight item(s) elsewhere" + (f": {note}" if note else ""), project)
    return s


def end_spotlight(actor: str) -> dict:
    s = get_spotlight()
    with db(write=True) as con:
        con.execute("DELETE FROM settings WHERE key='spotlight'")
        # un-flag paused subtasks so they flow normally again
        for i in rows(con, "SELECT id, execution_plan_json FROM initiatives WHERE execution_plan_json LIKE '%paused_by_spotlight%'"):
            plan = json.loads(i["execution_plan_json"])
            for sub in plan.get("subtasks", []):
                sub.pop("paused_by_spotlight", None)
            con.execute("UPDATE initiatives SET execution_plan_json=? WHERE id=?", (json.dumps(plan), i["id"]))
        log_event(con, actor, "spotlight_end", f"spotlight ended ({s['project'] if s else 'none active'})",
                  s["project"] if s else None)
    return {"ended": s}


def _sub_status(iid: int, sub_id) -> str | None:
    with db() as con:
        r = con.execute("SELECT execution_plan_json FROM initiatives WHERE id=?", (iid,)).fetchone()
    for s in json.loads((r and r["execution_plan_json"]) or "{}").get("subtasks", []):
        if int(s["id"]) == int(sub_id):
            return s.get("status")
    return None


def finishing(spot: dict | None, iid: int | None) -> bool:
    """Graceful mode: an agent may keep writing to an initiative whose in-flight subtask is still `doing`."""
    if not spot or spot.get("mode") != "graceful" or iid is None:
        return False
    return any(f["initiative"] == iid and _sub_status(iid, f["sub"]) == "doing" for f in spot.get("in_flight", []))


def handoffs_due(spot: dict | None, assignee: str) -> list[dict]:
    if not spot:
        return []
    due = []
    for f in spot.get("in_flight", []):
        if f["assignee"] != assignee or f["handoff_done"]:
            continue
        if spot.get("mode") == "graceful" and _sub_status(f["initiative"], f["sub"]) == "doing":
            continue  # still finishing; the note comes when it stops
        due.append(f)
    return due


def handoff_note(iid: int, note: str, actor: str) -> dict:
    """Document the state of work an agent is leaving. Always allowed, whatever mode is on."""
    if len(note.strip()) < 40:
        raise OrchError("handoff note too short: say what is done, what is left, and anything half-finished")
    with db() as con:
        init = get_initiative(con, iid)
    state = ""
    wt = init.get("worktree_path")
    if wt and Path(wt).exists():
        state = (f"- branch `{init['branch_name']}` at `{git(Path(wt), 'log', '-1', '--pretty=%h %s')}`\n"
                 f"- uncommitted:\n```\n{git(Path(wt), 'status', '--short') or '(clean)'}\n```\n")
    with (design_dir(init) / "HANDOFF_NOTES.md").open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {now()} by {actor}\n\n{note.strip()}\n\n{state}")
    assignee = ASSIGNEE_OF.get(actor)
    with db(write=True) as con:
        raw = con.execute("SELECT value FROM settings WHERE key='spotlight'").fetchone()
        if raw:
            s = json.loads(raw["value"])
            for f in s.get("in_flight", []):
                if f["initiative"] == iid and (assignee is None or f["assignee"] == assignee):
                    f["handoff_done"] = True
            _save_spotlight(con, s)
        log_event(con, actor, "handoff_note", note[:300], init["project_name"], iid)
    return {"ok": True, "file": str(design_dir(init) / "HANDOFF_NOTES.md")}


def check_spotlight(project: str, actor: str, category: str | None = None, iid: int | None = None) -> None:
    """While a spotlight is on, scheduled agents work only on that project (and aspect, for new sparks)."""
    s = get_spotlight()
    if not s or actor not in AGENT_ACTORS:
        return
    if project != s["project"]:
        if finishing(s, iid):
            return
        raise OrchError(f"spotlight is on {s['project']} ({s.get('mode', 'graceful')}); agents work only there. "
                        f"Skip {project}. If you were in the middle of work here, write `handoff-note <id> --note ...` first.")
    due = handoffs_due(s, ASSIGNEE_OF.get(actor, ""))
    if due:
        raise OrchError("write your handoff note(s) before starting spotlight work: "
                        + ", ".join(f"#{f['initiative']} sub {f['sub']}" for f in due))
    if category and category not in s["categories"]:
        raise OrchError(f"spotlight aspect is '{s['aspect']}': sparks must be one of {s['categories']}")


# ---------------------------------------------------------------- claims (interactive chat sessions)

def active_claim(init: dict) -> str | None:
    if init.get("claimed_by") and (init.get("claim_expires_at") or "") > now():
        return init["claimed_by"]
    return None


def active_focus(proj: dict | None) -> str | None:
    if proj and proj.get("focus_by") and (proj.get("focus_until") or "") > now():
        return proj["focus_by"]
    return None


def focused_projects() -> dict[str, dict]:
    with db() as con:
        ps = rows(con, "SELECT repo_name, focus_by, focus_until, focus_note FROM projects WHERE focus_by IS NOT NULL")
    return {p["repo_name"]: p for p in ps if active_focus(p)}


def check_focus(project: str, actor: str) -> None:
    """Scheduled agents stay out of a project while the producer runs a frontier focus session on it."""
    if actor not in AGENT_ACTORS:
        return
    f = focused_projects().get(project)
    if f:
        raise OrchError(f"{project} is in a focus session with '{f['focus_by']}' until {f['focus_until']} "
                        f"({f['focus_note'] or 'manual frontier work'}). Skip this project.")


def check_claim(init: dict, actor: str) -> None:
    """Scheduled agents may not touch a card an interactive session has claimed, or any card in a focused project."""
    who = active_claim(init)
    if who and actor in AGENT_ACTORS and actor != who:
        raise OrchError(f"#{init['id']} is claimed by '{who}' until {init['claim_expires_at']} "
                        f"({init.get('claim_note') or 'being handled in chat'}). Skip it.")
    check_focus(init["project_name"], actor)
    check_spotlight(init["project_name"], actor, iid=init["id"])


def focus(project: str, actor: str, hours: float | None = None, note: str = "") -> dict:
    if actor in AGENT_ACTORS:
        raise OrchError("focus sessions are for interactive sessions (e.g. --as claude-desktop, --as codex-cli)")
    with db(write=True) as con:
        proj = get_project(con, project)
        who = active_focus(proj)
        if who and who != actor:
            raise OrchError(f"{project} is already in focus with '{who}' until {proj['focus_until']}")
        exp = until_from(hours)
        con.execute("UPDATE projects SET focus_by=?, focus_until=?, focus_note=? WHERE repo_name=?",
                    (actor, exp, note or None, project))
        log_event(con, actor, "focus", f"focus session until {exp}" + (f": {note}" if note else ""), project)
        return get_project(con, project)


def unfocus(project: str, actor: str, note: str = "") -> dict:
    with db(write=True) as con:
        proj = get_project(con, project)
        con.execute("UPDATE projects SET focus_by=NULL, focus_until=NULL, focus_note=NULL WHERE repo_name=?", (project,))
        log_event(con, actor, "unfocus", note or f"focus session ended (was {proj.get('focus_by')})", project)
        return get_project(con, project)


def claim(iid: int, actor: str, hours: float = CLAIM_HOURS, note: str = "") -> dict:
    if actor in AGENT_ACTORS:
        raise OrchError("claims are for interactive sessions (e.g. --as claude-desktop, --as codex-cli)")
    with db(write=True) as con:
        init = get_initiative(con, iid)
        if init["stage"] in ("done", "rejected"):
            raise OrchError(f"#{iid} is {init['stage']}")
        who = active_claim(init)
        if who and who != actor:
            raise OrchError(f"#{iid} is already claimed by '{who}' until {init['claim_expires_at']}; "
                            f"run `release {iid}` first if that session is finished")
        exp = (dt.datetime.now().astimezone() + dt.timedelta(hours=hours)).isoformat(timespec="seconds")
        con.execute("UPDATE initiatives SET claimed_by=?, claimed_at=?, claim_expires_at=?, claim_note=? WHERE id=?",
                    (actor, now(), exp, note or None, iid))
        log_event(con, actor, "claim", f"claimed until {exp}" + (f": {note}" if note else ""), init["project_name"], iid)
        return get_initiative(con, iid)


def release(iid: int, actor: str, note: str = "") -> dict:
    with db(write=True) as con:
        init = get_initiative(con, iid)
        con.execute("UPDATE initiatives SET claimed_by=NULL, claimed_at=NULL, claim_expires_at=NULL, claim_note=NULL "
                    "WHERE id=?", (iid,))
        log_event(con, actor, "release", note or f"released (was {init.get('claimed_by')})", init["project_name"], iid)
        return get_initiative(con, iid)


AWAITING_PRODUCER = {"spark": "pitch to approve", "hld_review": "HLD to review", "lld_review": "LLD + plan to review",
                     "playtest": "branch to playtest"}


def inbox() -> dict:
    """Everything an interactive session needs to pick up work: producer gates, agent work, claims."""
    with db() as con:
        inits = rows(con, "SELECT * FROM initiatives WHERE stage NOT IN ('done','rejected') ORDER BY updated_at DESC")
        events = rows(con, "SELECT ts, actor, project_name, initiative_id, kind, message FROM events "
                           "ORDER BY id DESC LIMIT 15")

    def card(i):
        d = {k: i[k] for k in ("id", "project_name", "category", "title", "stage", "complexity", "branch_name",
                                "revision_note", "updated_at")}
        d["design_dir"] = str(DESIGNS / f"{i['id']:04d}-{i['slug']}")
        if i["worktree_path"]:
            d["worktree"] = i["worktree_path"]
        if i["execution_plan_json"]:
            subs = json.loads(i["execution_plan_json"]).get("subtasks", [])
            d["subtasks"] = [{k: s.get(k) for k in ("id", "title", "assignee", "status")} for s in subs]
        if active_claim(i):
            d["claimed_by"], d["claim_expires_at"], d["claim_note"] = i["claimed_by"], i["claim_expires_at"], i["claim_note"]
        return d
    awaiting = [dict(card(i), needs=AWAITING_PRODUCER[i["stage"]]) for i in inits if i["stage"] in AWAITING_PRODUCER]
    in_flight = [card(i) for i in inits if i["stage"] not in AWAITING_PRODUCER]
    return {"awaiting_you": awaiting, "in_flight": in_flight,
            "focus_sessions": list(focused_projects().values()),
            "spotlight": get_spotlight(),
            "claimed": [c for c in awaiting + in_flight if c.get("claimed_by")],
            "recent_activity": events,
            "how_to": "claim <id> before working on a card; agents skip claimed cards. release <id> or advance it when done."}


def inbox_md(b: dict) -> str:
    def line(c):
        cl = f" · **claimed by {c['claimed_by']}**" if c.get("claimed_by") else ""
        subs = ""
        if c.get("subtasks"):
            subs = " · " + ", ".join(f"{s['id']}:{s['assignee']}/{s['status']}" for s in c["subtasks"])
        rev = f"\n  - revision asked: {c['revision_note']}" if c.get("revision_note") else ""
        return (f"- **#{c['id']} {c['title']}** ({c['project_name']}, {c['category']}, `{c['stage']}`"
                f"{', high complexity' if c['complexity'] == 'high' else ''}){cl}{subs}\n  - files: `{c['design_dir']}`{rev}")
    out = ["# Producer inbox", ""]
    if b.get("spotlight"):
        s = b["spotlight"]
        out += [f"**SPOTLIGHT:** all agents on **{s['project']}** · aspect `{s['aspect']}` · until "
                f"{s['until'][:16].replace('T', ' ')}" + (f" · {s['note']}" if s.get("note") else ""), ""]
    if b.get("focus_sessions"):
        out += ["## Focus sessions (agents stay out)"]
        out += [f"- **{f['repo_name']}** with {f['focus_by']} until {f['focus_until'][:16].replace('T', ' ')}"
                f"{' · ' + f['focus_note'] if f['focus_note'] else ''}" for f in b["focus_sessions"]] + [""]
    out += [f"## Awaiting you ({len(b['awaiting_you'])})"]
    out += [line(c) + f"\n  - needs: {c['needs']}" for c in b["awaiting_you"]] or ["- nothing"]
    out += ["", f"## In flight with agents ({len(b['in_flight'])})"]
    out += [line(c) for c in b["in_flight"]] or ["- nothing"]
    out += ["", "## Recent activity"]
    out += [f"- {e['ts'][5:16]} {e['actor']}: {e['kind']} {('#' + str(e['initiative_id']) + ' ') if e['initiative_id'] else ''}"
            f"{e['project_name'] or ''} {(e['message'] or '')[:90]}" for e in b["recent_activity"]]
    return "\n".join(out)


def attach(iid: int, kind: str, src_text: str, actor: str, model: str | None = None) -> dict:
    """Attach an HLD, LLD, or execution plan and move the card to its review gate."""
    with db(write=True) as con:
        init = get_initiative(con, iid)
        check_claim(init, actor)
        d = design_dir(init)
        if kind == "hld":
            if init["stage"] not in ("hld_draft", "spark"):
                raise OrchError(f"#{iid} is in {init['stage']}; HLDs attach in hld_draft")
            p = d / "HLD.md"
            p.write_text(src_text.rstrip() + "\n", encoding="utf-8")
            return _set_stage(con, init, "hld_review", actor, "HLD attached", hld_path=str(p),
                              assigned_model=model or init["assigned_model"], revision_note=None)
        if kind == "lld":
            if init["stage"] != "lld_draft":
                raise OrchError(f"#{iid} is in {init['stage']}; LLDs attach in lld_draft")
            p = d / "LLD.md"
            p.write_text(src_text.rstrip() + "\n", encoding="utf-8")
            con.execute("UPDATE initiatives SET lld_path=? WHERE id=?", (str(p), iid))
            log_event(con, actor, "lld", "LLD attached", init["project_name"], iid)
            init = get_initiative(con, iid)
            if init["execution_plan_json"]:
                return _set_stage(con, init, "lld_review", actor, "LLD + plan ready", revision_note=None)
            return init
        if kind == "plan":
            plan = validate_plan(src_text, init["complexity"])
            if init["stage"] not in ("lld_draft", "building"):
                raise OrchError(f"#{iid} is in {init['stage']}; plans attach in lld_draft or building")
            con.execute("UPDATE initiatives SET execution_plan_json=? WHERE id=?", (json.dumps(plan), iid))
            log_event(con, actor, "plan", f"{len(plan['subtasks'])} subtasks", init["project_name"], iid)
            init = get_initiative(con, iid)
            if init["stage"] == "lld_draft" and init["lld_path"]:
                return _set_stage(con, init, "lld_review", actor, "LLD + plan ready", revision_note=None)
            return init
    raise OrchError(f"unknown attachment kind: {kind}")


def ready(sub: dict, subs: list[dict]) -> bool:
    """A subtask may start when its prerequisites are done.

    Explicit `depends_on: [ids]` wins; otherwise the plan is ordered and every earlier subtask
    (except ide_handoff ones, which the producer does at the end) must be done.
    """
    done = {int(s["id"]) for s in subs if s.get("status") == "done"}
    if "depends_on" in sub:
        return all(int(d) in done for d in sub.get("depends_on") or [])
    pos = next((n for n,s in enumerate(subs) if s["id"] == sub["id"]), len(subs))
    return all(int(s["id"]) in done for s in subs[:pos] if s.get("assignee") != "ide_handoff")


def reroute(iid: int, sub_id: int, to: str, actor: str, note: str = "") -> dict:
    """Producer/chat override of a subtask's assignee (agents use escalate)."""
    if actor in AGENT_ACTORS:
        raise OrchError("agents escalate; only the producer or a chat session reroutes")
    if to not in ASSIGNEES:
        raise OrchError(f"assignee must be one of {ASSIGNEES}")
    with db(write=True) as con:
        init = get_initiative(con, iid)
        plan = json.loads(init["execution_plan_json"] or "{}")
        s = next((x for x in plan.get("subtasks", []) if int(x["id"]) == int(sub_id)), None)
        if not s:
            raise OrchError(f"#{iid} has no subtask {sub_id}")
        if to == "gemma":
            why = gemma_fit(s, init["complexity"])
            if why:
                raise OrchError("not gemma-safe: " + "; ".join(why))
        prev = s["assignee"]
        s.update(assignee=to, status="todo", attempts=0)
        s.pop("escalated_from", None)
        s["notes"] = (s.get("notes", "") + f"\n[{now()} {actor}] REROUTED {prev}->{to}: {note}").strip()
        con.execute("UPDATE initiatives SET execution_plan_json=?, updated_at=? WHERE id=?",
                    (json.dumps(plan), now(), iid))
        log_event(con, actor, "reroute", f"subtask {sub_id} {prev}->{to}: {note}"[:300], init["project_name"], iid)
        return get_initiative(con, iid)


def gemma_fit(s: dict, complexity: str) -> list[str]:
    """Reasons a subtask is outside Gemma's contract. Empty list = OK to route to gemma."""
    why = []
    files = s.get("files") or []
    if not 1 <= len(files) <= GEMMA["max_files"]:
        why.append(f"must list 1-{GEMMA['max_files']} exact `files` (has {len(files)})")
    if not (s.get("instructions") or "").strip():
        why.append("needs step-by-step `instructions`")
    if not (s.get("acceptance") or "").strip():
        why.append("needs an `acceptance` criterion")
    if not (s.get("verify") or "").strip():
        why.append("needs a `verify` shell command that exits 0 on success")
    if len(s.get("instructions") or "") > 3000:
        why.append("instructions over 3000 chars means the task is too big; split it")
    if complexity == "high" and not s.get("mechanical"):
        why.append("high-complexity project: only subtasks flagged `\"mechanical\": true` "
                   "(renames, data tables, test scaffolds, docs) may go to gemma")
    return why


def validate_plan(text: str, complexity: str = "standard") -> dict:
    try:
        plan = json.loads(text)
    except json.JSONDecodeError as e:
        raise OrchError(f"plan is not valid JSON: {e}")
    subs = plan.get("subtasks")
    if not isinstance(subs, list) or not subs:
        raise OrchError("plan needs a non-empty `subtasks` list")
    problems = []
    for n, s in enumerate(subs, 1):
        s.setdefault("id", n)
        s.setdefault("status", "todo")
        s.setdefault("notes", "")
        s.setdefault("attempts", 0)
        if s.get("assignee") not in ASSIGNEES:
            raise OrchError(f"subtask {s['id']}: assignee must be one of {ASSIGNEES}")
        if not s.get("title"):
            raise OrchError(f"subtask {s['id']}: needs a title")
        if s["assignee"] == "gemma":
            problems += [f"subtask {s['id']}: {w}" for w in gemma_fit(s, complexity)]
    if problems:
        raise OrchError("gemma routing rejected (see GEMMA_CAPABILITIES.md); fix or route to codex/claude: "
                        + "; ".join(problems))
    plan.setdefault("review", {"status": "pending", "notes": ""})
    return plan


def escalate(iid: int, sub_id: int, reason: str, actor: str, to: str | None = None) -> dict:
    """Move a gemma subtask to a frontier model. Any agent may call this; gemma should when unsure."""
    to = to or GEMMA["escalate_to"]
    if to not in ("codex", "claude", "ide_handoff"):
        raise OrchError("escalate to codex|claude|ide_handoff")
    with db(write=True) as con:
        init = get_initiative(con, iid)
        check_claim(init, actor)
        plan = json.loads(init["execution_plan_json"] or "{}")
        for s in plan.get("subtasks", []):
            if int(s["id"]) == int(sub_id):
                prev = s["assignee"]
                s.update(assignee=to, status="todo", escalated_from=prev)
                s["notes"] = (s.get("notes", "") + f"\n[{now()} {actor}] ESCALATED {prev}->{to}: {reason}").strip()
                break
        else:
            raise OrchError(f"#{iid} has no subtask {sub_id}")
        con.execute("UPDATE initiatives SET execution_plan_json=?, updated_at=? WHERE id=?",
                    (json.dumps(plan), now(), iid))
        log_event(con, actor, "escalated", f"subtask {sub_id} {prev}->{to}: {reason}"[:300], init["project_name"], iid)
        return get_initiative(con, iid)


def subtask_update(iid: int, sub_id: int, status: str, note: str, actor: str) -> dict:
    if status not in ("todo", "doing", "done", "blocked"):
        raise OrchError("status must be todo|doing|done|blocked")
    with db(write=True) as con:
        init = get_initiative(con, iid)
        check_claim(init, actor)
        if init["stage"] != "building":
            raise OrchError(f"#{iid} is in {init['stage']}; subtasks run in building")
        plan = json.loads(init["execution_plan_json"] or "{}")
        for s in plan.get("subtasks", []):
            if int(s["id"]) == int(sub_id):
                if actor in SCOUT_ACTORS and s["assignee"] != "gemma":
                    raise OrchError(f"subtask {sub_id} is routed to {s['assignee']}, not gemma")
                if status == "done" and actor in SCOUT_ACTORS and not s.get("verify_ok"):
                    raise OrchError(f"run `orch.py verify {iid} {sub_id}` and get a pass before marking done")
                previous = s.get("status")
                if status == "doing" and previous != "doing":
                    s["run_attempt"] = uuid.uuid4().hex
                details = {"v":1,"work_type":"build","stage":"building","subtask_id":sub_id,
                           "attempt":s.get("run_attempt"),"from":previous,"to":status}
                s["status"] = status
                if note:
                    s["notes"] = (s.get("notes", "") + f"\n[{now()} {actor}] {note}").strip()
                if status == "blocked" and s["assignee"] == "gemma":
                    s["attempts"] = int(s.get("attempts", 0)) + 1
                break
        else:
            raise OrchError(f"#{iid} has no subtask {sub_id}")
        con.execute("UPDATE initiatives SET execution_plan_json=?, updated_at=? WHERE id=?",
                    (json.dumps(plan), now(), iid))
        log_event(con, actor, "subtask", f"{sub_id} -> {status}: {note}"[:300], init["project_name"], iid, details)
        auto = status == "blocked" and s["assignee"] == "gemma" and s["attempts"] >= GEMMA["max_attempts"]
    if auto:
        return escalate(iid, sub_id, f"gemma blocked {s['attempts']}x: {note}", "orch")
    with db() as con:
        return get_initiative(con, iid)


def review_build(iid: int, verdict: str, note: str, actor: str) -> dict:
    """Planner's code review of a feat branch. pass -> playtest; fail -> stays in building with notes."""
    if verdict not in ("pass", "fail"):
        raise OrchError("verdict must be pass|fail")
    with db(write=True) as con:
        init = get_initiative(con, iid)
        check_claim(init, actor)
        if init["stage"] != "building":
            raise OrchError(f"#{iid} is in {init['stage']}")
        plan = json.loads(init["execution_plan_json"] or "{}")
        plan["review"] = {"status": verdict, "notes": note, "by": actor, "at": now()}
        con.execute("UPDATE initiatives SET execution_plan_json=? WHERE id=?", (json.dumps(plan), iid))
        if verdict == "pass":
            return _set_stage(con, init, "playtest", actor, f"Review passed: {note}"[:300])
        con.execute("UPDATE initiatives SET revision_note=?, updated_at=? WHERE id=?", (note, now(), iid))
        log_event(con, actor, "review_fail", note[:300], init["project_name"], iid)
        return get_initiative(con, iid)


def lane_control(declaration, enabled, expected, actor, controller=None):
    import dashboard_ops
    return dashboard_ops.lane_control(sys.modules[__name__],declaration,enabled,expected,actor,controller)


def project_version(project):
    return steering.version({k:project.get(k) for k in sorted(PROJECT_FIELDS)})


def set_initiative(iid, priority, expected, actor):
    if priority not in ('high','medium','low'):
        raise OrchError('initiative priority must be high/medium/low')
    with db(write=True) as con:
        init = get_initiative(con,iid)
        check_claim(init,actor)
        steering.expect(steering.version(init),expected)
        con.execute('UPDATE initiatives SET priority=? WHERE id=?',(priority,iid))
        log_event(con,actor,'initiative_priority',priority,init['project_name'],iid)
        return get_initiative(con,iid)


def reorder_subtasks(iid, order, expected, actor):
    with db(write=True) as con:
        init = get_initiative(con,iid)
        check_claim(init,actor)
        steering.expect(steering.version(init['execution_plan_json']),expected)
        plan = json.loads(init['execution_plan_json'] or '{}')
        try:
            plan['subtasks'] = steering.reordered(plan.get('subtasks',[]),order)
        except ValueError as exc:
            raise OrchError(str(exc)) from exc
        con.execute('UPDATE initiatives SET execution_plan_json=? WHERE id=?',(json.dumps(plan),iid))
        log_event(con,actor,'subtask_order',json.dumps(order),init['project_name'],iid)
        return get_initiative(con,iid)


# ---------------------------------------------------------------- producer controls

def advance(iid: int, actor: str = "producer", note: str = "") -> dict:
    with db(write=True) as con:
        init = get_initiative(con, iid)
        nxt = ADVANCE.get(init["stage"])
        if not nxt:
            raise OrchError(f"#{iid} is {init['stage']}; nothing to advance to")
        if nxt == "building":
            if init["project_name"] == "NEW_CONCEPT":
                raise OrchError("NEW_CONCEPT has no repo yet. Create the repo, then re-home the card "
                                "(orch.py rehome) before building.")
            if not init["execution_plan_json"]:
                raise OrchError("cannot start building without an execution plan")
            branch, wt = create_branch(con, init)
            return _set_stage(con, init, "building", actor, note or "Approved for build",
                              branch_name=branch, worktree_path=str(wt), revision_note=None)
        if nxt == "done" and init["project_name"] == SELF_REPO and init.get("branch_name"):
            shipped = ship_self(init)  # raises (card stays in playtest) if the merge can't be done cleanly
            done = _set_stage(con, init, "done", actor, (note or "Approved") + f"; shipped: {shipped}",
                              revision_note=None)
            _restart_after_ship.append(True)
            return done
        return _set_stage(con, init, nxt, actor, note or "Approved", revision_note=None)


_restart_after_ship: list[bool] = []


def ship_self(init: dict) -> str:
    """Merge an approved 000-orchestrator feature into the live orchestrator's main, push, and clean up."""
    repo, branch = ORCH, init["branch_name"]
    if not branch.startswith("feat/"):
        raise OrchError(f"refusing to ship non-feat branch {branch}")
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD") != "main":
        raise OrchError("live orchestrator checkout is not on main; ship by hand")
    dirty = [l for l in git(repo, "status", "--porcelain").splitlines() if l and not l.endswith(".tmp")]
    if dirty:
        raise OrchError(f"live orchestrator has uncommitted changes ({len(dirty)}); commit them, then approve again")
    p = run(["git", "-C", str(repo), "merge", "--no-ff", branch, "-m",
             f"Ship #{init['id']}: {init['title']}\n\nMerged {branch} on producer approval."])
    if p.returncode != 0:
        run(["git", "-C", str(repo), "merge", "--abort"])
        raise OrchError(f"merge of {branch} failed; card left in playtest: {(p.stdout + p.stderr).strip()[:300]}")
    sha = git(repo, "rev-parse", "--short", "HEAD")
    pushed = run(["git", "-C", str(repo), "push", "-q"], timeout=120).returncode == 0
    wt = init.get("worktree_path")
    if wt and Path(wt).exists():
        run(["git", "-C", str(repo), "worktree", "remove", "--force", wt])
    run(["git", "-C", str(repo), "worktree", "prune"])
    run(["git", "-C", str(repo), "branch", "-d", branch])
    return f"{sha}{'' if pushed else ' (push failed; push by hand)'}"


def restart_dashboard(delay: int = 3) -> None:
    """Restart the always-on dashboard in a detached process (it may be the caller), so merged code goes live."""
    if os.name != "nt":
        return
    vbs = ORCH / "dashboard" / "serve-hidden.vbs"
    ps = (f"Start-Sleep -Seconds {delay}; "
          "Get-NetTCPConnection -LocalPort 8420 -State Listen -ErrorAction SilentlyContinue | "
          "ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}; "
          "Start-Sleep -Seconds 2; "
          f"Start-Process -FilePath \"$env:WINDIR\\System32\\wscript.exe\" -ArgumentList '\"{vbs}\"'")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) \
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps.replace("{{", "{").replace("}}", "}")],
                     creationflags=flags, close_fds=True)


def revise(iid: int, note: str, actor: str = "producer") -> dict:
    if not note.strip():
        raise OrchError("a revision request needs feedback text")
    with db(write=True) as con:
        init = get_initiative(con, iid)
        back = REVISE.get(init["stage"])
        if not back:
            raise OrchError(f"#{iid} is {init['stage']}; cannot revise")
        if back == "building" and init["execution_plan_json"]:
            plan = json.loads(init["execution_plan_json"])
            plan["review"] = {"status": "pending", "notes": f"Producer revision: {note}"}
            con.execute("UPDATE initiatives SET execution_plan_json=? WHERE id=?", (json.dumps(plan), iid))
        with (design_dir(init) / "REVISIONS.md").open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {now()} at {init['stage']}\n\n{note.strip()}\n")
        return _set_stage(con, init, back, actor, f"Revision requested: {note}"[:300], revision_note=note)


def reject(iid: int, note: str, actor: str = "producer") -> dict:
    if not note.strip():
        raise OrchError("a rejection needs a reason (it trains the taste profile)")
    with db(write=True) as con:
        init = get_initiative(con, iid)
        if init["stage"] in ("rejected", "done"):
            raise OrchError(f"#{iid} is already {init['stage']}")
        deleted = delete_branch(con, init)
        append_taste(init, note)
        msg = f"Rejected at {init['stage']}: {note}" + (f" (deleted {deleted})" if deleted else "")
        return _set_stage(con, init, "rejected", actor, msg[:300], rejection_reason=note,
                          claimed_by=None, claimed_at=None, claim_expires_at=None, claim_note=None)


def append_taste(init: dict, note: str) -> None:
    if not TASTE.exists():
        TASTE.write_text(TASTE_TEMPLATE, encoding="utf-8")
    clean = " ".join(note.split())
    with TASTE.open("a", encoding="utf-8") as fh:
        fh.write(f"- {now()} | {init['project_name']} | #{init['id']} {init['title']} | "
                 f"rejected at `{init['stage']}` | {clean}\n")


def rehome(iid: int, project: str, actor: str = "producer") -> dict:
    with db(write=True) as con:
        init = get_initiative(con, iid)
        get_project(con, project)
        con.execute("UPDATE initiatives SET project_name=?, updated_at=? WHERE id=?", (project, now(), iid))
        log_event(con, actor, "rehome", f"NEW_CONCEPT -> {project}", project, iid)
        return get_initiative(con, iid)


# ---------------------------------------------------------------- branches (the main guard lives here)

def _repo_for(con, init: dict) -> tuple[dict, Path]:
    proj = get_project(con, init["project_name"])
    if not proj["is_git"]:
        raise OrchError(f"{proj['repo_name']} is not a git repo; building is disabled for it")
    return proj, Path(proj["local_path"])


def create_branch(con, init: dict) -> tuple[str, Path]:
    """Create feat/<slug> in a separate worktree. The user's checkout is never switched."""
    proj, repo = _repo_for(con, init)
    branch = f"feat/{init['slug']}"
    base = proj["default_branch"] or default_branch(repo)
    if not base:
        raise OrchError(f"cannot find a default branch for {proj['repo_name']}")
    wt = WORKTREES / proj["repo_name"] / init["slug"]
    if wt.exists():
        return branch, wt
    wt.parent.mkdir(parents=True, exist_ok=True)
    exists = git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    args = ["worktree", "add", str(wt), branch] if exists else ["worktree", "add", "-b", branch, str(wt), base]
    p = run(["git", "-C", str(repo), *args])
    if p.returncode != 0:
        raise OrchError(f"git worktree add failed: {p.stderr.strip()}")
    return branch, wt


def delete_branch(con, init: dict) -> str:
    """Remove the worktree, then the local feat/ branch. Only branches recorded in the DB; never remote."""
    branch = init.get("branch_name")
    if not branch:
        return ""
    if not branch.startswith("feat/") or branch.split("/", 1)[1] in PROTECTED_BRANCHES:
        raise OrchError(f"refusing to delete non-feat branch {branch}")
    proj, repo = _repo_for(con, init)
    wt = init.get("worktree_path")
    if wt and Path(wt).exists():
        run(["git", "-C", str(repo), "worktree", "remove", "--force", wt])
        if Path(wt).exists():
            shutil.rmtree(wt, ignore_errors=True)
    run(["git", "-C", str(repo), "worktree", "prune"])
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD") == branch:
        raise OrchError(f"{branch} is checked out in the main checkout; not deleting it")
    run(["git", "-C", str(repo), "branch", "-D", branch])
    return branch


def guard(path: Path) -> dict:
    """Exit non-zero unless `path` is inside an orchestrator worktree on a feat/ branch."""
    path = path.resolve()
    if WORKTREES.resolve() not in path.parents and path != WORKTREES.resolve():
        raise OrchError(f"{path} is not under {WORKTREES}; agents only write inside worktrees")
    branch = git(path, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch.startswith("feat/") or branch in PROTECTED_BRANCHES:
        raise OrchError(f"{path} is on '{branch}', not a feat/ branch")
    return {"path": str(path), "branch": branch, "ok": True}


def _subtask(init: dict, sub_id: int) -> dict:
    for s in json.loads(init["execution_plan_json"] or "{}").get("subtasks", []):
        if int(s["id"]) == int(sub_id):
            return s
    raise OrchError(f"#{init['id']} has no subtask {sub_id}")


def changed_lines(wt: Path) -> dict[str, int]:
    run(["git", "-C", str(wt), "add", "-A"], check=True)
    out = {}
    for line in git(wt, "diff", "--cached", "--numstat").splitlines():
        a, d, f = line.split("\t", 2)
        out[f] = (int(a) if a.isdigit() else 999) + (int(d) if d.isdigit() else 999)  # binary counts as huge
    return out


def verify(iid: int, sub_id: int, actor: str) -> dict:
    """Run a subtask's verify command in its worktree and record pass/fail."""
    with db() as con:
        init = get_initiative(con, iid)
        check_claim(init, actor)
    if init["stage"] != "building" or not init["worktree_path"]:
        raise OrchError(f"#{iid} has no active build worktree")
    s = _subtask(init, sub_id)
    cmd = s.get("verify")
    if not cmd:
        raise OrchError(f"subtask {sub_id} has no verify command")
    wt = Path(init["worktree_path"])
    guard(wt)
    try:
        p = sh(cmd, wt, 900)
        ok, tail = p.returncode == 0, (p.stdout + p.stderr)[-2500:]
    except subprocess.TimeoutExpired:
        ok, tail = False, "verify timed out after 900s"
    with db(write=True) as con:
        init = get_initiative(con, iid)
        plan = json.loads(init["execution_plan_json"])
        for t in plan["subtasks"]:
            if int(t["id"]) == int(sub_id):
                t["verify_ok"] = ok
                t["last_verify"] = {"at": now(), "ok": ok, "output_tail": tail}
        con.execute("UPDATE initiatives SET execution_plan_json=? WHERE id=?", (json.dumps(plan), iid))
        log_event(con, actor, "verify", f"subtask {sub_id}: {'PASS' if ok else 'FAIL'}", init["project_name"], iid)
    return {"ok": ok, "output_tail": tail}


def discard(iid: int, actor: str) -> dict:
    """Throw away uncommitted changes in the initiative's worktree (never touches the user's checkout)."""
    with db() as con:
        init = get_initiative(con, iid)
        check_claim(init, actor)
    wt = Path(init["worktree_path"] or "")
    guard(wt)
    run(["git", "-C", str(wt), "reset", "--hard", "-q"], check=True)
    run(["git", "-C", str(wt), "clean", "-fdq"], check=True)
    with db(write=True) as con:
        log_event(con, actor, "discard", "uncommitted worktree changes discarded", init["project_name"], iid)
    return {"ok": True, "worktree": str(wt)}


def commit(iid: int, message: str, actor: str, sub_id: int | None = None) -> str:
    with db() as con:
        init = get_initiative(con, iid)
        check_claim(init, actor)
    if init["stage"] != "building" or not init["worktree_path"]:
        raise OrchError(f"#{iid} has no active build worktree")
    wt = Path(init["worktree_path"])
    guard(wt)
    if actor in SCOUT_ACTORS:
        if sub_id is None:
            raise OrchError("gemma commits must name the subtask: orch.py commit <id> --sub <n> -m ...")
        s = _subtask(init, sub_id)
        if s["assignee"] != "gemma":
            raise OrchError(f"subtask {sub_id} is routed to {s['assignee']}, not gemma")
        changes = changed_lines(wt)
        allowed = {f.replace("\\", "/") for f in s.get("files", [])}
        stray = sorted(set(changes) - allowed)
        total = sum(changes.values())
        if stray or total > GEMMA["max_changed_lines"]:
            raise OrchError(
                f"commit refused: {'files outside the subtask: ' + ', '.join(stray) + '; ' if stray else ''}"
                f"{total} changed lines (limit {GEMMA['max_changed_lines']}). Run `orch.py discard {iid}`, then "
                f"`orch.py subtask {iid} {sub_id} blocked --note \"<why>\"` so a frontier model takes it.")
        message = f"[gemma] {message}"
    run(["git", "-C", str(wt), "add", "-A"], check=True)
    p = run(["git", "-C", str(wt), "commit", "-m", f"{message}\n\nOrchestrator: #{iid} by {actor}"])
    if p.returncode != 0 and "nothing to commit" not in p.stdout + p.stderr:
        raise OrchError(p.stderr.strip() or p.stdout.strip())
    sha = git(wt, "rev-parse", "HEAD")
    with db(write=True) as con:
        current = get_initiative(con, iid)
        if sub_id is not None and p.returncode == 0:
            plan = json.loads(current["execution_plan_json"] or "{}")
            sub = next(x for x in plan["subtasks"] if int(x["id"]) == int(sub_id))
            commits = sub.setdefault("commit_shas", [])
            if sha not in commits:
                commits.append(sha)
            con.execute("UPDATE initiatives SET execution_plan_json=? WHERE id=?", (json.dumps(plan),iid))
        log_event(con, actor, "commit", f"{sha} {message}"[:300], init["project_name"], iid,
                  {"v":1,"subtask_id":sub_id,"sha":sha})
    return sha


def diff_summary(init: dict) -> dict:
    if not init.get("branch_name") or not init.get("worktree_path") or not Path(init["worktree_path"]).exists():
        return {}
    with db() as con:
        proj = get_project(con, init["project_name"])
    wt = Path(init["worktree_path"])
    base = proj["default_branch"] or "main"
    mb = git(wt, "merge-base", base, "HEAD")
    return {
        "branch": init["branch_name"],
        "worktree": str(wt),
        "base": base,
        "commits": git(wt, "log", "--pretty=format:%h %ad %s", "--date=short", f"{mb}..HEAD").splitlines() if mb else [],
        "stat": git(wt, "diff", "--stat", mb) if mb else "",
        "uncommitted": git(wt, "status", "--porcelain").splitlines(),
    }


def ide_handoff(iid: int) -> Path:
    with db() as con:
        init = get_initiative(con, iid)
    plan = json.loads(init["execution_plan_json"] or "{}")
    subs = [s for s in plan.get("subtasks", []) if s["assignee"] == "ide_handoff"]
    d = design_dir(init)
    parts = [f"# IDE handoff: #{iid} {init['title']}\n",
             f"- Project: `{init['project_name']}`\n- Branch: `{init['branch_name']}`\n"
             f"- Worktree: `{init['worktree_path']}`\n- Never commit to main; this worktree is already on the feat branch.\n"]
    for s in subs:
        parts.append(f"\n## Subtask {s['id']}: {s['title']}\n\n{s.get('instructions', '')}\n\n"
                     f"**Files:** {', '.join(s.get('files', [])) or 'see LLD'}\n\n**Done when:** {s.get('acceptance', '')}\n")
    if init.get("lld_path") and Path(init["lld_path"]).exists():
        parts.append("\n---\n\n" + Path(init["lld_path"]).read_text(encoding="utf-8"))
    out = d / "IDE_HANDOFF.md"
    out.write_text("".join(parts), encoding="utf-8")
    return out


# ---------------------------------------------------------------- work queues for agents

def queue(agent: str) -> dict:
    with db() as con:
        inits = rows(con, "SELECT * FROM initiatives WHERE stage NOT IN ('done','rejected') ORDER BY updated_at")
        projects = rows(con, "SELECT repo_name, priority, complexity, last_scanned_at, is_git, focus_by, focus_until "
                             "FROM projects WHERE priority != 'skip' ORDER BY CASE priority WHEN 'high' THEN 0 "
                             "WHEN 'medium' THEN 1 ELSE 2 END, COALESCE(last_scanned_at, '') ASC")
    focused = {p["repo_name"] for p in projects if active_focus(p)}
    spot = get_spotlight()
    by_project = {p["repo_name"]:p for p in projects}
    who = {"planner":"codex","scout":"gemma"}.get(agent,"claude")
    inits = [i for i in inits if not steering.eligibility(i, by_project.get(i["project_name"], {"priority":"skip"}),
             spot, now(), bool(handoffs_due(spot,who)), finishing(spot,i["id"]))]
    rank = {"high":0,"medium":1,"low":2,"skip":3}
    inits.sort(key=lambda i:(rank.get(by_project.get(i["project_name"],{}).get("priority"),3),
                            rank.get(i.get("priority"),1),i["updated_at"],i["id"]))
    projects = [{k: p[k] for k in ("repo_name", "priority", "complexity", "last_scanned_at", "is_git")}
                for p in projects if p["repo_name"] not in focused]
    def subtasks_for(who):
        out = []
        for i in inits:
            if i["stage"] != "building" or not i["execution_plan_json"]:
                continue
            subs = json.loads(i["execution_plan_json"]).get("subtasks", [])
            for s in subs:
                off_spot = spot and i["project_name"] != spot["project"]
                if off_spot and s["status"] != "doing":
                    continue  # graceful: only finish what was already in progress elsewhere
                if s["assignee"] == who and s["status"] in ("todo", "doing") and ready(s, subs):
                    item = {"initiative": i["id"], "project": i["project_name"], "worktree": i["worktree_path"],
                            "subtask": s}
                    if i["worktree_path"]:
                        item["new_files"] = [f for f in s.get("files", [])
                                             if not (Path(i["worktree_path"]) / f).exists()]
                    out.append(item)
        return out
    brief = lambda i: {k: i[k] for k in ("id", "project_name", "title", "stage", "complexity", "revision_note")}
    if agent == "scout":
        # One job per run: a 12B model does one narrow thing well, several things badly.
        due = handoffs_due(spot, "gemma")
        if due:
            return {"job": "handoff", **due[0], "spotlight": spot}
        subs = subtasks_for("gemma")
        if subs:
            return {"job": "subtask", **subs[0], "remaining": len(subs) - 1, "spotlight": spot}
        if spot:
            p = next((x for x in projects if x["repo_name"] == spot["project"]), None)
            fresh = p and p["last_scanned_at"] and p["last_scanned_at"] > (
                dt.datetime.now().astimezone() - dt.timedelta(hours=6)).isoformat(timespec="seconds")
            return {"job": "scan", "project": None if (not p or fresh) else p["repo_name"], "spotlight": spot}
        return {"job": "scan", "project": projects[0]["repo_name"] if projects else None}
    if agent in ("architect", "architect-high"):
        want_high = agent == "architect-high"
        hld = [brief(i) for i in inits if i["stage"] == "hld_draft" and (i["complexity"] == "high") == want_high]
        respark = [brief(i) for i in inits if i["stage"] == "spark" and i["revision_note"]]
        return {"spotlight": spot, "handoffs_due": handoffs_due(spot, "claude"), "hld_to_draft": hld, "sparks_needing_rework": respark if not want_high else [],
                "open_sparks": sum(1 for i in inits if i["stage"] == "spark"),
                "subtasks": subtasks_for("claude") if not want_high else []}
    if agent == "planner":
        lld = [brief(i) for i in inits if i["stage"] == "lld_draft"]
        review = []
        for i in inits:
            if i["stage"] != "building" or not i["execution_plan_json"]:
                continue
            plan = json.loads(i["execution_plan_json"])
            work = [s for s in plan["subtasks"] if s["assignee"] != "ide_handoff"]
            if work and all(s["status"] == "done" for s in work) and plan.get("review", {}).get("status") != "pass":
                review.append(brief(i))
        return {"spotlight": spot, "handoffs_due": handoffs_due(spot, "codex"), "lld_to_draft": lld, "branches_to_review": review, "subtasks": subtasks_for("codex")}
    raise OrchError("agent must be scout|architect|architect-high|planner")


# ---------------------------------------------------------------- model performance (feeds MODEL_NOTES.md)

def model_stats() -> dict:
    """Outcome counts per actor from the event log: what each model lane delivered and where it struggled."""
    with db() as con:
        ev = rows(con, "SELECT actor, kind, message FROM events")
    out: dict[str, dict] = {}
    for e in ev:
        a = out.setdefault(e["actor"], {})
        k = e["kind"]
        msg = e["message"] or ""
        if k == "subtask":
            k = "subtask_" + (msg.split("-> ", 1)[1].split(":", 1)[0].strip() if "-> " in msg else "?")
        elif k == "verify":
            k = "verify_pass" if "PASS" in msg else "verify_fail"
        elif k.startswith("stage:"):
            continue
        a[k] = a.get(k, 0) + 1
    return {actor: dict(sorted(c.items())) for actor, c in sorted(out.items())}


# ---------------------------------------------------------------- bootstrap

def init_all() -> dict:
    for d in (STATE, DOSSIERS, DESIGNS, WORKTREES, ORCH / "logs"):
        d.mkdir(parents=True, exist_ok=True)
    init_db()
    load_config()
    if not TASTE.exists():
        TASTE.write_text(TASTE_TEMPLATE, encoding="utf-8")
    added = seed_projects("init")
    export_json()
    return {"db": str(DB_PATH), "projects_added": added}


# ---------------------------------------------------------------- CLI

def _read_text(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    p = Path(arg)
    if not p.exists():
        raise OrchError(f"no such file: {arg}")
    return p.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="orch.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as", dest="actor", default=os.environ.get("ORCH_ACTOR", "cli"),
                    help="who is acting (scout-gemma, architect-claude, planner-codex, producer)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("lane-control")
    p.add_argument("declaration"); p.add_argument("--enabled",choices=("true","false"),required=True); p.add_argument("--expected",type=int,required=True)
    p = sp.add_parser("set-initiative")
    p.add_argument("id",type=int); p.add_argument("--priority",required=True); p.add_argument("--expected",required=True)
    p = sp.add_parser("reorder-subtasks")
    p.add_argument("id",type=int); p.add_argument("--order",required=True); p.add_argument("--expected",required=True)

    s = sp.add_parser("quota-snapshot", help="record manual Claude quota readings")
    s.add_argument("--provider", required=True, choices=["anthropic"])
    s.add_argument("--window", action="append", required=True, choices=["5h", "weekly"])
    s.add_argument("--used-pct", action="append", required=True)
    s.add_argument("--resets-at", action="append", required=True)
    sp.add_parser("init", help="create db, config, taste profile; register projects")
    s = sp.add_parser("sync-repos", help="clone org repos missing locally (never touches existing ones)")
    s.add_argument("--dry-run", action="store_true")
    s = sp.add_parser("projects", help="list projects")
    s.add_argument("--all", action="store_true", help="include priority=skip")
    s = sp.add_parser("set-project", help="update project fields")
    s.add_argument("repo")
    s.add_argument("pairs", nargs="+", metavar="field=value")
    s = sp.add_parser("scan", help="deterministic scan -> dossiers/<repo>/SCAN.json")
    s.add_argument("repo")
    s = sp.add_parser("smoke", help="run a safe headless test in a throwaway worktree -> SMOKE.json")
    s.add_argument("repo")
    s = sp.add_parser("write-dossier", help="write dossiers/<repo>/DOSSIER.md from a file or - for stdin")
    s.add_argument("repo")
    s.add_argument("file")
    s.add_argument("--playability", type=int)
    s.add_argument("--visual", type=int)
    s.add_argument("--bottleneck")
    s.add_argument("--optimization-notes")
    s = sp.add_parser("queue", help="what this agent should work on now")
    s.add_argument("agent", choices=["scout", "architect", "architect-high", "planner"])
    s = sp.add_parser("add-spark", help="pitch a new initiative")
    s.add_argument("--project", required=True, help="repo name or NEW_CONCEPT")
    s.add_argument("--category", required=True, choices=CATEGORIES)
    s.add_argument("--title", required=True)
    s.add_argument("--pitch", required=True, help="pitch text, or @file to read it from a file")
    s.add_argument("--complexity", choices=COMPLEXITIES)
    s = sp.add_parser("initiatives", help="list initiatives")
    s.add_argument("--stage", choices=STAGES)
    s = sp.add_parser("show", help="one initiative as JSON")
    s.add_argument("id", type=int)
    for kind in ("hld", "lld", "plan"):
        s = sp.add_parser(f"attach-{kind}", help=f"attach {kind.upper()} (file or -)")
        s.add_argument("id", type=int)
        s.add_argument("file")
        s.add_argument("--model")
    s = sp.add_parser("subtask", help="update a build subtask")
    s.add_argument("id", type=int)
    s.add_argument("sub", type=int)
    s.add_argument("status", choices=["todo", "doing", "done", "blocked"])
    s.add_argument("--note", default="")
    s = sp.add_parser("commit", help="commit all changes in the initiative's feat worktree (guarded)")
    s.add_argument("id", type=int)
    s.add_argument("-m", "--message", required=True)
    s.add_argument("--sub", type=int, help="subtask id (required for gemma)")
    s = sp.add_parser("verify", help="run a subtask's verify command in its worktree")
    s.add_argument("id", type=int)
    s.add_argument("sub", type=int)
    s = sp.add_parser("discard", help="discard uncommitted changes in the initiative's worktree")
    s.add_argument("id", type=int)
    s = sp.add_parser("escalate", help="hand a gemma subtask to a frontier model")
    s.add_argument("id", type=int)
    s.add_argument("sub", type=int)
    s.add_argument("--reason", required=True)
    s.add_argument("--to", choices=["codex", "claude", "ide_handoff"])
    s = sp.add_parser("guard", help="fail unless path is a feat/ worktree")
    s.add_argument("path", nargs="?", default=".")
    s = sp.add_parser("review", help="planner verdict on a building branch")
    s.add_argument("id", type=int)
    s.add_argument("verdict", choices=["pass", "fail"])
    s.add_argument("--note", required=True)
    s = sp.add_parser("diff", help="branch diff summary")
    s.add_argument("id", type=int)
    s = sp.add_parser("handoff", help="write IDE_HANDOFF.md for ide_handoff subtasks")
    s.add_argument("id", type=int)
    for name in ("advance", "revise", "reject"):
        s = sp.add_parser(name, help=f"producer control: {name}")
        s.add_argument("id", type=int)
        s.add_argument("--note", default="")
    s = sp.add_parser("rehome", help="attach a NEW_CONCEPT card to a repo")
    s.add_argument("id", type=int)
    s.add_argument("project")
    s = sp.add_parser("log", help="record agent activity")
    s.add_argument("message")
    s.add_argument("--project")
    s.add_argument("--initiative", type=int)
    sp.add_parser("export", help="rewrite PORTFOLIO_STATE.json")
    sp.add_parser("model-stats", help="outcome counts per agent/model lane (evidence for MODEL_NOTES.md)")
    s = sp.add_parser("inbox", help="what awaits the producer, what's in flight, what's claimed (for chat sessions)")
    s.add_argument("--md", action="store_true", help="markdown instead of JSON")
    s = sp.add_parser("claim", help="claim a card for an interactive session; agents will skip it")
    s.add_argument("id", type=int)
    s.add_argument("--hours", type=float, default=CLAIM_HOURS)
    s.add_argument("--note", default="")
    s = sp.add_parser("spotlight", help="point ALL scheduled agents at one project (optionally one aspect)")
    s.add_argument("repo", nargs="?")
    s.add_argument("--aspect", default="any", choices=sorted(ASPECTS))
    s.add_argument("--hours", type=float, default=0, help="0 or omitted = indefinite")
    s.add_argument("--mode", default="graceful", choices=["graceful", "forced"])
    s.add_argument("--note", default="")
    s.add_argument("--end", action="store_true", help="end the current spotlight")
    s = sp.add_parser("handoff-note", help="agents: document the state of work you are leaving (always allowed)")
    s.add_argument("id", type=int)
    s.add_argument("--note", required=True)
    s = sp.add_parser("reroute", help="producer/chat: change a subtask's assignee")
    s.add_argument("id", type=int)
    s.add_argument("sub", type=int)
    s.add_argument("to", choices=ASSIGNEES)
    s.add_argument("--note", default="")
    s = sp.add_parser("focus", help="start a frontier focus session on a whole project; agents stay out of it")
    s.add_argument("repo")
    s.add_argument("--hours", type=float, default=0, help="0 = indefinite")
    s.add_argument("--note", default="")
    s = sp.add_parser("unfocus", help="end a focus session; agents resume on the project")
    s.add_argument("repo")
    s.add_argument("--note", default="")
    s = sp.add_parser("release", help="release a claim so agents can pick the card up again")
    s.add_argument("id", type=int)
    s.add_argument("--note", default="")

    a = ap.parse_args(argv)
    actor = a.actor
    try:
        if a.cmd == "quota-snapshot":
            from utilization import Store
            try:
                store = Store(DB_PATH)
                store.initialize()
                out = store.quota_snapshot(a.provider, a.window, a.used_pct, a.resets_at)
            except (ValueError, TypeError, sqlite3.Error) as exc:
                raise OrchError(str(exc)) from exc
            print(json.dumps(out, indent=2))
            return 0
        if a.cmd != "init":
            init_all() if not DB_PATH.exists() else init_db()
        if a.cmd == "init":
            out = init_all()
        elif a.cmd == "sync-repos":
            out = {"cloned": sync_repos(a.dry_run), "dry_run": a.dry_run}
        elif a.cmd == "projects":
            with db() as con:
                sql = "SELECT repo_name, stack, priority, complexity, playability_score, visual_maturity, " \
                      "last_scanned_at, is_git FROM projects"
                out = rows(con, sql + ("" if a.all else " WHERE priority != 'skip'") + " ORDER BY repo_name")
        elif a.cmd == "lane-control":
            out = lane_control(a.declaration,a.enabled=="true",a.expected,actor)
        elif a.cmd == "set-initiative":
            out = set_initiative(a.id,a.priority,a.expected,actor)
        elif a.cmd == "reorder-subtasks":
            out = reorder_subtasks(a.id,json.loads(a.order),a.expected,actor)
        elif a.cmd == "set-project":
            out = update_project(a.repo, dict(p.split("=", 1) for p in a.pairs), actor)
        elif a.cmd == "scan":
            out = scan_project(a.repo)
        elif a.cmd == "smoke":
            out = smoke(a.repo, actor)
        elif a.cmd == "write-dossier":
            fields = {k: v for k, v in {"playability_score": a.playability, "visual_maturity": a.visual,
                                        "bottleneck_summary": a.bottleneck,
                                        "optimization_notes": a.optimization_notes}.items() if v is not None}
            out = {"path": str(write_dossier(a.repo, _read_text(a.file), actor, fields))}
        elif a.cmd == "queue":
            out = queue(a.agent)
        elif a.cmd == "add-spark":
            pitch = _read_text(a.pitch[1:]) if a.pitch.startswith("@") else a.pitch
            out = add_spark(a.project, a.category, a.title, pitch, actor, a.complexity)
        elif a.cmd == "initiatives":
            with db() as con:
                out = rows(con, "SELECT id, project_name, category, title, stage, complexity, branch_name, updated_at "
                                "FROM initiatives" + (" WHERE stage=?" if a.stage else "") + " ORDER BY id",
                           *([a.stage] if a.stage else []))
        elif a.cmd == "show":
            with db() as con:
                out = get_initiative(con, a.id)
            if out.get("execution_plan_json"):
                out["execution_plan_json"] = json.loads(out["execution_plan_json"])
        elif a.cmd.startswith("attach-"):
            out = attach(a.id, a.cmd.split("-", 1)[1], _read_text(a.file), actor, a.model)
        elif a.cmd == "subtask":
            out = subtask_update(a.id, a.sub, a.status, a.note, actor)
        elif a.cmd == "commit":
            out = {"sha": commit(a.id, a.message, actor, a.sub)}
        elif a.cmd == "verify":
            out = verify(a.id, a.sub, actor)
        elif a.cmd == "discard":
            out = discard(a.id, actor)
        elif a.cmd == "escalate":
            out = escalate(a.id, a.sub, a.reason, actor, a.to)
        elif a.cmd == "guard":
            out = guard(Path(a.path))
        elif a.cmd == "review":
            out = review_build(a.id, a.verdict, a.note, actor)
        elif a.cmd == "diff":
            with db() as con:
                out = diff_summary(get_initiative(con, a.id))
        elif a.cmd == "handoff":
            out = {"path": str(ide_handoff(a.id))}
        elif a.cmd == "advance":
            out = advance(a.id, actor, a.note)
            if _restart_after_ship:
                restart_dashboard()
        elif a.cmd == "revise":
            out = revise(a.id, a.note, actor)
        elif a.cmd == "reject":
            out = reject(a.id, a.note, actor)
        elif a.cmd == "rehome":
            out = rehome(a.id, a.project, actor)
        elif a.cmd == "log":
            with db(write=True) as con:
                log_event(con, actor, "note", a.message, a.project, a.initiative)
            out = {"ok": True}
        elif a.cmd == "inbox":
            out = inbox()
            if a.md:
                sys.stdout.reconfigure(encoding="utf-8")
                print(inbox_md(out))
                return 0
        elif a.cmd == "claim":
            out = claim(a.id, actor, a.hours, a.note)
        elif a.cmd == "release":
            out = release(a.id, actor, a.note)
        elif a.cmd == "spotlight":
            if a.end:
                out = end_spotlight(actor)
            elif a.repo:
                out = spotlight(a.repo, actor, a.aspect, a.hours, a.note, a.mode)
            else:
                out = {"spotlight": get_spotlight()}
        elif a.cmd == "handoff-note":
            out = handoff_note(a.id, a.note, actor)
        elif a.cmd == "reroute":
            out = reroute(a.id, a.sub, a.to, actor, a.note)
        elif a.cmd == "focus":
            out = focus(a.repo, actor, a.hours, a.note)
        elif a.cmd == "unfocus":
            out = unfocus(a.repo, actor, a.note)
        elif a.cmd == "model-stats":
            out = model_stats()
        elif a.cmd == "export":
            out = {"path": str(JSON_PATH), "initiatives": len(export_json()["initiatives"])}
        else:
            ap.error("unknown command")
            return 2
    except (OrchError, ValueError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, default=str))
    for t in _webhook_threads:  # CLI exits fast; let pending notifications finish
        t.join(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())


