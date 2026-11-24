"""Inspect the effective Docker context without reading or emitting data rows."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.public_revocation import content_not_revoked  # noqa: E402

BLOCKED_SUFFIXES = {
    ".csv",
    ".parquet",
    ".pbix",
    ".pbit",
    ".xls",
    ".xlsx",
    ".jsonl",
    ".ndjson",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".duckdb",
    ".zip",
    ".gz",
    ".tar",
    ".bundle",
    ".sarif",
    ".pdf",
    ".docx",
}
BLOCKED_DIRECTORIES = {".git", ".venv", "venv", "logs", "__pycache__"}
PENDING_REPORTS = {
    "docs/reports/data_dictionary.md",
    "docs/reports/data_quality_report.md",
    "docs/governance/lgpd_controls.md",
    "docs/governance/lgpd_ripd_sample.md",
}


def context_problems(root: Path) -> list[str]:
    """Fail closed; only explicit public synthetic-fixture grants allow data."""
    try:
        grants = json.loads(
            (root / "config/docker_fixture_authorizations.json").read_text()
        )
        if grants.get("version") != 1 or not isinstance(
            grants.get("authorizations"), list
        ):
            return ["Invalid fixture authorization registry."]
        manifest = json.loads((root / "config/public_visitor_content.json").read_text())
        blocked_hashes = {
            item["sha256"]
            for item in manifest["files"].values()
            if item.get("status") in {"Needs Review", "BLOCKED", "Blocked"}
        }
        for item in manifest["files"].values():
            if item.get("status") in {"Needs Review", "BLOCKED", "Blocked"}:
                previous = item.get("blocked_previous_sha256", [])
                if not isinstance(previous, list):
                    raise ValueError("Invalid historical report hashes.")
                blocked_hashes.update(previous)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ["Distribution authorization evidence is unavailable."]
    problems = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        if path.is_symlink():
            problems.append("Symlink in effective context.")
            continue
        if any(part.lower() in BLOCKED_DIRECTORIES for part in parts):
            problems.append("Internal directory in effective context.")
            continue
        if not path.is_file():
            continue
        basename = path.name.lower()
        if relative in PENDING_REPORTS or relative.startswith("docs/security/"):
            problems.append("Pending review evidence in effective context.")
            continue
        if (
            basename == "secrets.toml"
            or basename == ".env"
            or basename.startswith(".env.")
        ):
            problems.append("Credential file in effective context.")
            continue
        content = path.read_bytes()
        if not content_not_revoked(content, root=root, artifact=relative):
            problems.append("Revoked content or unavailable central revocation policy.")
            continue
        digest = hashlib.sha256(content).hexdigest()
        if digest in blocked_hashes:
            problems.append("Copy of pending report in effective context.")
            continue
        if (
            parts[0] == "data"
            or path.suffix.lower() in BLOCKED_SUFFIXES
            or basename.startswith(".sqlite")
        ):
            fixture = relative.startswith(("data/samples/", "tests/fixtures/"))
            authorized = fixture and any(
                isinstance(grant, dict)
                and grant.get("path") == relative
                and grant.get("sha256") == digest
                and grant.get("status") == "Approved"
                and grant.get("publication_authorized") is True
                and grant.get("audience") == "public"
                and grant.get("purpose") == "synthetic_test_fixture"
                for grant in grants["authorizations"]
            )
            if not authorized:
                problems.append(
                    "Data or binary artifact lacks synthetic-fixture authorization."
                )
    return problems


if __name__ == "__main__":
    failures = context_problems(Path(__file__).resolve().parents[1])
    if failures:
        raise SystemExit("FAIL: " + "; ".join(sorted(set(failures))))
    print("PASS: effective context excludes restricted data and pending reports.")
