from __future__ import annotations

import hashlib
import json
import subprocess
from functools import partial

import pandas as pd
import pytest

from app.pages import lgpd_privacy_risk as page
from src.artifact_access import artifact_authorized, dataset_download
from src.repository_publication import publication_problems, snapshot_problems
from src.schema_contract_components.discovery import load_dataset


@pytest.fixture
def authorization(tmp_path):
    content = b"metric\n1\n"
    context = {
        "dataset": "synthetic_test",
        "version": hashlib.sha256(b"synthetic-source").hexdigest(),
        "purpose": "protected_dataset_download",
        "audience": "public",
    }
    grant = {
        **context,
        "sha256": hashlib.sha256(content).hexdigest(),
        "status": "Approved",
        "publication_authorized": True,
    }
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps({"authorizations": [grant]}))
    return content, context, grant, path


@pytest.mark.parametrize(
    "field",
    [
        "dataset",
        "version",
        "purpose",
        "audience",
        "sha256",
        "status",
        "publication_authorized",
    ],
)
def test_every_authorization_field_is_required(authorization, field):
    content, context, grant, path = authorization
    assert artifact_authorized(
        content, **context, publication_status="Approved", authorization_path=path
    )
    grant.pop(field)
    path.write_text(json.dumps({"authorizations": [grant]}))
    assert not artifact_authorized(
        content, **context, publication_status="Approved", authorization_path=path
    )


def test_modified_bytes_and_context_are_denied(authorization):
    content, context, _grant, path = authorization
    assert not artifact_authorized(
        content + b"2\n",
        **context,
        publication_status="Approved",
        authorization_path=path,
    )
    for field in ("dataset", "version", "purpose", "audience"):
        changed = {**context, field: "different"}
        assert not artifact_authorized(
            content, **changed, publication_status="Approved", authorization_path=path
        )
    for status in ("Needs Review", "BLOCKED", "Blocked"):
        assert not artifact_authorized(
            content, **context, publication_status=status, authorization_path=path
        )


@pytest.mark.parametrize(
    "document", ['{"authorizations": null}', "[]", "{", '{"authorizations": [true]}']
)
def test_malformed_authorization_fails_closed(authorization, document):
    content, context, _grant, path = authorization
    path.write_text(document)
    assert not artifact_authorized(
        content, **context, publication_status="Approved", authorization_path=path
    )


def test_download_keeps_gate_and_risk_controls(authorization, tmp_path):
    content, context, _grant, path = authorization
    options = {
        "dataset": context["dataset"],
        "version": context["version"],
        "risk_recommendation": "approved",
        "uses_persisted_governance": True,
        "decision_path": tmp_path / "decision.json",
        "authorization_path": path,
    }
    assert dataset_download(content, **options) is None
    for status in ("Needs Review", "BLOCKED"):
        options["decision_path"].write_text(
            json.dumps({"dataset": context["dataset"], "status": status})
        )
        assert dataset_download(content, **options) is None
    options["decision_path"].write_text(
        json.dumps({"dataset": context["dataset"], "status": "Approved"})
    )
    assert dataset_download(content, **options) == content
    assert (
        dataset_download(content, **{**options, "risk_recommendation": "needs_review"})
        is None
    )
    options["decision_path"].write_text(
        json.dumps({"dataset": "another_dataset", "status": "Approved"})
    )
    assert dataset_download(content, **options) is None


def test_index_catches_forced_data_and_renamed_content(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "core.longpaths", "true"], check=True
    )
    restricted = b"synthetic restricted fixture"
    policy = {
        "excluded_files": [
            {"path": "private.txt", "sha256": hashlib.sha256(restricted).hexdigest()}
        ],
        "restricted_git_blobs": [],
    }
    (tmp_path / "config").mkdir()
    (tmp_path / "config/distribution_inventory.json").write_text(json.dumps(policy))
    (tmp_path / ".gitignore").write_text("generated.csv\n")
    (tmp_path / "source.py").write_text("pass\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    assert publication_problems(tmp_path, ":index") == []
    (tmp_path / "generated.csv").write_text("metric\n1\n")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "-f", "generated.csv"], check=True
    )
    assert any(
        "generated.csv" in item for item in publication_problems(tmp_path, ":index")
    )
    (tmp_path / "renamed.txt").write_bytes(restricted)
    subprocess.run(["git", "-C", str(tmp_path), "add", "renamed.txt"], check=True)
    assert any(
        "Unauthorized content copy" in item
        for item in publication_problems(tmp_path, ":index")
    )


def test_symlinks_and_submodules_are_not_distributed():
    inventory = json.dumps({"excluded_files": [], "restricted_git_blobs": []}).encode()
    files = {"config/distribution_inventory.json": inventory}
    modes = {
        "config/distribution_inventory.json": "100644",
        "link": "120000",
        "module": "160000",
    }
    assert len(snapshot_problems(files, modes)) == 2


def test_legacy_fixture_metadata_cannot_authorize_csv_or_renamed_copy():
    content = b"metric\n1\n"
    name = "tests/fixtures/synthetic.csv"
    policy = {
        "excluded_files": [],
        "restricted_git_blobs": [],
        "synthetic_test_fixtures": {
            name: {"sha256": hashlib.sha256(content).hexdigest()}
        },
    }
    files = {
        "config/distribution_inventory.json": json.dumps(policy).encode(),
        name: content,
    }
    modes = {path: "100644" for path in files}
    assert any(
        "Unauthorized distribution path" in p for p in snapshot_problems(files, modes)
    )
    files["renamed.txt"] = files.pop(name)
    modes["renamed.txt"] = modes.pop(name)
    assert any(
        "Unauthorized content copy" in problem
        for problem in snapshot_problems(files, modes)
    )


