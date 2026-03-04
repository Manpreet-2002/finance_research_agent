FROM node:20-bookworm-slim AS node_runtime

FROM python:3.11-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH=/app/.venv/bin:/usr/local/bin:${PATH}

COPY --from=node_runtime /usr/local/ /usr/local/

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY infographics/package.json infographics/package-lock.json ./infographics/
RUN cd infographics \
    && npm ci \
    && npx playwright install --with-deps chromium

COPY backend ./backend
COPY infographics ./infographics
COPY skills ./skills
COPY Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx ./
COPY Valuation_Agent_Logbook_ExcelGraph.xlsx ./

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/artifacts /tmp/google /ms-playwright \
    && chown -R appuser:appuser /app /tmp/google /ms-playwright

USER appuser

EXPOSE 8000

CMD ["uvicorn", "backend.app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
