# Synthetic Public Dataset Manifest (APPROVED)

## Summary

- **Artifact:** data/samples/gap_public_demo_synthetic_v1.parquet
- **Audience:** public
- **Purpose:** synthetic_demo_preview
- **Status:** Approved (owner-authorized for public portfolio distribution)
- **Rows:** 100,001
- **Grain:** one row per order_id + order_item_id
- **SHA-256 (current local bytes):** 9fe727d2e5f60ac8e2a9c7e6c4d979102882a11afa7874100c5705bcaa51a1c7
- **Generator:** scripts/generate_synthetic_public_demo.py (gap-synthetic-demo-v2)

## Why this exists

This fixture is designed to let the **full Streamlit portfolio** run without using any private Olist data.
The dataset is synthetic-only and uses pseudonymized identifiers derived from deterministic hashes.

## Contract alignment

- Dataset contract: contracts/published/fact_orders_dashboard.contract.yml
- Schema checks contract: contracts/published/fact_orders_dashboard.contract.json

The fixture columns match the published dashboard contract and are designed to keep relationships coherent across:
- Business KPIs (revenue, sellers)
- Cohorts
- Semantic slices
- Governance / LGPD classification

## Privacy & re-identification posture

- No real emails, phone numbers, documents, addresses, or names.
- Identifiers are deterministic hashes prefixed by the identifier type.
- Geography is limited to state-level (SP, RJ, MG, PR) only.

## How to (re)generate locally (deterministic environment)

Use the pinned dependency set from uv.lock.

```bash
uv sync --frozen --all-extras
uv run python scripts/generate_synthetic_public_demo.py data/samples/gap_public_demo_synthetic_v1.parquet
```

Important: Parquet bytes can differ across dependency versions. For byte-stable SHA-256, always generate using the locked environment.

## Publication Gate notes

- The public visitor profile requires **byte-level authorization** in config/public_distribution_authorizations.json.
- This manifest and SHA-256 are retained as traceability evidence for the owner approval.
- Owner authorization granted on 2026-11-24 for this artifact only.