@pytest.mark.parametrize(
    "name",
    [
        "high_lgpd_risk_dataset.csv",
        "invalid_missing_customer_id.csv",
        "invalid_schema_change.csv",
        "privacy_governance_synthetic_4_pass_12_fail.csv",
        "valid_dataset.csv",
    ],
)
def test_force_staged_legacy_csv_is_rejected(tmp_path, name):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "core.longpaths", "true"], check=True
    )
    relative = f"tests/fixtures/{name}"
    content = b"synthetic_metric\n7\n"
    policy = {
        "excluded_files": [],
        "restricted_git_blobs": [],
        "synthetic_test_fixtures": {
            relative: {"sha256": hashlib.sha256(content).hexdigest()}
        },
    }
    (tmp_path / "config").mkdir()
    (tmp_path / "tests/fixtures").mkdir(parents=True)
    (tmp_path / "config/distribution_inventory.json").write_text(json.dumps(policy))
    (tmp_path / ".gitignore").write_text(relative + "\n")
    (tmp_path / relative).write_bytes(content)
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "config", ".gitignore"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", relative], check=True)
    assert any(
        f"Unauthorized distribution path: {relative}" in problem
        for problem in publication_problems(tmp_path, ":index")
    )


def test_csv_contract_parses_dates_without_accepting_invalid_values(tmp_path):
    path = tmp_path / "output.csv"
    path.write_text("when,amount\n2024-01-01,1\n")
    contract = {
        "path": "output.csv",
        "columns": {"when": "datetime", "amount": "integer"},
    }
    assert pd.api.types.is_datetime64_any_dtype(
        load_dataset(contract, root_dir=tmp_path)["when"]
    )
    path.write_text("when,amount\ninvalid,1\n")
    assert not pd.api.types.is_datetime64_any_dtype(
        load_dataset(contract, root_dir=tmp_path)["when"]
    )
    path.unlink()
    with pytest.raises(FileNotFoundError):
        load_dataset(contract, root_dir=tmp_path)


def test_pending_reports_are_hidden_even_with_a_matching_grant(tmp_path, monkeypatch):
    import src.artifact_access as access

    monkeypatch.setattr(access, "ROOT", tmp_path)
    path = tmp_path / "docs/reports/data_dictionary.md"
    path.parent.mkdir(parents=True)
    path.write_text("synthetic pending evidence")
    # A pending report remains excluded until the explicit human review is resolved.
    monkeypatch.setattr(access, "artifact_authorized", lambda *_args, **_kwargs: True)
    assert access.public_document_content(path) is None


def test_default_sample_fallback_is_synthetic_and_writes_nothing(tmp_path, monkeypatch):
    import src.data_loader as loader

    monkeypatch.setattr(loader, "DEFAULT_SAMPLE_DATASET", tmp_path / "absent.csv")
    first = loader.load_dataset()
    assert first.equals(loader.load_dataset())
    assert first["order_id"].str.startswith("demo-").all()
    assert not list(tmp_path.iterdir())


class Capture:
    def __init__(self):
        self.downloads = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None

    def tabs(self, names):
        return [self for _ in names]

    def columns(self, count):
        return [self for _ in range(count)]

    def download_button(self, **kwargs):
        self.downloads.append(kwargs["data"])


def test_normal_page_download_uses_exact_authorized_bytes(tmp_path, monkeypatch):
    capture = Capture()
    monkeypatch.setattr(page, "st", capture)
    path = tmp_path / "authorization.json"
    path.write_text('{"authorizations":[]}')
    monkeypatch.setattr(
        page, "dataset_download", partial(dataset_download, authorization_path=path)
    )
    df = pd.DataFrame({"metric": [1]})
    classification = pd.DataFrame(
        {"column_name": ["metric"], "lgpd_classification": ["non_personal"]}
    )
    monkeypatch.setattr(
        page, "apply_privacy_actions", lambda *_: (df.copy(), pd.DataFrame())
    )
    risk = {
        "score": 0,
        "risk_level": "low",
        "publication_recommendation": "approved",
        "recommendations": [],
    }
    page.render_lgpd_privacy_risk(df, classification, risk, "en-US")
    assert capture.downloads == []
    content = df.to_csv(index=False).encode()
    grant = {
        "dataset": "governance_preview",
        "version": hashlib.sha256(content).hexdigest(),
        "purpose": "protected_dataset_download",
        "audience": "public",
        "sha256": hashlib.sha256(content).hexdigest(),
        "status": "Approved",
        "publication_authorized": True,
    }
    path.write_text(json.dumps({"authorizations": [grant]}))
    page.render_lgpd_privacy_risk(df, classification, risk, "en-US")
    assert capture.downloads == [content]


@pytest.mark.parametrize("name", ["data/quarantine/build-run.json", "src/renamed.json"])
def test_quarantine_journal_is_blocked_from_public_distribution(name):
    content = b'{"kind":"olist_rejection_journal","publication_authorized":false}'
    problems = snapshot_problems(
        {"config/distribution_inventory.json": b"{}", name: content},
        {name: "100644"},
        policy={"excluded_files": [], "restricted_git_blobs": []},
    )
    assert any(name in problem for problem in problems)
