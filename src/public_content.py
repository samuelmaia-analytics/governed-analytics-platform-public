"""Read only explicitly reviewed visitor content, checking its current bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.public_revocation import content_not_revoked

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "config/public_visitor_content.json"
ALLOWED_SUFFIXES = {".md", ".svg", ".png", ".drawio", ".json"}


def public_entries(manifest: Path = MANIFEST_PATH) -> dict[str, dict]:
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("version") != 1 or not isinstance(payload.get("files"), dict):
            return {}
        return payload["files"]
    except (OSError, ValueError, AttributeError):
        return {}


def read_public_content(
    path: Path, *, root: Path = PROJECT_ROOT, manifest: Path = MANIFEST_PATH
) -> bytes | None:
    """Fail closed for unlisted, modified, restricted or redirected files."""
    try:
        relative = path.absolute().relative_to(root.absolute())
        if (
            not relative.parts
            or ".." in relative.parts
            or path.suffix.lower() not in ALLOWED_SUFFIXES
        ):
            return None
        if relative.parts[0] not in {"docs", "workflows"}:
            return None
        current = root
        for part in relative.parts:
            current = current / part
            if (
                current.is_symlink()
                or getattr(current.lstat(), "st_file_attributes", 0) & 0x400
            ):
                return None
        if not path.resolve().is_relative_to(root.resolve()):
            return None
        entry = public_entries(manifest).get(relative.as_posix(), {})
        if not isinstance(entry, dict) or (
            entry.get("audience") != "public"
            or entry.get("approved") is not True
            or entry.get("status") != "Approved"
        ):
            return None
        content = path.read_bytes()
        if not content_not_revoked(content, root=root, artifact=relative.as_posix()):
            return None
        if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
            return None
        return content
    except (OSError, ValueError):
        return None


def approved_markdown_files(
    root: Path = PROJECT_ROOT, manifest: Path = MANIFEST_PATH
) -> list[Path]:
    paths = [
        root / name
        for name in public_entries(manifest)
        if name.startswith("docs/") and name.endswith(".md")
    ]
    return sorted(
        (
            path
            for path in paths
            if read_public_content(path, root=root, manifest=manifest) is not None
        ),
        key=lambda path: path.as_posix().lower(),
    )
