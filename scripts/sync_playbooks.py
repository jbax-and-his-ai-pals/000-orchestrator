"""Keep agent playbooks under version control.

OpenClaw's agent workspaces (agents/<name>/) contain their own .git, so the orchestrator repo can't track files
inside them. `playbooks/<name>/` is the tracked copy.

    python scripts/sync_playbooks.py          # export: workspaces -> playbooks/ (run by the pre-commit hook)
    python scripts/sync_playbooks.py --install  # install: playbooks/ -> workspaces (after a fresh clone)
"""
import shutil
import sys
from pathlib import Path

ORCH = Path(__file__).resolve().parents[1]
FILES = ("AGENTS.md", "IDENTITY.md", "SOUL.md", "USER.md", "orch.cmd", "DOSSIER_TEMPLATE.md")


def main() -> int:
    install = "--install" in sys.argv
    src_root, dst_root = (ORCH / "playbooks", ORCH / "agents") if install else (ORCH / "agents", ORCH / "playbooks")
    n = 0
    for agent in sorted(p for p in src_root.iterdir() if p.is_dir()) if src_root.exists() else []:
        for f in FILES:
            src = agent / f
            if src.exists():
                dst = dst_root / agent.name / f
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists() or dst.read_bytes() != src.read_bytes():
                    shutil.copy2(src, dst)
                    n += 1
    print(f"{'installed' if install else 'exported'} {n} changed file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
