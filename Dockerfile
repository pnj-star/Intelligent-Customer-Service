FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models/hf_cache

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY components ./components
COPY config ./config
COPY docker ./docker
COPY src ./src
COPY pyproject.toml README.md langgraph.json run.py run_mcp.py ./

# Install the local components without dependency resolution, then install the
# complete external dependency set explicitly. This keeps the image reproducible
# without publishing common-core / retrieve-skill / nl2sql-skill to PyPI.
RUN python -m pip install --upgrade pip \
    && python -m pip install \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch>=2.2" \
    && python -m pip install \
      "prometheus-client>=0.20" \
      "PyJWT[crypto]>=2.8" \
      "python-dotenv>=1.0" \
      "openai>=1.60" \
      "sentence-transformers>=3.3,<6" \
      "pymilvus>=2.5,<3" \
      "redis>=5.2" \
      "mcp>=1.2,<2" \
      "tiktoken>=0.8" \
      "pymysql>=1.1" \
      "DBUtils>=3.1" \
      "sqlglot>=23.0" \
      "pyyaml>=6.0" \
      "langgraph>=1.2,<2" \
      "fastapi>=0.115" \
      "uvicorn>=0.30" \
    && python -m pip install --no-deps \
      ./components/common_core \
      ./components/retrieve_skill \
      ./components/nl2sql_skill \
      .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "run.py"]
