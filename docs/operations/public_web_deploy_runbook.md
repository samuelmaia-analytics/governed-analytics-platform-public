# Public web execution (Streamlit) — deploy runbook (no external publish)

This runbook prepares a reproducible public web execution of the Governed Analytics Platform (GAP) without distributing private datasets.

## Scope

- Target UI runtime: Streamlit app entrypoint `app/main.py`.
- Optional API runtime: FastAPI `src/api.py` (separate process).
- Public visitor profile: **no private datasets bundled** and **fail-closed** Publication Gate.

This document does **not** authorize publishing data or changing repository visibility.

## 1) Local run (private development)

Prerequisites:
- Python 3.11
- `uv` installed

Commands:
- Install deps: `uv sync --all-extras`
- Run Streamlit: `uv run streamlit run app/main.py`
- Run API (optional): `uv run uvicorn src.api:app --host 0.0.0.0 --port 8000`

Health checks:
- Streamlit loads and navigation works
- API returns `{"status":"ok"}` on `GET /health`

## 2) Public visitor web run (no datasets)

Recommended environment flags:
- `GAP_PUBLIC_VISITOR_MODE=true` (legacy alias: `GAP_PUBLIC_DEMO_MODE=true`)

Expected behavior:
- The application boots even without the public fixture dataset.
- Data-driven pages stay blocked with an explicit explanation.
- Documentation / governance pages remain available.
- Downloads remain deny-first.

## 3) Conditions to show public dashboards

See also: [synthetic_public_dataset_manifest.md](./synthetic_public_dataset_manifest.md).

Dashboards in the public visitor profile require **all** of the following:

- File present: `data/samples/gap_public_demo_synthetic_v1.parquet`
- Explicit grant for its exact bytes in `config/public_distribution_authorizations.json` with:
  - `audience=public`, `status=Approved`, `publication_authorized=true`
  - `sha256` matching the current file bytes
- No revocation for the file hash/path in `config/public_revocations.json`
- Publication Gate remains **fail-closed**

If any of the above conditions is not satisfied, the public visitor dataset remains blocked.

## 4) Streamlit Community Cloud (free-tier candidate)

Repository configuration:
- Python: `runtime.txt` (currently `python-3.11`)
- Dependencies: `requirements.txt` (pinned)
- Main file path: `app/main.py`

Secrets:
- Configure secrets in the Streamlit Cloud dashboard (never commit secrets).

Notes:
- The Community Cloud runtime overrides some Streamlit config options (consult Streamlit official docs).
- The platform does not assume persistence across restarts.

## 5) Rollback

- Streamlit Community Cloud: redeploy a previous commit/branch in the UI.
- Self-hosted container: redeploy the previously tagged image.
- Local: `git checkout <known-good-commit>` and rerun.

## 6) Verification checklist

- UI boots with `GAP_PUBLIC_VISITOR_MODE=true` and no fixture dataset
- Publication Gate remains BLOCKED without public authorization
- No private dataset files exist in the public repo tree
- Downloads are denied in public visitor mode
- Optional API requires `GAP_API_BEARER_TOKEN` (fail-closed when unset)
