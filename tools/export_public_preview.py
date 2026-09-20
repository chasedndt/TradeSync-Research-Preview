"""Export a history-free TradeSync public research-preview candidate.

The export includes the current tracked and non-ignored working-tree files,
not Git objects or ignored runtime material. It never overwrites a non-empty
destination. Publication and remote-repository creation remain separate,
approval-gated actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from public_release_audit import ROOT, audit, candidate_files


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    destination = args.destination.resolve()

    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty destination: {destination}")
    if audit(ROOT) != 0:
        raise SystemExit("Source tree failed the public-release audit; export refused.")

    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for relative in candidate_files(ROOT):
        source = ROOT / relative
        if not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative.replace("\\", "/"))

    manifest = {
        "schema_version": "tradesync_public_preview_export_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": git_value("rev-parse", "HEAD"),
        "source_worktree_dirty": bool(git_value("status", "--porcelain")),
        "history_included": False,
        "licence": "FSL-1.1-MIT",
        "file_count_before_manifest": len(copied),
        "files": [
            {"path": relative, "sha256": sha256(destination / relative)}
            for relative in copied
        ],
    }
    manifest_path = destination / "PUBLIC_EXPORT_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if audit(destination) != 0:
        raise SystemExit("Exported tree failed the public-release audit.")
    print(f"Exported {len(copied)} files plus manifest to {destination}")
    print("Git history was not included; no remote repository was created or changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
