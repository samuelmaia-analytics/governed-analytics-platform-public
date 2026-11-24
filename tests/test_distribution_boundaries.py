from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.validate_docker_context import context_problems

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def context(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/public_revocations.json").write_text(
        json.dumps(
            {
                "version": 1,
                "revoked_sha256": [],
                "revoked_artifacts": [],
            }
        )
    )
    (tmp_path / "config/docker_fixture_authorizations.json").write_text(
        json.dumps({"version": 1, "authorizations": []})
    )
    (tmp_path / "config/public_visitor_content.json").write_text(
        json.dumps(
            {
                "files": {
                    "docs/pending.md": {
                        "status": "Needs Review",
                        "sha256": hashlib.sha256(b"pending").hexdigest(),
                    }
                }
            }
        )
    )
    return tmp_path


@pytest.mark.parametrize(
    "name",
    [
        "nested/result.CSV",
        "nested/result.PARQUET",
        "nested/report.PBIX",
        "nested/findings.SARIF",
        "nested/package.zip",
        "nested/cv.pdf",
        "nested/private.DOCX",
        "nested/.env.production",
        "nested/secrets.toml",
        "logs/event.txt",
        "data/published/renamed.txt",
        "docs/governance/lgpd_controls.md",
    ],
)
def test_effective_context_rejects_nested_data_and_evidence(context, name):
    path = context / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic")
    assert context_problems(context)


def test_pending_report_copy_is_blocked_even_after_renaming(context):
    (context / "innocent.txt").write_bytes(b"pending")
    assert context_problems(context)


def test_old_pending_report_hash_remains_blocked_after_review_edits(context):
    manifest = context / "config/public_visitor_content.json"
    payload = json.loads(manifest.read_text())
    entry = payload["files"]["docs/pending.md"]
    entry["blocked_previous_sha256"] = [entry["sha256"]]
    entry["sha256"] = hashlib.sha256(b"reviewed annotation, still pending").hexdigest()
    manifest.write_text(json.dumps(payload))
    (context / "renamed_previous_version.txt").write_bytes(b"pending")
    assert context_problems(context)


def test_fixture_requires_exact_public_grant_and_supports_revocation(context):
    path = context / "tests/fixtures/synthetic.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"value\n1\n")
    assert context_problems(context)
    grant = {
        "path": path.relative_to(context).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": "Approved",
        "publication_authorized": True,
        "audience": "public",
        "purpose": "synthetic_test_fixture",
    }
    registry = context / "config/docker_fixture_authorizations.json"
    registry.write_text(json.dumps({"version": 1, "authorizations": [grant]}))
    assert context_problems(context) == []
    path.write_bytes(b"changed\n")
    assert context_problems(context)
    path.write_bytes(b"value\n1\n")
    grant["publication_authorized"] = False
    registry.write_text(json.dumps({"version": 1, "authorizations": [grant]}))
    assert context_problems(context)


def test_malformed_authorization_fails_closed(context):
    registry = context / "config/docker_fixture_authorizations.json"
    registry.write_text("null")
    assert context_problems(context)
    registry.unlink()
    assert context_problems(context)


def test_operational_workflows_are_absent_in_public_candidate():
    # The public candidate must not ship operational workflows.
    for filename in (
        "deploy-streamlit.yml",
        "operate-published-layer.yml",
        "sync-dadosfera-catalog.yml",
    ):
        assert not (ROOT / ".github/workflows" / filename).exists()


def test_implicit_uploaders_cannot_publish_findings_or_coverage():
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                action = step.get("uses", "")
                if "actions/setup-python@" in action:
                    assert not step.get("with", {}).get("cache")
                if "codecov/codecov-action@" in action:
                    assert step.get("if") == "${{ false }}"
                if "gitleaks/gitleaks-action@" in action:
                    assert all(
                        step["env"][key] == "false"
                        for key in (
                            "GITLEAKS_ENABLE_UPLOAD_ARTIFACT",
                            "GITLEAKS_ENABLE_COMMENTS",
                            "GITLEAKS_ENABLE_SUMMARY",
                        )
                    )


def test_security_audits_fail_the_workflow_instead_of_masking_findings():
    workflow = yaml.load(
        (ROOT / ".github/workflows/security.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["security-checks"]["steps"]
    audits = [
        s
        for s in steps
        if "audit" in s.get("name", "").lower()
        or "secret scan" in s.get("name", "").lower()
    ]
    assert len(audits) == 2
    assert all(s.get("continue-on-error", "false") == "false" for s in audits)


def test_operational_workflows_are_not_referenced_by_required_jobs():
    # The remaining workflows must not reference deployment/ops workflows.
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "operate-published-layer.yml" not in text
        assert "deploy-streamlit.yml" not in text
        assert "sync-dadosfera-catalog.yml" not in text


def test_required_pr_jobs_remain_enabled():
    expected = {
        "ci.yml": "test",
        "security.yml": "security-checks",
        "lint.yml": "ruff",
        "policy-check.yml": "governance-policy",
        "publication-safety.yml": "publication-safety",
    }
    for filename, job_name in expected.items():
        workflow = yaml.load(
            (ROOT / ".github/workflows" / filename).read_text(),
            Loader=yaml.BaseLoader,
        )
        assert "pull_request" in workflow["on"]
        assert "if" not in workflow["jobs"][job_name]


@pytest.mark.parametrize(
    "filename",
    [
        "ci.yml",
        "lint.yml",
        "policy-check.yml",
        "publication-safety.yml",
        "security.yml",
    ],
)
def test_source_is_checked_before_installing_dependencies(filename):
    workflow = yaml.load(
        (ROOT / ".github/workflows" / filename).read_text(),
        Loader=yaml.BaseLoader,
    )
    for job in workflow["jobs"].values():
        steps = job.get("steps", [])
        names = [step.get("name") for step in steps]
        if "Install dependencies" in names:
            assert names.index("Check source distribution") < names.index(
                "Install dependencies"
            )
