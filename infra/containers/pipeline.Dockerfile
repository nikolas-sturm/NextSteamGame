FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /workspace
ENV UV_LINK_MODE=copy UV_NO_DEV=1
COPY pyproject.toml uv.lock ./
COPY pipeline ./pipeline
RUN uv sync --frozen --no-dev
ENTRYPOINT ["uv", "run", "nextsteam-pipeline"]
