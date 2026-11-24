"""Explicit authorization for the exact bytes and context being delivered."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.public_revocation import content_not_revoked, public_downloads_enabled

ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATIONS_PATH = ROOT / "config" / "public_distribution.json"
PENDING_REPORTS = frozenset(
    {
        "docs/reports/data_dictionary.md",
        "docs/reports/data_quality_report.md",
        "docs/governance/lgpd_controls.md",
        "docs/governance/lgpd_ripd_sample.md",
    }
)


def artifact_authorized(
    content: bytes,
    *,
    dataset: str,
    version: str,
    purpose: str,
    audience: str,
    publication_status: str,
    authorization_path: Path = AUTHORIZATIONS_PATH,
) -> bool:
    if not content_not_revoked(content, root=ROOT, artifact=dataset):
        return False
    if publication_status != "Approved" or not all(
        isinstance(value, str) and value.strip()
        for value in (dataset, version, purpose, audience)
    ):
        return False
    expected = {
        "dataset": dataset,
        "version": version,
        "purpose": purpose,
        "audience": audience,
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    try:
        document = json.loads(authorization_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(document, dict):
        return False
    grants = document.get("authorizations", [])
    if not isinstance(grants, list):
        return False
    return any(
        isinstance(grant, dict)
        and grant.get("status") == "Approved"
        and grant.get("publication_authorized") is True
        and all(grant.get(key) == value for key, value in expected.items())
        for grant in grants
    )


def public_document_content(path: Path) -> str | None:
    try:
        relative_path = path.absolute().relative_to(ROOT.absolute())
        if ".." in relative_path.parts:
            return None
        current = ROOT
        for part in relative_path.parts:
            current = current / part
            if (
                current.is_symlink()
                or getattr(current.lstat(), "st_file_attributes", 0) & 0x400
            ):
                return None
        if not path.resolve().is_relative_to(ROOT.resolve()):
            return None
        relative = relative_path.as_posix()
        if relative in PENDING_REPORTS:
            return None
        content = path.read_bytes()
    except (OSError, ValueError):
        return None
    digest = hashlib.sha256(content).hexdigest()
    if not artifact_authorized(
        content,
        dataset=relative,
        version=digest,
        purpose="documentation_preview",
        audience="public",
        publication_status="Approved",
    ):
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def dataset_download(
    content: bytes,
    *,
    dataset: str,
    version: str,
    risk_recommendation: str,
    uses_persisted_governance: bool,
    decision_path: Path | None = None,
    authorization_path: Path = AUTHORIZATIONS_PATH,
) -> bytes | None:
    if not public_downloads_enabled():
        return None
    if risk_recommendation != "approved":
        return None
    if uses_persisted_governance:
        decision_path = decision_path or (
            ROOT / "data/published/monitoring/publication_decision.json"
        )
        try:
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if (
            not isinstance(decision, dict)
            or decision.get("dataset") != dataset
            or decision.get("status") != "Approved"
        ):
            return None
    if not artifact_authorized(
        content,
        dataset=dataset,
        version=version,
        purpose="protected_dataset_download",
        audience="public",
        publication_status="Approved",
        authorization_path=authorization_path,
    ):
        return None
    return content


def public_artifact_authorized(content: bytes, authorization_path: Path) -> bool:
    """Require a reviewed sidecar matching the exact bytes being delivered."""
    try:
        authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(authorization, dict)
        and authorization.get("audience") == "public"
        and authorization.get("publication_authorized") is True
        and authorization.get("status") == "Approved"
        and authorization.get("sha256") == hashlib.sha256(content).hexdigest()
        and content_not_revoked(content)
    )
