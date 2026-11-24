from __future__ import annotations

import hashlib
import json

import pytest

from scripts.validate_docker_context import context_problems
from src.artifact_access import public_artifact_authorized
from src.public_content import read_public_content
from src.public_distribution_authorization import (
    REQUIRED_ARTIFACTS,
    public_demo_authorization_complete,
    public_distribution_artifact_authorized,
)
from src.public_revocation import public_downloads_enabled


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize(
    "state",
    [
        "valid",
        "absent",
        "malformed",
        "empty_override",
        "divergent",
        "revoked_hash",
        "revoked_path",
    ],
)
def test_central_policy_overrides_previously_approved_channel_manifests(
    tmp_path, monkeypatch, state
):
    policy = tmp_path / "shared-revocations.json"
    monkeypatch.setenv("GAP_PUBLIC_REVOCATIONS_PATH", str(policy))
    content = b"synthetic cross-channel test only"
    digest = hashlib.sha256(content).hexdigest()
    grant = {
        "sha256": digest,
        "status": "Approved",
        "publication_authorized": True,
        "audience": "public",
    }
    root = tmp_path / "visitor"
    document = root / "docs/approved.md"
    document.parent.mkdir(parents=True)
    document.write_bytes(content)
    manifest = root / "config/public_visitor_content.json"
    write_json(
        manifest,
        {"version": 1, "files": {"docs/approved.md": {**grant, "approved": True}}},
    )
    sidecar = tmp_path / "sidecar.json"
    write_json(sidecar, grant)
    demo = tmp_path / "demo"
    grants = []
    for name, purpose in REQUIRED_ARTIFACTS.items():
        path = demo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        grants.append({**grant, "file": name, "purpose": purpose})
    write_json(
        demo / "config/public_distribution_authorizations.json",
        {"version": 1, "authorizations": grants},
    )
    docker = tmp_path / "docker"
    fixture = docker / "tests/fixtures/synthetic.csv"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(content)
    write_json(
        docker / "config/public_visitor_content.json", {"version": 1, "files": {}}
    )
    write_json(
        docker / "config/docker_fixture_authorizations.json",
        {
            "version": 1,
            "authorizations": [
                {
                    **grant,
                    "path": "tests/fixtures/synthetic.csv",
                    "purpose": "synthetic_test_fixture",
                },
            ],
        },
    )
    approved_manifest_bytes = manifest.read_bytes()

    def channels():
        return [
            read_public_content(document, root=root, manifest=manifest) is not None,
            public_artifact_authorized(content, sidecar),
            public_demo_authorization_complete(demo),
            not context_problems(docker),
        ]

    write_json(policy, {"version": 1, "revoked_sha256": [], "revoked_artifacts": []})
    assert all(channels())
    if state == "absent":
        policy.unlink()
    elif state == "malformed":
        policy.write_text("invalid")
    elif state == "empty_override":
        monkeypatch.setenv("GAP_PUBLIC_REVOCATIONS_PATH", "")
    elif state == "divergent":
        document.write_bytes(b"changed")
        write_json(sidecar, {**grant, "sha256": "0" * 64})
        (demo / next(iter(REQUIRED_ARTIFACTS))).write_bytes(b"changed")
        fixture.write_bytes(b"changed")
    elif state == "revoked_hash":
        write_json(
            policy, {"version": 1, "revoked_sha256": [digest], "revoked_artifacts": []}
        )
    elif state == "revoked_path":
        write_json(
            policy,
            {
                "version": 1,
                "revoked_sha256": [],
                "revoked_artifacts": [
                    "docs/approved.md",
                    *REQUIRED_ARTIFACTS,
                    "tests/fixtures/synthetic.csv",
                ],
            },
        )
    assert channels() == [state == "valid"] * 4
    assert manifest.read_bytes() == approved_manifest_bytes


def test_public_profile_never_issues_reusable_download_urls(monkeypatch):
    monkeypatch.setenv("GAP_PUBLIC_DEMO_MODE", "true")
    assert not public_downloads_enabled()


