# 🚀 BOM / BOQ Studio Pro — Docker & Tailscale Funnel Deployment Guide

This guide provides complete instructions for deploying the **BOM / BOQ Studio Pro** FastAPI application in a Docker container with integrated **Tailscale Funnel**, making it securely accessible worldwide via HTTPS at **`https://bom.ratfish-regulus.ts.net`**, with automatic host reboot recovery and persistent data mounts.

---

## 📋 Table of Contents
1. [Architecture Overview](#-architecture-overview)
2. [Prerequisites](#-prerequisites)
3. [Tailscale Funnel Setup (One-Time Tailnet Config)](#-tailscale-funnel-setup-one-time-tailnet-config)
4. [Quick Start (One-Command Setup)](#-quick-start-one-command-setup)
5. [Tailscale Authentication](#-tailscale-authentication)
   - [Method A: Automated Auth Key (Recommended)](#method-a-automated-auth-key-recommended)
   - [Method B: Interactive Browser Login](#method-b-interactive-browser-login)
6. [Accessing the Application](#-accessing-the-application)
7. [Host Reboot & Restart Guarantee](#-host-reboot--restart-guarantee)
8. [Persistent Data Mount & Backup](#-persistent-data-mount--backup)
9. [Useful Operations & Management Commands](#-useful-operations--management-commands)
10. [Troubleshooting](#-troubleshooting)

---

## 🏗️ Architecture Overview

```
                          ┌────────────────────────────────────────────────────────┐
                          │                   Host Machine                         │
                          │                                                        │
                          │   ┌────────────────────────────────────────────────┐   │
                          │   │          Docker Container ("bom")              │   │
                          │   │                                                │   │
Public Internet ─────────►│───┼──► Tailscale Funnel (Port 443 HTTPS)           │   │
(https://bom.ratfish-     │   │         │ (Automated Let's Encrypt TLS)        │   │
 regulus.ts.net)          │   │         ▼                                      │   │
                          │   │    Tailscale Daemon (hostname: "bom")          │   │
Private Tailnet ─────────►│───┼──►      │ (internal routing)                   │   │
(http://bom:8000)         │   │         ▼                                      │   │
LAN / Localhost ─────────►│───┼──► FastAPI / Uvicorn Server (:8000)            │   │
(http://localhost:8000)   │   │    (with --proxy-headers for TLS forwarding)   │   │
                          │   │         │                                      │   │
                          │   │         ▼                                      │   │
                          │   │    SQLite ORM & File Storage                   │   │
                          │   └─────────┬───────────────────┬──────────────────┘   │
                          │             │                   │                      │
                          │   ┌─────────▼─────────┐   ┌─────▼──────────────────┐   │
                          │   │ Host Data Mount   │   │ Tailscale State Volume │   │
                          │   │  (./data)         │   │  (tailscale_state)     │   │
                          │   │  - bom_system.db  │   │  - tailscaled.state    │   │
                          │   │  - uploads/       │   │  - serve/funnel config │   │
                          │   └───────────────────┘   └────────────────────────┘   │
                          └────────────────────────────────────────────────────────┘
```

- **Application:** High-performance asynchronous FastAPI Python 3.12 backend with proxy headers for seamless HTTPS forwarding.
- **Tailscale Funnel:** Routes public traffic from **`https://bom.ratfish-regulus.ts.net`** over TLS to port 8000 without opening router ports or configuring third-party reverse proxies.
- **Persistence:** All document data, SQLite tables, and uploaded PO files are stored in `./data`.
- **Identity Retention:** Tailscale node credentials and Funnel configuration are stored in the `bom_tailscale_state` volume, so the node retains its identity and certificates across reboots.
- **Auto-Recovery:** Container restart policy `restart: unless-stopped` ensures instant automatic startup when the host operating system boots or reboots.

---

## 💻 Prerequisites

Ensure the host machine (Linux, macOS, or Windows with WSL2) has the following installed:

1. **Docker Engine** (version 24.0+)
2. **Docker Compose** (version 2.0+)
3. A **Tailscale Account** with tailnet **`ratfish-regulus.ts.net`**

---

## 🌍 Tailscale Funnel Setup (One-Time Tailnet Config)

Before enabling Funnel on your container, verify two settings in the Tailscale Admin Console:

### 1. Enable MagicDNS & HTTPS Certificates
1. Go to [Tailscale Admin Console → DNS](https://login.tailscale.com/admin/dns).
2. Ensure **MagicDNS** is enabled.
3. Under **HTTPS Certificates**, click **Enable HTTPS Certificates**. (Tailscale automatically provisions valid Let's Encrypt certificates for `*.ts.net`).

### 2. Enable Funnel in Access Controls (ACLs)
1. Go to [Tailscale Admin Console → Access Controls](https://login.tailscale.com/admin/acls).
2. Ensure your policy allows Funnel for your tailnet nodes by adding `funnel` to `nodeAttrs`:
   ```json
   "nodeAttrs": [
     {
       "target": ["autogroup:members", "*"],
       "attr": ["funnel"]
     }
   ]
   ```
3. Save the ACL policy.

---

## ⚡ Quick Start (One-Command Setup)

### 1. Navigate to Project Directory
```bash
cd /mnt/d/bom_finalv1.1.2
```

### 2. Configure Environment (.env)
Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env`:
```ini
# Tailscale Authentication Key (from https://login.tailscale.com/admin/settings/keys)
TS_AUTHKEY=tskey-auth-kxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxx

# Tailscale Hostname & Tailnet
TS_HOSTNAME=bom
TS_TAILNET=ratfish-regulus.ts.net

# Enable Tailscale Funnel (Public HTTPS access)
TS_FUNNEL=true

# Application Secret Key
SECRET_KEY=b0m-sUpEr-s3cr3t-kEy-998822-ph-engr-alex-2026

# Local Host Port
PORT=8000
```

### 3. Build & Start the Container
```bash
docker compose up -d --build
```

### 4. Verify Container Status
```bash
docker compose ps
```
You should see container `bom` running with status `Up (healthy)`.

---

## 🔐 Tailscale Authentication

The container joins your tailnet as **`bom`** and activates Funnel at **`https://bom.ratfish-regulus.ts.net`**.

### Method A: Automated Auth Key (Recommended)
1. Generate a reusable auth key at [Tailscale Admin Console → Settings → Keys](https://login.tailscale.com/admin/settings/keys).
2. Set `TS_AUTHKEY=tskey-auth-...` in `.env`.
3. Run `docker compose up -d`. The container authenticates automatically and publishes the Funnel URL.

### Method B: Interactive Browser Login
If you do not have an auth key:
1. Start the container with `TS_AUTHKEY=` empty.
2. View the container logs:
   ```bash
   docker compose logs -f
   ```
3. Copy the authentication link:
   ```
   To authenticate, visit:
       https://login.tailscale.com/a/xxxxxxxxxxxx
   ```
4. Open the link in any web browser and authorize device `bom`.
5. Once logged in, the container worker automatically activates Funnel and announces:
   ```
   🎉 Tailscale Funnel is LIVE & PUBLICLY ACCESSIBLE!
   🌐 Public URL: https://bom.ratfish-regulus.ts.net
   ```

---

## 🌐 Accessing the Application

Once running, the application can be accessed via:

| Access Method | URL | Description |
| :--- | :--- | :--- |
| **🌍 Tailscale Funnel (Public)** | **`https://bom.ratfish-regulus.ts.net`** | **Public HTTPS worldwide access with automatic SSL certificate** |
| **🔒 Tailscale MagicDNS** | `http://bom:8000` | Private tailnet access for devices on your Tailscale network |
| **🔒 Tailscale IP** | `http://<tailscale-ip>:8000` | Direct private Tailscale IP (100.x.y.z) |
| **🏠 Localhost** | `http://localhost:8000` | Local machine access |
| **🏢 Local LAN** | `http://<host-ip>:8000` | Office / Home LAN access |
| **📖 API Documentation** | `https://bom.ratfish-regulus.ts.net/docs` | Interactive Swagger API documentation |

### Default Credentials
- **Username:** `Admin`
- **Password:** `admin123`

---

## 🔄 Host Reboot & Restart Guarantee

The container is configured with:
```yaml
restart: unless-stopped
```

### Why this guarantees 100% uptime:
1. **Operating System Reboot:** When the host machine restarts (power outage, kernel update, server reboot), the Docker daemon automatically starts the `bom` container upon boot.
2. **Container Crash Protection:** If the process is terminated unexpectedly, Docker restarts it immediately.
3. **Tailscale State Retention:** Because `/var/lib/tailscale` is mounted to the named volume `bom_tailscale_state`, Tailscale automatically restores its existing encryption keys, hostname (`bom`), and assigned 100.x.y.z IP without requesting a new login.
4. **Data Retention:** Because `/app/data` is mounted to `./data` on the host, the database and all uploaded PO files remain completely intact.

### Testing Host Reboot Recovery
You can test the automatic restart mechanism by simulating a container restart:
```bash
docker restart bom
docker compose logs -f
```
You will see Tailscale reconnect instantly and the FastAPI server serve requests without data loss.

---

## 💾 Persistent Data Mount & Backup

### Storage Structure
All persistent state is stored outside the container inside `./data`:
```
./data/
├── bom_system.db            # Primary SQLite database (Users, BOMs, BOQs, Estimates, Logs)
└── uploads/                 # Uploaded PO files, engineering attachments, and PDFs
```

### Creating Backups
To create a complete backup of the application state, simply archive the `./data` directory:
```bash
# Create timestamped backup archive
tar -czvf bom_backup_$(date +%Y%m%d_%H%M%S).tar.gz data/
```

### Restoring from Backup
```bash
# 1. Stop container
docker compose down

# 2. Restore data directory
tar -xzvf bom_backup_YYYYMMDD_HHMMSS.tar.gz

# 3. Restart container
docker compose up -d
```

---

## 🛠️ Useful Operations & Management Commands

### Check Container Status
```bash
docker compose ps
```

### View Live Application & Tailscale Logs
```bash
docker compose logs -f --tail=100
```

### Check Tailscale Status Inside Container
```bash
docker compose exec bom tailscale status
```

### Check Tailscale Funnel Status
```bash
docker compose exec bom tailscale funnel status
```

### Enable Funnel Manually
```bash
docker compose exec bom tailscale funnel --bg --yes 8000
```

### Reset / Disable Funnel (Switch Back to Private Tailnet Only)
```bash
docker compose exec bom tailscale funnel reset
```

### Check Tailscale IP Address
```bash
docker compose exec bom tailscale ip -4
```

### Update to Latest Code Version
```bash
git pull
docker compose build --no-cache
docker compose up -d
```

### Stop the Container
```bash
docker compose down
```
*(Your data in `./data` and Tailscale credentials in `tailscale_state` will remain safe.)*

---

## ❓ Troubleshooting

### 1. Tailscale Fails to Connect
- **Check `/dev/net/tun`:** Verify your host supports TUN devices. Run `ls -l /dev/net/tun`.
- **Check Docker Capabilities:** Ensure `cap_add: [NET_ADMIN, NET_RAW]` is present in `docker-compose.yml`.
- **Check Auth Key:** If using `TS_AUTHKEY`, make sure the key has not expired in your Tailscale admin console.

### 2. Tailscale Funnel Notice: "Funnel not allowed" or "node not authorized"
- Verify that **HTTPS Certificates** are enabled in [Tailscale Admin Console → DNS](https://login.tailscale.com/admin/dns).
- Verify that the **`funnel`** attribute is added to `nodeAttrs` in [Tailscale Admin Console → Access Controls](https://login.tailscale.com/admin/acls):
  ```json
  "nodeAttrs": [
    {
      "target": ["autogroup:members", "*"],
      "attr": ["funnel"]
    }
  ]
  ```

### 3. Cannot Access `https://bom.ratfish-regulus.ts.net` from the Internet
- Confirm container is running and healthy: `docker compose ps`
- Confirm Tailscale node is online: `docker compose exec bom tailscale status`
- Check Funnel status: `docker compose exec bom tailscale funnel status`
- If needed, re-run: `docker compose exec bom tailscale funnel --bg --yes 8000`

### 4. Port 8000 Conflict on Host
If port 8000 is already in use by another service on your host:
Change the host port mapping in `docker-compose.yml`:
```yaml
ports:
  - "8080:8000"   # Maps host port 8080 to container port 8000
```
*(Note: Tailscale Funnel always routes directly through the internal container network, so changing host port mappings does not break Funnel!)*
