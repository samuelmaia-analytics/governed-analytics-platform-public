"""Uncached, deny-first revocation shared by every public delivery channel.

Revocation prevents new authorizations. It cannot recall bytes already delivered.
Public containers require an externally mounted policy to avoid a stale image copy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

from src.public_mode import is_public_visitor_mode

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def public_downloads_enabled() -> bool:
    """Do not issue reusable Streamlit media URLs in the public container."""
    return not is_public_visitor_mode()


def content_not_revoked(
    content: bytes,
    *,
    root: Path = PROJECT_ROOT,
    artifact: str | None = None,
) -> bool:
    try:
        override = os.environ.get("GAP_PUBLIC_REVOCATIONS_PATH")
        if override is not None and not override.strip():
            return False
        policy_path = (
            Path(override) if override else root / "config/public_revocations.json"
        )
        return policy_allows(policy_path.read_bytes(), content, artifact=artifact)
    except OSError:
        return False


def policy_allows(policy_bytes: bytes, content: bytes, *, artifact: str | None) -> bool:
    """Evaluate exact policy bytes from a delivery snapshot."""
    try:
        policy = json.loads(policy_bytes.decode("utf-8"))
        if policy.get("version") != 1:
            return False
        hashes = policy.get("revoked_sha256")
        paths = policy.get("revoked_artifacts")
        if not isinstance(hashes, list) or not isinstance(paths, list):
            return False
        if any(
            not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h)
            for h in hashes
        ):
            return False
        if any(
            not isinstance(p, str)
            or not p
            or p.startswith("/")
            or "\\" in p
            or ".." in PurePosixPath(p).parts
            or PurePosixPath(p).as_posix() != p
            or any(character in p for character in "\x00*?[]")
            for p in paths
        ):
            return False
        return hashlib.sha256(content).hexdigest() not in hashes and (
            artifact not in paths if artifact is not None else not paths
        )
    except (ValueError, TypeError, AttributeError):
        return False
