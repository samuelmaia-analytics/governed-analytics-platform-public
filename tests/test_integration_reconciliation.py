from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from scripts.generate_synthetic_public_demo import generate


def test_remote_context_metadata_survives_reconciliation(monkeypatch):
    import app.context as context

    monkeypatch.setattr(
        context, "load_dataset", lambda _: pd.DataFrame({"synthetic": [1]})
    )
    result = context._load_platform_dataframe(context.DEFAULT_PUBLISHED_DATASET)
    assert result.attrs["dataset_name"] == "fact_orders_dashboard"
    assert result.attrs["uses_persisted_governance"] is True


def test_remote_no_report_regeneration_survives_reconciliation(tmp_path, monkeypatch):
    import app.context as context
    import src.report_generator as reports

    monkeypatch.setattr(
        reports,
        "generate_markdown_reports",
        lambda *_a, **_k: pytest.fail("Report write"),
    )
    context._build_context_from_dataframe.clear()
    result = context._build_context_from_dataframe(
        generate(20),
        docs_dir=tmp_path / "reports",
        uses_persisted_governance=True,
    )
    assert result.report_paths
    assert not (tmp_path / "reports").exists()


def test_central_revocation_also_overrides_remote_context_bound_api(
    tmp_path, monkeypatch
):
    from src.artifact_access import artifact_authorized

    policy = tmp_path / "revocations.json"
    policy.write_text(
        json.dumps({"version": 1, "revoked_sha256": [], "revoked_artifacts": []})
    )
    monkeypatch.setenv("GAP_PUBLIC_REVOCATIONS_PATH", str(policy))
    content = b"synthetic remote-api test"
    context = {
        "dataset": "synthetic",
        "version": "v1",
        "purpose": "documentation_preview",
        "audience": "public",
    }
    grants = tmp_path / "approved.json"
    grants.write_text(
        json.dumps(
            {
                "authorizations": [
                    {
                        **context,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "status": "Approved",
                        "publication_authorized": True,
                    }
                ]
            }
        )
    )
    assert artifact_authorized(
        content, **context, publication_status="Approved", authorization_path=grants
    )
    before = grants.read_bytes()
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "revoked_sha256": [hashlib.sha256(content).hexdigest()],
                "revoked_artifacts": [],
            }
        )
    )
    assert not artifact_authorized(
        content, **context, publication_status="Approved", authorization_path=grants
    )
    assert grants.read_bytes() == before


def test_document_symlink_cannot_change_artifact_identity(tmp_path, monkeypatch):
    import src.artifact_access as access

    monkeypatch.setattr(access, "ROOT", tmp_path)
    monkeypatch.setattr(access, "artifact_authorized", lambda *_a, **_k: True)
    target = tmp_path / "target.md"
    target.write_text("synthetic")
    link = tmp_path / "alias.md"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Host does not allow symlinks")
    assert access.public_document_content(link) is None
