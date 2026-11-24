# Azure Manual Deployment Guide — Governed Analytics Platform (Streamlit)

This document prepares a **manual** deployment path for Microsoft Azure.
It does **not** create resources, publish images, or grant public dataset authorization.

## Recommended Azure target

- **Primary:** Azure Container Apps (ACA)
  - Best fit for a single-container Streamlit portfolio behind HTTPS with autoscaling and log aggregation.
- **Optional (advanced):** deploy src/api.py as a second ACA app if/when the API is required.

## Container assumptions

- Container image runs Streamlit: streamlit run app/main.py
- Default port: 8501 (set PORT env var if needed)
- Health endpoint: /_stcore/health

## Required files & controls

- The application **must not** ship private Olist datasets.
- The public visitor profile loads only data/samples/gap_public_demo_synthetic_v1.parquet **and only when authorized**.
- Authorization is fail-closed and depends on SHA-256 in config/public_distribution_authorizations.json.

## Environment variables (minimum)

- GAP_PUBLIC_VISITOR_MODE=true
- PORT=8501 (or match ACA ingress target port)

Optional integrations (do not configure unless you intend to enable them):
- GAP_API_BEARER_TOKEN=... (required to use the FastAPI endpoints)
- Snowflake: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_ROLE
- OpenAI/RAG features may require API keys depending on configuration

## Storage / persistence

- For a portfolio-only deployment, **persistence is not required**.
- If you want to persist logs or generated semantic slices beyond container restarts, mount an Azure File Share.
## Public dataset provisioning (APPROVED artifact)

The synthetic fixture is owner-approved for public portfolio use **by exact bytes**:
- Path: data/samples/gap_public_demo_synthetic_v1.parquet
- SHA-256: 9fe727d2e5f60ac8e2a9c7e6c4d979102882a11afa7874100c5705bcaa51a1c7

Recommended approach on Azure (do not bake data into the image):
- Create an Azure Storage Account + File Share.
- Upload the approved Parquet to the share.
- Mount the share into the Container App at /app/data/samples (read-only).
- Ensure the mounted file name is exactly gap_public_demo_synthetic_v1.parquet.

Revocation remains fail-closed:
- To revoke, update config/public_revocations.json and roll a new ACA revision.

## Manual steps (Portal)

### 1) Build container image locally

From the repo root:

```bash
docker build -t gap-public-portfolio:local .
```

Dataset is already approved for the public portfolio; prefer mounting it via Azure Files (see section above) and avoid baking the Parquet into the image.

### 2) Push image to Azure Container Registry (ACR)

- Create ACR (Basic is usually enough for training).
- Build/push using Docker or Azure CLI (manual training step).

### 3) Create Azure Container App

- Create **Container App Environment**
- Create **Container App** pointing to the pushed image
- Ingress:
  - External: **Enabled**
  - Target port: 8501
  - Transport: HTTP
- Health probes:
  - Liveness: /_stcore/health
  - (Optional) Startup probe with longer timeout on first boot

### 4) Configure environment variables

Set:
- GAP_PUBLIC_VISITOR_MODE=true
- PORT=8501

Do not configure secrets for private services unless you are enabling those integrations.

### 5) Verify health

- Open the Container App URL
- Confirm the Streamlit UI loads
- Confirm the sidebar shows Publication Gate state

## Rollback

- Keep at least 1 prior revision enabled in ACA.
- Roll back by selecting the prior revision as active.

## Abuse protection

- Keep resource limits tight (CPU/memory)
- Configure scaling min=0 / max small for training
- Consider IP restrictions / authentication layer if needed

## Cost notes

Azure costs depend on region and chosen plan.
Before deployment, confirm **current** pricing for:
- Azure Container Apps (consumption vs dedicated)
- Azure Container Registry
- Log Analytics (if enabled)

This repo does not assume the deployment will be free.
