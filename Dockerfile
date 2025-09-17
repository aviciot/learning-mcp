FROM python:3.12-slim

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini && \
    rm -rf /var/lib/apt/lists/*

# install uv (no -y flag)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
ENV PYTHONPATH="/app/src" 

WORKDIR /app

# copy project files (include src so editable install works)
COPY pyproject.toml ./
COPY src ./src

# install deps with uv (editable)
RUN uv pip install --system -e .

EXPOSE 8013
ENTRYPOINT ["/usr/bin/tini", "--"]

