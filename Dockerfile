# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md requirements.txt runtime.txt ./
COPY app ./app
COPY src ./src
COPY scripts ./scripts
COPY contracts ./contracts
COPY config ./config
COPY docs ./docs
COPY sql ./sql
COPY pages ./pages
COPY workflows ./workflows
COPY app.py streamlit_shared.py DASHBOARD_LICENSE_NOTICE.txt LICENSE Makefile ./

RUN pip install --upgrade pip \
    && pip install .

EXPOSE 8501
ENV PORT=8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/_stcore/health || exit 1

CMD ["sh", "-c", "streamlit run app/main.py --server.address=0.0.0.0 --server.port=${PORT}"]
