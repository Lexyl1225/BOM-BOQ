# ==============================================================================
# BOM / BOQ Studio Pro — Docker Container with Integrated Tailscale
# Hostname: bom
# ==============================================================================

FROM python:3.12-slim-bookworm

# Set environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    DATA_DIR=/app/data \
    TS_HOSTNAME=bom

# Install system dependencies, networking tools, and Tailscale
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    iptables \
    iproute2 \
    procps \
    && curl -fsSL https://tailscale.com/install.sh | sh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create application and persistence directories
WORKDIR /app
RUN mkdir -p /app/data /app/data/uploads /var/lib/tailscale /var/run/tailscale /dev/net

# Install Python requirements
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ /app/app/
COPY run.py /app/run.py

# Copy initial database and seed files (used for initial population of data mount if empty)
COPY bom_system.db /app/bom_system.db_initial
COPY bom_db_dump.sql /app/bom_db_dump.sql
COPY users.json /app/users.json
COPY user_activity_logs.json /app/user_activity_logs.json

# Copy existing uploads as initial template
COPY uploads/ /app/uploads_template/

# Copy container entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose web application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
