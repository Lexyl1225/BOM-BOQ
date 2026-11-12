#!/bin/bash
# ==============================================================================
# Entrypoint Script for BOM / BOQ Studio Pro Container with Tailscale
# ==============================================================================

set -e

# If custom command is provided to container, execute directly
if [ "$#" -gt 0 ] && [ "$1" != "start" ]; then
    exec "$@"
fi

echo "=================================================="
echo "🚀 Initializing BOM / BOQ Studio Pro Container"
echo "=================================================="

# 1. Initialize Persistent Data Mount (/app/data)
# Guarantees zero data loss across restarts, reboots, and container rebuilds
echo "[1/4] Checking persistent data mount at ${DATA_DIR:-/app/data}..."
mkdir -p "${DATA_DIR:-/app/data}/uploads"

# Seed SQLite database into data volume on first run
if [ ! -f "${DATA_DIR:-/app/data}/bom_system.db" ]; then
    if [ -f "/app/bom_system.db_initial" ]; then
        echo " -> Initializing persistent SQLite database from template..."
        cp /app/bom_system.db_initial "${DATA_DIR:-/app/data}/bom_system.db"
    fi
else
    echo " -> Existing database found at ${DATA_DIR:-/app/data}/bom_system.db (preserving data)."
fi

# Seed initial uploads if mount directory is empty
if [ -z "$(ls -A "${DATA_DIR:-/app/data}/uploads" 2>/dev/null)" ]; then
    if [ -d "/app/uploads_template" ] && [ -n "$(ls -A /app/uploads_template 2>/dev/null)" ]; then
        echo " -> Copying seed attachments to persistent uploads directory..."
        cp -rn /app/uploads_template/* "${DATA_DIR:-/app/data}/uploads/" 2>/dev/null || true
    fi
else
    echo " -> Persistent uploads directory already contains files (preserving data)."
fi

# Ensure seed SQL/JSON files are available in data directory
for f in bom_db_dump.sql users.json user_activity_logs.json; do
    if [ ! -f "${DATA_DIR:-/app/data}/$f" ] && [ -f "/app/$f" ]; then
        cp "/app/$f" "${DATA_DIR:-/app/data}/$f" || true
    fi
done

# 2. Configure TUN Device for Tailscale
echo "[2/4] Configuring network TUN device..."
if [ ! -c /dev/net/tun ]; then
    mkdir -p /dev/net
    mknod /dev/net/tun c 10 200 2>/dev/null || true
fi

# 3. Start Tailscale Daemon
echo "[3/4] Starting Tailscale daemon (hostname: ${TS_HOSTNAME:-bom})..."
mkdir -p /var/lib/tailscale /var/run/tailscale

tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscale/tailscaled.sock >/tmp/tailscaled.log 2>&1 &
TAILSCALED_PID=$!

# Wait for tailscaled socket to become available
for i in $(seq 1 30); do
    if tailscale --socket=/var/run/tailscale/tailscaled.sock status >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# Connect to Tailscale network
TS_HOST="${TS_HOSTNAME:-bom}"

if [ -n "${TS_AUTHKEY}" ]; then
    echo " -> Authenticating Tailscale with provided TS_AUTHKEY..."
    tailscale up --hostname="${TS_HOST}" --auth-key="${TS_AUTHKEY}" --accept-routes ${TS_EXTRA_ARGS} || true
else
    echo " -> Connecting Tailscale (using persisted state or generating auth link)..."
    # Use 5s timeout so web server boots immediately without waiting indefinitely on interactive auth
    tailscale up --hostname="${TS_HOST}" --accept-routes --timeout=5s ${TS_EXTRA_ARGS} || true
fi

# Show Tailscale connection info
TS_TAILNET_NAME="${TS_TAILNET:-ratfish-regulus.ts.net}"
FUNNEL_PUBLIC_URL="https://${TS_HOST}.${TS_TAILNET_NAME}"

if tailscale ip -4 >/dev/null 2>&1; then
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "not yet assigned")
    echo " -> Tailscale connected successfully!"
    echo " -> Hostname     : ${TS_HOST}"
    echo " -> Tailscale IP : ${TS_IP}"
    echo " -> Tailnet URL  : http://${TS_HOST}:${PORT:-8000}"
    echo " -> Funnel URL   : ${FUNNEL_PUBLIC_URL}"
else
    echo " -> Tailscale background service active."
    echo " -> If not yet authenticated, run: docker compose exec bom tailscale up"
fi

# 4. Start FastAPI Application
echo "[4/4] Starting BOM / BOQ Studio Pro FastAPI Application..."
echo "=================================================="
echo "📡 Server listening on port ${PORT:-8000}"
echo "🌐 Local Access     : http://localhost:${PORT:-8000}"
echo "🔒 Tailnet Access   : http://${TS_HOST}:${PORT:-8000}"
echo "🌍 Public Funnel    : ${FUNNEL_PUBLIC_URL}"
echo "=================================================="

# Export paths for FastAPI application
export DATA_DIR="${DATA_DIR:-/app/data}"
export DATABASE_URL="sqlite:///${DATA_DIR}/bom_system.db"
export UPLOAD_DIR="${DATA_DIR}/uploads"
export TS_HOSTNAME="${TS_HOST}"
export TS_TAILNET="${TS_TAILNET_NAME}"
export FUNNEL_URL="${FUNNEL_PUBLIC_URL}"

# Launch Uvicorn in background with proxy headers for TLS termination
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*' &
UVICORN_PID=$!

# 5. Tailscale Funnel Background Worker (Activates funnel once tailnet is connected)
activate_funnel_worker() {
    if [ "${TS_FUNNEL:-true}" != "true" ]; then
        return 0
    fi
    for i in $(seq 1 60); do
        if tailscale ip -4 >/dev/null 2>&1; then
            sleep 2
            echo " -> Activating Tailscale Funnel for port ${PORT:-8000}..."
            if tailscale funnel --bg --yes "${PORT:-8000}" >/tmp/funnel.log 2>&1; then
                echo "=================================================="
                echo "🎉 Tailscale Funnel is LIVE & PUBLICLY ACCESSIBLE!"
                echo "🌐 Public URL: ${FUNNEL_PUBLIC_URL}"
                echo "=================================================="
            else
                ERR=$(cat /tmp/funnel.log 2>/dev/null || echo "Check Funnel ACL")
                echo "⚠️ Tailscale Funnel notice: ${ERR}"
                echo "   If Funnel requires ACL permission, see DEPLOYMENT.md"
            fi
            return 0
        fi
        sleep 2
    done
}
activate_funnel_worker &
FUNNEL_PID=$!

# Trap signals for graceful shutdown
cleanup() {
    echo ""
    echo "⚠️ Shutting down container services..."
    kill -TERM "$FUNNEL_PID" 2>/dev/null || true
    kill -TERM "$UVICORN_PID" 2>/dev/null || true
    kill -TERM "$TAILSCALED_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
    echo "✓ Clean shutdown complete."
    exit 0
}

trap cleanup SIGTERM SIGINT

# Keep entrypoint alive
wait "$UVICORN_PID"
