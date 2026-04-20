FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy package metadata first to leverage Docker layer caching
COPY pyproject.toml ./

# Install runtime dependencies only (no dev extras in the image)
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .

# Copy the source package and CLI entry point
COPY src/ ./src/
COPY ingest.py ./

# Run as a non-root user for security
RUN adduser --disabled-password --gecos "" importer && chown -R importer /app
USER importer

# The import pipeline is invoked as a one-off command or Kubernetes Job.
# Callers pass --source and optional --config as CMD arguments.
ENTRYPOINT ["python", "ingest.py"]
