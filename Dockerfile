# Headless server mode (ROADMAP.md Phase 8).
# Installs the advertised inference runtime so containers can run real nodes,
# not only the weight-less API shell.
FROM python:3.12-slim-bookworm

WORKDIR /app
COPY backend/pyproject.toml backend/README.md /app/backend/
COPY backend/src /app/backend/src
COPY frontend/dist /app/frontend/dist

# CPU torch first so the inference extra does not pull a CUDA wheel on slim CI hosts.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -e "/app/backend[inference]"

ENV RESTORE_HOME=/data
EXPOSE 8765
CMD ["restore", "serve", "--host", "0.0.0.0", "--port", "8765"]
