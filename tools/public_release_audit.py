"""Fail a public-source check on likely committed credentials or secret files.

This is deliberately narrow. It is a release-hygiene guard, not a substitute
for GitHub secret scanning, history review, dependency scanning or legal review.
Only file names and line numbers are printed; matched values are never emitted.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PROHIBITED_PATHS = (
    re.compile(r"(^|/)\.env$", re.IGNORECASE),
    re.compile(r"\.(pem|key|p12|pfx|keystore)$", re.IGNORECASE),
    re.compile(r"(^|/)(credentials\.json|secrets?/)", re.IGNORECASE),
)

PROHIBITED_DATA_PREFIXES = (
    "data/replay/real_trade_data/",
    "data/replay/calibration/",
    "data/reports/calibration/",
    "data/reports/golden_reports/real_trade_data/",
    "data/reports/phase3D/real_",
)

SIGNATURES = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "slack_token": re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
    "discord_webhook": re.compile(
        r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+"
    ),
}

PRIVATE_INSTALLATION_MARKERS = (
    "C:" + "\\Users\\" + "chase" + "os",
    "C:/Users/" + "chase" + "os",
    "/mnt/c/Users/" + "chase" + "os",
    "/home/" + "chase" + "os",
    "chaseos_" + "chaseintech",
    "chaseos_" + "obsidian",
)

# These files exercise redaction with inert, fabricated values.
FIXTURE_EXCEPTIONS = {
    "services/state-api/tests/test_fleet_activity.py",
    "tests/test_job_errors.py",
}


def candidate_files(root: Path) -> list[str]:
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )


def audit(root: Path) -> int:
    failures: list[tuple[str, int, str]] = []
    warnings: list[str] = []
    files = candidate_files(root)

    for relative in files:
        normalized = relative.replace("\\", "/")
        if any(pattern.search(normalized) for pattern in PROHIBITED_PATHS):
            failures.append((normalized, 0, "prohibited_secret_path"))
            continue
        if any(normalized.startswith(prefix) for prefix in PROHIBITED_DATA_PREFIXES):
            failures.append((normalized, 0, "captured_or_derived_provider_data"))
            continue

        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        if any(marker in text for marker in PRIVATE_INSTALLATION_MARKERS):
            failures.append((normalized, 0, "operator_specific_path"))

        if normalized in FIXTURE_EXCEPTIONS:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in SIGNATURES.items():
                if pattern.search(line):
                    failures.append((normalized, line_number, label))

    for path, line, label in failures:
        suffix = f":{line}" if line else ""
        print(f"FAIL {label}: {path}{suffix}")
    for warning in sorted(set(warnings)):
        print(f"WARN {warning}")

    if failures:
        print(f"Public-release audit failed: {len(failures)} blocking item(s).")
        return 1
    print(
        f"Public-release credential audit passed for {len(files)} tracked files; "
        f"{len(set(warnings))} non-secret release warning(s)."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a TradeSync public-source tree.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository or exported tree to scan")
    args = parser.parse_args()
    return audit(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
