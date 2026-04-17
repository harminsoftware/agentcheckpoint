FROM python:3.10-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml .
# Copying source for editable install or direct install
COPY src/ src/
RUN pip install --no-cache-dir -e ".[dashboard,postgres,s3]"

# Set environment
ENV HOST=0.0.0.0
ENV PORT=8585
ENV AGENTCHECKPOINT_STORAGE_PATH=/data/checkpoints

# Expose API port
EXPOSE 8585

# Healthcheck
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8585/api/health || exit 1

# Start server
CMD ["agentcheckpoint", "dashboard", "--host", "0.0.0.0", "--port", "8585"]
