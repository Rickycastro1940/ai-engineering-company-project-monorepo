# Brasaland Digital backend (CONTEXT.md Technology — Nicolás Park).
# Official Python image. Installs uv, then dependencies from root requirements.txt.
# Build from the monorepo root:
#   docker build -f services/Dockerfile -t brasaland-api .

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:/usr/local/bin:$PATH"

# Install uv (Astral) onto the official Python image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN uv venv "$VIRTUAL_ENV"

COPY requirements.txt /app/requirements.txt
RUN uv pip install -r requirements.txt

COPY api /app/api
COPY services /app/services
COPY data /app/data
COPY scripts /app/scripts
COPY agent.py products.csv pyproject.toml /app/

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
