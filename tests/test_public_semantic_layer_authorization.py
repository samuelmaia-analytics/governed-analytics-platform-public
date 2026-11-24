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

    calls = {"count": 0}
    real_stage = semantic_layer.stage_dataset

    def broken_stage(df: pd.DataFrame, target: Path, temp_dir: Path):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("boom")
        return real_stage(df, target, temp_dir)

    monkeypatch.setattr(semantic_layer, "stage_dataset", broken_stage)

    with pytest.raises(RuntimeError):
        semantic_layer.run_semantic_layer(output_dir=semantic_dir, docs_dir=docs_dir)

    assert not (semantic_dir / "logistics_slice.parquet").exists()
    assert not (semantic_dir / "seller_slice.parquet").exists()
    assert not (semantic_dir / "cohort_slice.parquet").exists()
    assert not (semantic_dir / "category_slice.parquet").exists()
    assert not (semantic_dir / "state_performance_slice.parquet").exists()



def test_semantic_layer_cleanup_isolated_per_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    semantic_dir = tmp_path / "semantic"
    docs_dir = tmp_path / "docs"

    foreign_dir = semantic_dir / ".tmp_semantic_layer_foreign"
    foreign_dir.mkdir(parents=True)
    foreign_file = foreign_dir / "foreign.tmp"
    foreign_file.write_text("keep", encoding="utf-8")

    monkeypatch.setattr(semantic_layer, "load_published_table", lambda: generate(rows=501))

    semantic_layer.run_semantic_layer(output_dir=semantic_dir, docs_dir=docs_dir)

    assert foreign_file.exists(), "Cleanup must not delete unrelated temp artifacts"
    remaining = [p for p in semantic_dir.glob(".tmp_semantic_layer_*") if p != foreign_dir]
    assert not remaining, "Temp dirs must be removed"


def test_semantic_layer_concurrent_runs_use_isolated_temp_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(semantic_layer, "load_published_table", lambda: generate(rows=801))

    def _run(target: Path) -> None:
        semantic_layer.run_semantic_layer(output_dir=target / "semantic", docs_dir=target / "docs")

    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(_run, [run_a, run_b]))

    assert (run_a / "semantic" / "seller_slice.parquet").exists()
    assert (run_b / "semantic" / "seller_slice.parquet").exists()



def test_semantic_layer_concurrent_runs_same_output_dir_produces_consistent_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    semantic_dir = tmp_path / 'semantic'
    docs_dir = tmp_path / 'docs'

    barrier = Barrier(2)
    reports: dict[str, list[str]] = {'texts': []}

    def render_report(*_args, **_kwargs) -> str:
        text = ('report-{}-'.format(len(reports['texts'])) + ('X' * 50_000))
        reports['texts'].append(text)
        return text

    real_commit = semantic_layer.commit_staged_dataset

    def commit_with_barrier(parquet_tmp: Path, csv_tmp: Path, target: Path) -> None:
        real_commit(parquet_tmp, csv_tmp, target)
        if target.name == 'state_performance_slice.parquet':
            barrier.wait(timeout=10)

    monkeypatch.setattr(semantic_layer, 'load_published_table', lambda: generate(rows=1001))
    monkeypatch.setattr(semantic_layer, 'render_report', render_report)
    monkeypatch.setattr(semantic_layer, 'commit_staged_dataset', commit_with_barrier)

    def _run() -> None:
        semantic_layer.run_semantic_layer(output_dir=semantic_dir, docs_dir=docs_dir)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: _run(), range(2)))

    expected_reports = set(reports['texts'])
    report_path = docs_dir / 'semantic_layer.md'
    assert report_path.exists()
    assert report_path.read_text(encoding='utf-8') in expected_reports

    for slice_name in (
        'logistics_slice.parquet',
        'seller_slice.parquet',
        'cohort_slice.parquet',
        'category_slice.parquet',
        'state_performance_slice.parquet',
    ):
        slice_path = semantic_dir / slice_name
        assert slice_path.exists()
        df = pd.read_parquet(slice_path)
        assert not df.empty

    assert not list(semantic_dir.glob('.tmp_semantic_layer_*')), 'Temp dirs must be cleaned'
