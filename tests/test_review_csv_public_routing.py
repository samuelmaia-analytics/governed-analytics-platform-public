from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app.context as context
import src.data_loader as loader
from scripts.generate_synthetic_public_demo import generate
from src.data_quality import run_data_quality_checks
from src.public_distribution_authorization import REQUIRED_ARTIFACTS
from src.schema_contract_components.checks import validate_contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(context, "PROJECT_ROOT", tmp_path)
    fixture = tmp_path / "data/samples/gap_public_demo_synthetic_v1.parquet"
    monkeypatch.setattr(loader, "DEFAULT_PUBLIC_DEMO_DATASET", fixture)
    monkeypatch.setattr(context, "DEFAULT_PUBLIC_DEMO_DATASET", fixture)
    monkeypatch.setenv(
        "GAP_PUBLIC_REVOCATIONS_PATH", str(tmp_path / "config/public_revocations.json")
    )
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
    return tmp_path


@pytest.mark.parametrize("invalid", [False, True])
def test_published_csv_dates_preserve_real_contract_failures(
    root, monkeypatch, invalid
):
    monkeypatch.delenv("GAP_PUBLIC_DEMO_MODE", raising=False)
    contract = json.loads(
        (ROOT / "contracts/published/fact_orders_dashboard.contract.json").read_text()
    )
    target = root / "contracts/published/fact_orders_dashboard.contract.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(contract))
    csv = root / "data/published/dashboard/fact_orders_dashboard.csv"
    csv.parent.mkdir(parents=True)
    frame = generate(20)
    if invalid:
        frame["order_date"] = "invalid-date"
        frame["order_purchase_timestamp"] = "invalid-date"
    frame.to_csv(csv, index=False)
    loaded = loader.load_dataset(csv)
    checks = validate_contract(contract, load_dataset_fn=lambda _: loaded)
    date_failures = [
        c
        for c in checks
        if c.status == "FAIL"
        and ("order_date" in str(c) or "order_purchase_timestamp" in str(c))
    ]
    assert bool(date_failures) is invalid
    assert pd.api.types.is_datetime64_any_dtype(loaded.order_delivered_customer_date)
    if invalid:
        quality = run_data_quality_checks(loaded, dataset_name="fact_orders_dashboard")
        assert quality["failed_checks_count"] > 0


def provision_synthetic_test_grants(root):
    # Grants exist only in pytest's temporary root, never in repository policy.
    fixture = root / "data/samples/gap_public_demo_synthetic_v1.parquet"
    fixture.parent.mkdir(parents=True)
    generate().to_parquet(fixture, index=False)
    grants = []
    for name, purpose in REQUIRED_ARTIFACTS.items():
        path = root / name
        if path != fixture:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Synthetic test document")
        grants.append(
            {
                "file": name,
                "purpose": purpose,
                "audience": "public",
                "status": "Approved",
                "publication_authorized": True,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    registry = root / "config/public_distribution_authorizations.json"
    registry.write_text(json.dumps({"version": 1, "authorizations": grants}))
    return fixture, registry


def test_normal_startup_retains_published_route(root, monkeypatch):
    monkeypatch.delenv("GAP_PUBLIC_DEMO_MODE", raising=False)
    published = root / "published.csv"
    published.write_text("synthetic\n1\n")
    monkeypatch.setattr(context, "DEFAULT_PUBLISHED_DATASET", published)
    sidebar = Mock()
    sidebar.file_uploader.return_value = None
    sidebar.toggle.return_value = True
    monkeypatch.setattr(context.st, "sidebar", sidebar)
    result = context.load_input_dataframe("en-US")
    assert result.attrs["uses_persisted_governance"] is True


def test_public_startup_checks_grants_hash_and_live_revocation(root, monkeypatch):
    monkeypatch.setenv("GAP_PUBLIC_DEMO_MODE", "true")
    fixture, registry = provision_synthetic_test_grants(root)
    uploader = Mock(side_effect=AssertionError("Public mode must not accept uploads"))
    monkeypatch.setattr(context.st.sidebar, "file_uploader", uploader)
    context._build_context_from_dataframe.clear()
    approved = context.build_context("en-US")
    assert approved.df.attrs["quality_dataset"] == "fact_orders_dashboard"
    assert not approved.uses_persisted_governance
    assert approved.public_distribution_gate.decision != "BLOCKED"
    assert not approved.report_paths
    uploader.assert_not_called()
    app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=45).run()
    assert not app.exception
    assert any("<h1>Governed Analytics Platform</h1>" in item.value for item in app.markdown)
    policy = root / "config/public_revocations.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "revoked_sha256": [],
                "revoked_artifacts": ["docs/reports/data_dictionary.md"],
            }
        )
    )
    assert (
        context.build_context("en-US").public_distribution_gate.decision == "APPROVED"
    )
    policy.write_text(
        json.dumps({"version": 1, "revoked_artifacts": [], "revoked_sha256": []})
    )
    original = registry.read_bytes()
    registry.write_text(json.dumps({"version": 1, "authorizations": []}))
    with pytest.raises(PermissionError):
        context.build_context("en-US")
    registry.write_bytes(original)
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "revoked_artifacts": [],
                "revoked_sha256": [hashlib.sha256(fixture.read_bytes()).hexdigest()],
            }
        )
    )
    with pytest.raises(PermissionError):
        context.build_context("en-US")
    policy.write_text(
        json.dumps({"version": 1, "revoked_artifacts": [], "revoked_sha256": []})
    )
    fixture.write_bytes(b"changed bytes")
    with pytest.raises(PermissionError):
        context.build_context("en-US")


def test_public_mode_never_falls_back_to_historical_or_missing_fixture(
    root, monkeypatch
):
    monkeypatch.setenv("GAP_PUBLIC_DEMO_MODE", "true")
    historical = root / "historical.csv"
    historical.write_text("synthetic\n1\n")
    monkeypatch.setattr(context, "DEFAULT_PUBLISHED_DATASET", historical)
    with pytest.raises(FileNotFoundError):
        context.load_input_dataframe("en-US")
    with pytest.raises(PermissionError):
        loader.load_dataset(historical)
