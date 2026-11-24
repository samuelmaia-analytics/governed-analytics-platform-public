"""Verify public grants independently from technical dataset quality."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.public_revocation import content_not_revoked

REQUIRED_ARTIFACTS = {
    # Demo renders the synthetic dataframe, not historical report documents.
    # Those remain independently governed by their visitor-content grants.
    "data/samples/gap_public_demo_synthetic_v1.parquet": "synthetic_demo_preview",
}


def public_distribution_artifact_authorized(
    root: Path,
    name: str,
    purpose: str,
    content: bytes,
) -> bool:
    try:
        registry = json.loads(
            (root / "config/public_distribution_authorizations.json").read_text()
        )
        if registry.get("version") != 1 or not isinstance(
            registry.get("authorizations"), list
        ):
            return False
        digest = hashlib.sha256(content).hexdigest()
        return content_not_revoked(content, root=root, artifact=name) and any(
            isinstance(grant, dict)
            and grant.get("file") == name
            and grant.get("sha256") == digest
            and grant.get("purpose") == purpose
            and grant.get("audience") == "public"
            and grant.get("status") == "Approved"
            and grant.get("publication_authorized") is True
            for grant in registry["authorizations"]
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def public_demo_authorization_complete(root: Path) -> bool:
    try:
        registry = json.loads(
            (root / "config/public_distribution_authorizations.json").read_text(
                encoding="utf-8"
            )
        )
        if registry.get("version") != 1 or not isinstance(
            registry.get("authorizations"), list
        ):
            return False
        for name, purpose in REQUIRED_ARTIFACTS.items():
            grants = [
                grant
                for grant in registry["authorizations"]
                if isinstance(grant, dict)
                and grant.get("file") == name
                and grant.get("purpose") == purpose
                and grant.get("audience") == "public"
                and grant.get("status") == "Approved"
                and grant.get("publication_authorized") is True
            ]
            if not grants:
                return False
            current = root
            for part in Path(name).parts:
                current = current / part
                if (
                    current.is_symlink()
                    or getattr(current.lstat(), "st_file_attributes", 0) & 0x400
                ):
                    return False
            content = current.read_bytes()
            if not content_not_revoked(content, root=root, artifact=name):
                return False
            digest = hashlib.sha256(content).hexdigest()
            if not any(grant.get("sha256") == digest for grant in grants):
                return False
        return True
    except (OSError, ValueError, TypeError, AttributeError):
        return False
