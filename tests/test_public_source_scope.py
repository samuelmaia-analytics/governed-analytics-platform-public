import hashlib
import json

import pytest

from scripts.build_public_distribution import _selection, public_snapshot
from src.repository_publication import INVENTORY, PUBLIC_POLICY, snapshot_problems


def source_files():
    document = b"Reviewed technical architecture\n"
    digest = hashlib.sha256(document).hexdigest()
    name = "docs/architecture/demo.md"
    scope = {
        "repository": "samuelmaia-analytics/Governed-Analytics-Platform",
        "documents": {name: digest},
        "assets": {},
        "private_test_modules": ["tests/test_private.py"],
        "public_tests": ["tests/test_public.py"],
        "data_metadata": [],
        "root_files": ["README.md"],
        "code_prefixes": ["src/", "tests/", "config/"],
        "readme_source": name,
    }
    grant = {
        "dataset": name,
        "version": digest,
        "sha256": digest,
        "purpose": "documentation_preview",
        "audience": "public",
        "status": "Approved",
        "publication_authorized": True,
    }
    registry = {"repository": scope["repository"], "authorizations": [grant]}
    return {
        "config/public_scope.json": json.dumps(scope).encode(),
        "config/public_distribution.json": json.dumps(registry).encode(),
        "config/public_revocations.json": b'{"version":1,"revoked_sha256":[],"revoked_artifacts":[]}',
        name: document,
        "README.md": b"Legacy README",
        "src/demo.py": b"pass\n",
        "tests/test_public.py": b"pass\n",
        "tests/test_private.py": b"pass\n",
        "tests/fixtures/legacy.csv": b"synthetic\n1\n",
        "data/raw/input.csv": b"synthetic\n2\n",
        "docs/unreviewed.md": b"Pending documentation",
        ".git/config": b"synthetic Git metadata",
    }


def test_public_source_excludes_pending_data_documents_tests_and_git():
    files = source_files()
    selected = public_snapshot(files)
    assert selected["README.md"] == files["docs/architecture/demo.md"]
    assert "src/demo.py" in selected
    assert "tests/test_public.py" in selected
    for name in (
        "tests/test_private.py",
        "tests/fixtures/legacy.csv",
        "data/raw/input.csv",
        "docs/unreviewed.md",
        ".git/config",
    ):
        assert name not in selected


def test_changed_document_requires_another_review():
    files = source_files()
    files["docs/architecture/demo.md"] += b"changed"
    with pytest.raises(ValueError):
        public_snapshot(files)


@pytest.mark.parametrize(
    "target", ["config/public_scope.json", "config/public_distribution.json"]
)
def test_other_repository_approval_is_rejected(target):
    files = source_files()
    document = json.loads(files[target])
    document["repository"] = "other/repository"
    files[target] = json.dumps(document).encode()
    with pytest.raises(ValueError):
        public_snapshot(files)


def test_missing_document_authorization_is_rejected():
    files = source_files()
    document = json.loads(files["config/public_distribution.json"])
    document["authorizations"] = []
    files["config/public_distribution.json"] = json.dumps(document).encode()
    with pytest.raises(ValueError):
        public_snapshot(files)


def test_readme_cannot_alias_an_excluded_data_file():
    files = source_files()
    scope = json.loads(files["config/public_scope.json"])
    scope["readme_source"] = "data/raw/input.csv"
    files["config/public_scope.json"] = json.dumps(scope).encode()
    with pytest.raises(ValueError):
        public_snapshot(files)


@pytest.mark.parametrize("field", ["revoked_sha256", "revoked_artifacts"])
def test_source_zip_honors_revocation_of_readme_alias(field):
    files = source_files()
    policy = {"version": 1, "revoked_sha256": [], "revoked_artifacts": []}
    policy[field] = [
        hashlib.sha256(files["docs/architecture/demo.md"]).hexdigest()
        if field == "revoked_sha256"
        else "README.md"
    ]
    files["config/public_revocations.json"] = json.dumps(policy).encode()
    with pytest.raises(ValueError, match="Revoked artifact"):
        public_snapshot(files)


def test_source_zip_fails_closed_when_revocation_policy_is_missing():
    files = source_files()
    del files["config/public_revocations.json"]
    with pytest.raises(ValueError, match="invalid revocation policy"):
        public_snapshot(files)


def test_external_revocation_also_blocks_zip(tmp_path, monkeypatch):
    override = tmp_path / "policy.json"
    override.write_text(
        '{"version":1,"revoked_sha256":[],"revoked_artifacts":["src/demo.py"]}'
    )
    monkeypatch.setenv("GAP_PUBLIC_REVOCATIONS_PATH", str(override))
    with pytest.raises(ValueError, match="src/demo.py"):
        public_snapshot(source_files())


def test_public_selection_projects_only_sanitized_safety_metadata():
    files = source_files()
    restricted = b"synthetic restricted evidence"
    digest = hashlib.sha256(restricted).hexdigest()
    private = "docs/legacy/synthetic-private-case.md"
    files[INVENTORY] = json.dumps(
        {
            "excluded_files": [{"path": private, "sha256": digest}],
            "restricted_git_blobs": ["a" * 40],
        }
    ).encode()
    files.update(
        {
            ".githooks/pre-push": b"private hook",
            "src/private_pre_push.py": b"private implementation",
            "src/copy.py": b"private implementation",
            "config/public_visitor_content.json": json.dumps(
                {"version": 1, "files": {private: {"approved": False}}}
            ).encode(),
        }
    )
    selected, pending = _selection(files)
    assert not pending
    for name in (
        INVENTORY,
        ".githooks/pre-push",
        "src/private_pre_push.py",
        "src/copy.py",
    ):
        assert name not in selected
    for value in (private, digest, "a" * 40):
        assert value.encode() not in selected[PUBLIC_POLICY]
    assert json.loads(selected["config/public_visitor_content.json"])["files"] == {}
    assert snapshot_problems(selected, dict.fromkeys(selected, "100644")) == []
    for name, content in ((private, b"changed"), ("src/relabelled.txt", restricted)):
        with_forbidden = {**selected, name: content}
        assert any(
            name in problem
            for problem in snapshot_problems(
                with_forbidden, dict.fromkeys(with_forbidden, "100644")
            )
        )


def test_preview_lists_missing_grants_and_builder_keeps_blocking():
    files = source_files()
    files["config/public_distribution.json"] = json.dumps(
        {
            "repository": "samuelmaia-analytics/Governed-Analytics-Platform",
            "authorizations": [],
        }
    ).encode()
    selected, pending = _selection(files)
    assert pending == ["docs/architecture/demo.md"]
    assert selected["README.md"] == files[pending[0]]
    with pytest.raises(ValueError, match="Documentation authorization missing"):
        public_snapshot(files)
