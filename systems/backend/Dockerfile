# Stage 1: builder — install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Copy only the package manifest first for layer caching
COPY pyproject.toml ./

# Create a minimal src package stub so pip install -e . resolves correctly
RUN mkdir -p src && touch src/__init__.py

# Install runtime dependencies (no dev extras in production image)
RUN pip install --no-cache-dir -e .

# Stage 2: final image
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