@pytest.mark.parametrize(
    "state",
    [
        "valid",
        "missing",
        "wrong_hash",
        "wrong_purpose",
        "wrong_audience",
        "pending",
        "revoked",
        "missing_policy",
    ],
)
def test_demo_requires_only_exact_fixture_grant_not_historical_reports(
    tmp_path, monkeypatch, state
):
    name = "data/samples/gap_public_demo_synthetic_v1.parquet"
    assert REQUIRED_ARTIFACTS == {name: "synthetic_demo_preview"}
    fixture = tmp_path / name
    fixture.parent.mkdir(parents=True)
    content = b"synthetic authorization scope test bytes"
    fixture.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    grant = {
        "file": name,
        "sha256": digest,
        "purpose": "synthetic_demo_preview",
        "audience": "public",
        "status": "Approved",
        "publication_authorized": True,
    }
    if state == "wrong_hash":
        grant["sha256"] = "0" * 64
    elif state == "wrong_purpose":
        grant["purpose"] = "documentation_preview"
    elif state == "wrong_audience":
        grant["audience"] = "internal"
    elif state == "pending":
        grant["status"] = "Needs Review"
    write_json(
        tmp_path / "config/public_distribution_authorizations.json",
        {
            "version": 1,
            "authorizations": [] if state == "missing" else [grant],
        },
    )
    policy = tmp_path / "config/public_revocations.json"
    monkeypatch.setenv("GAP_PUBLIC_REVOCATIONS_PATH", str(policy))
    if state != "missing_policy":
        write_json(
            policy,
            {
                "version": 1,
                "revoked_artifacts": [],
                "revoked_sha256": [digest] if state == "revoked" else [],
            },
        )
    assert public_demo_authorization_complete(tmp_path) is (state == "valid")
    # No historical report bytes or approvals exist. Preview grants confer
    # neither document authorization, downloads nor Docker inclusion.
    assert not (tmp_path / "docs").exists()
    assert not public_distribution_artifact_authorized(
        tmp_path, name, "download", content
    )
    assert not public_distribution_artifact_authorized(
        tmp_path, name, "synthetic_test_fixture", content
    )
    document = tmp_path / "docs/reports/data_dictionary.md"
    document.parent.mkdir(parents=True)
    document.write_bytes(b"pending synthetic document test only")
    manifest = tmp_path / "config/public_visitor_content.json"
    write_json(
        manifest,
        {
            "version": 1,
            "files": {
                "docs/reports/data_dictionary.md": {
                    "status": "Needs Review",
                    "approved": False,
                    "audience": "review_pending",
                }
            },
        },
    )
    assert read_public_content(document, root=tmp_path, manifest=manifest) is None


def test_public_dataset_load_rechecks_exact_grant_and_revocation(tmp_path, monkeypatch):
    from scripts.generate_synthetic_public_demo import generate
    from src import data_loader

    name = "data/samples/gap_public_demo_synthetic_v1.parquet"
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    generate(20).to_parquet(path, index=False)
    original = path.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    monkeypatch.setattr(data_loader, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GAP_PUBLIC_DEMO_MODE", "true")
    policy = tmp_path / "config/public_revocations.json"
    monkeypatch.setenv("GAP_PUBLIC_REVOCATIONS_PATH", str(policy))
    write_json(policy, {"version": 1, "revoked_sha256": [], "revoked_artifacts": []})
    registry = tmp_path / "config/public_distribution_authorizations.json"
    write_json(registry, {"version": 1, "authorizations": []})
    with pytest.raises(PermissionError):
        data_loader.load_dataset(path)
    write_json(
        registry,
        {
            "version": 1,
            "authorizations": [
                {
                    "file": name,
                    "purpose": "synthetic_demo_preview",
                    "sha256": digest,
                    "audience": "public",
                    "status": "Approved",
                    "publication_authorized": True,
                }
            ],
        },
    )
    assert len(data_loader.load_dataset(path)) == 20
    path.write_bytes(b"divergent content")
    with pytest.raises(PermissionError):
        data_loader.load_dataset(path)
    path.write_bytes(original)
    write_json(
        policy, {"version": 1, "revoked_sha256": [digest], "revoked_artifacts": []}
    )
    with pytest.raises(PermissionError):
        data_loader.load_dataset(path)
