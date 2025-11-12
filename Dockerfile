FROM python:3.12-slim

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini supervisor && \
    rm -rf /var/lib/apt/lists/*

# install uv (no -y flag)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
ENV PYTHONPATH="/app/src" 

WORKDIR /app

# copy project files (include src so editable install works)
COPY pyproject.toml ./
COPY src ./src
COPY tests ./tests
COPY config ./config
COPY data ./data
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# install deps with uv (editable + test extras)
RUN uv pip install --system -e ".[test]"

# Create state directory for SQLite
RUN mkdir -p /app/state

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=http \
    MCP_PORT=8013 \
    JOB_PORT=8014 \
    USE_AUTOGEN=0

# Expose both ports
EXPOSE 8013 8014

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]


