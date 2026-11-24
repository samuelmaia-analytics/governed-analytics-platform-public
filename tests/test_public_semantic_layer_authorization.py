from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import src.data_loader as data_loader
import src.semantic_layer as semantic_layer
from scripts.generate_synthetic_public_demo import generate

ARTIFACT = "data/samples/gap_public_demo_synthetic_v1.parquet"
PURPOSE = "synthetic_demo_preview"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _setup_public_artifact(root: Path, *, approved: bool, sha_override: str | None = None) -> tuple[Path, str]:
    artifact_path = root / ARTIFACT
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    df = generate(rows=2_001)
    df.to_parquet(artifact_path, index=False)

    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    sha = sha_override or digest

    _write_json(
        root / "config/public_revocations.json",
        {"version": 1, "revoked_sha256": [], "revoked_artifacts": []},
    )

    _write_json(
        root / "config/public_distribution_authorizations.json",
        {
            "version": 1,
            "authorizations": [
                {
                    "file": ARTIFACT,
                    "sha256": sha,
                    "purpose": PURPOSE,
                    "audience": "public",
                    "status": "Approved" if approved else "Needs Review",
                    "publication_authorized": approved,
                }
            ],
        },
    )

    return artifact_path, digest


def _patch_loader_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(data_loader, "PROJECT_ROOT", root)
    monkeypatch.setattr(data_loader, "DEFAULT_PUBLIC_DEMO_DATASET", root / ARTIFACT)
    monkeypatch.setattr(data_loader, "DEFAULT_SAMPLE_DATASET", root / "data/samples/sample_governance_dataset.csv")


def test_public_semantic_layer_allows_only_authorized_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    artifact_path, digest = _setup_public_artifact(root, approved=True)
    _patch_loader_root(monkeypatch, root)

    # Create a private-looking published dashboard source that must be ignored.
    private_df = pd.DataFrame({"order_id": ["PRIVATE"], "order_item_id": [1]})
    private_path = root / "private_source.parquet"
    private_df.to_parquet(private_path, index=False)

    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")
    monkeypatch.setenv("GAP_SEMANTIC_LAYER_SOURCE_PATH", str(private_path))
    monkeypatch.setattr(semantic_layer, "PUBLISHED_SOURCE_PATH", private_path)

    df = semantic_layer.load_published_table()

    assert len(df) == 2001
    assert df.shape[1] == 34
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == digest


def test_public_semantic_layer_blocks_unapproved_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    _setup_public_artifact(root, approved=False)
    _patch_loader_root(monkeypatch, root)

    private_path = root / "private_source.parquet"
    pd.DataFrame({"order_id": ["PRIVATE"], "order_item_id": [1]}).to_parquet(private_path, index=False)

    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")
    monkeypatch.setattr(semantic_layer, "PUBLISHED_SOURCE_PATH", private_path)

    with pytest.raises(PermissionError):
        semantic_layer.load_published_table()


def test_public_semantic_layer_blocks_sha_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    _setup_public_artifact(root, approved=True, sha_override="0" * 64)
    _patch_loader_root(monkeypatch, root)

    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")

    with pytest.raises(PermissionError):
        semantic_layer.load_published_table()


def test_public_semantic_layer_blocks_revoked_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    artifact_path, digest = _setup_public_artifact(root, approved=True)
    _patch_loader_root(monkeypatch, root)

    _write_json(
        root / "config/public_revocations.json",
        {"version": 1, "revoked_sha256": [digest], "revoked_artifacts": []},
    )

    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")

    with pytest.raises(PermissionError):
        semantic_layer.load_published_table()


def test_public_semantic_layer_ignores_alternative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    _setup_public_artifact(root, approved=False)
    _patch_loader_root(monkeypatch, root)

    private_path = root / "private_source.parquet"
    pd.DataFrame({"order_id": ["PRIVATE"], "order_item_id": [1]}).to_parquet(private_path, index=False)

    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")
    monkeypatch.setenv("GAP_SEMANTIC_LAYER_SOURCE_PATH", str(private_path))

    with pytest.raises(PermissionError):
        semantic_layer.load_published_table()


def test_public_semantic_layer_materialization_is_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    _setup_public_artifact(root, approved=True)
    _patch_loader_root(monkeypatch, root)

    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")

    semantic_dir = tmp_path / "semantic"
    docs_dir = tmp_path / "docs"

    monkeypatch.setattr(semantic_layer, "PUBLISHED_SEMANTIC_DIR", semantic_dir)
    monkeypatch.setattr(semantic_layer, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(semantic_layer, "LOGISTICS_PATH", semantic_dir / "logistics_slice.parquet")
    monkeypatch.setattr(semantic_layer, "SELLER_PATH", semantic_dir / "seller_slice.parquet")
    monkeypatch.setattr(semantic_layer, "COHORT_PATH", semantic_dir / "cohort_slice.parquet")
    monkeypatch.setattr(semantic_layer, "CATEGORY_PATH", semantic_dir / "category_slice.parquet")
    monkeypatch.setattr(semantic_layer, "STATE_PATH", semantic_dir / "state_performance_slice.parquet")
    monkeypatch.setattr(semantic_layer, "REPORT_PATH", docs_dir / "semantic_layer.md")

    calls = {"count": 0}
    real_stage = semantic_layer.stage_dataset

    def broken_stage(df: pd.DataFrame, target: Path, temp_dir: Path):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("boom")
        return real_stage(df, target, temp_dir)

    monkeypatch.setattr(semantic_layer, "stage_dataset", broken_stage)

    with pytest.raises(RuntimeError):
        semantic_layer.run_semantic_layer()

    assert not (semantic_dir / "logistics_slice.parquet").exists()
    assert not (semantic_dir / "seller_slice.parquet").exists()
    assert not (semantic_dir / "cohort_slice.parquet").exists()
    assert not (semantic_dir / "category_slice.parquet").exists()
    assert not (semantic_dir / "state_performance_slice.parquet").exists()
