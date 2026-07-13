# Headless server mode (ROADMAP.md Phase 8)
FROM python:3.12-slim-bookworm

WORKDIR /app
COPY backend/pyproject.toml backend/README.md /app/backend/
COPY backend/src /app/backend/src
COPY frontend/dist /app/frontend/dist

RUN pip install --no-cache-dir -e "/app/backend[dev]" \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

ENV RESTORE_HOME=/data
EXPOSE 8765
CMD ["restore", "serve", "--host", "0.0.0.0", "--port", "8765"]
