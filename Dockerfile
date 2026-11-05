FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.7
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home biomcp
USER biomcp
ENTRYPOINT ["/app/.venv/bin/ensembl-uniprot-mcp", "--transport", "stdio"]
