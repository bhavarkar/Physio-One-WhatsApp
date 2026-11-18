# Hostinger Ubuntu Linux VPS Deployment Guide

**Platform:** Physio One WhatsApp AI Platform (Single Organization Edition)  
**Target Host:** Hostinger Ubuntu Linux VPS (Ubuntu 22.04 LTS or 24.04 LTS)  
**Hardware Specifications:** 4 GB RAM, 50 GB SSD, 1-2 vCPU  
**Deployment Architecture:** Docker Compose with Caddy Reverse Proxy & Automated HTTPS  

---

## 1. Architecture Overview

The Hostinger VPS deployment bundles the complete single-organization WhatsApp AI platform into a private, resource-constrained container network managed by Docker Compose and reverse-proxied by Caddy.

```text
                                  Internet
                                     |
                                  HTTPS (Ports 80 & 443)
                                     |
                     +-------------------------------+
                     |      Caddy Reverse Proxy      |
                     |  (Automated Let's Encrypt)    |
                     +---------------+---------------+
                                     |
               +---------------------+---------------------+
               |                                           |
      http://frontend:3000                        http://api:8000
    (Next.js App Router UI)                     (FastAPI REST Endpoints)
               |                                           |
               +---------------------+---------------------+
                                     |
                    Private Docker Network (physio_vps_network)
                                     |
               +---------------------+---------------------+
               |                                           |
      http://postgres:5432                    Continuous Async Daemon
     (PostgreSQL 16 + pgvector)             (app.workers.runner Daemon)
```

### Key Security Invariants
1. **Zero Direct Database Exposure:** PostgreSQL port 5432 is strictly bound to `physio_vps_network` and is **never published** to the host or internet.
2. **Zero Direct Application Exposure:** Next.js (port 3000) and FastAPI (port 8000) are internal container ports; external access must pass through Caddy reverse proxy.
3. **Public Ports:** Only ports `80` (HTTP redirect) and `443` (HTTPS) are open to the internet.
4. **Automated HTTPS:** Caddy obtains and renews TLS certificates automatically from Let's Encrypt or ZeroSSL.

---

## 2. Resource Budget (4 GB RAM / 50 GB SSD)

### 2.1 Memory (RAM) Allocation Plan

| Component | Minimum Reservation | Hard Memory Limit | CPU Limit | Purpose & Tuning |
|---|---|---|---|---|
| **PostgreSQL 16 + pgvector** | 300 MB | **800 MB** | 1.0 vCPU | `shared_buffers=128MB`, `work_mem=4MB`, `max_connections=50`. pgvector cosine index searches. |
| **FastAPI Backend (API)** | 300 MB | **600 MB** | 1.0 vCPU | REST API, webhook signature verification, JWT session auth, tool execution dispatch. |
| **Worker Daemon (`runner.py`)** | 200 MB | **500 MB** | 0.8 vCPU | Continuous polling sweeps (15s): automations, inactivity check-ins, campaign legal hours, inbound debounce. |
| **Next.js Frontend Dashboard** | 200 MB | **400 MB** | 1.0 vCPU | Prerendered static React pages, server-side `/api/*` rewrite proxy. |
| **Caddy Reverse Proxy** | 50 MB | **100 MB** | 0.5 vCPU | TLS termination, HTTP/2 & HTTP/3, security headers, gzip/zstd compression. |
| **Total Container Limits** | **1,050 MB** | **2,400 MB (2.4 GB)** | | **Leaves 1,600 MB (1.6 GB / 40%) unallocated headroom for Linux OS, page cache, Docker daemon, and temporary migration jobs.** |

### 2.2 Disk Storage Budget (50 GB SSD)

| Item | Estimated Consumption | Notes |
|---|---|---|
| **Ubuntu Linux OS & System Packages** | 5–8 GB | Base system, security updates, kernel images. |
| **Docker Engine & Image Cache** | 4–6 GB | Multi-stage builder layers, base images (`node:20-alpine`, `python:3.11-slim`). |
| **Production Application Images** | 2–3 GB | `physio-one-frontend:vps`, `physio-one-api:vps`, `pgvector:pg16`, `caddy:2.8-alpine`. |
| **PostgreSQL Data Volume (`postgres_data`)** | 2–5 GB | Relational tables, HNSW vector embeddings, appointment history. |
| **Media & Audio Storage (`media_storage`)** | 3–5 GB | WhatsApp voice-notes, patient documents, broadcast images. |
| **Local Backups (`/opt/physio/backups`)** | 2–4 GB | 7 daily compressed `.sql.gz` backups (automatic rotation). |
| **Docker Container Logs** | < 150 MB | Capped via json-file logging driver: `max-size: "10m"`, `max-file: "3"`. |
| **Total Projected Consumption** | **18–31 GB** | **Leaves 19–32 GB (38–64%) free disk headroom.** |

---

## 3. Ubuntu Host Security Hardening Checklist

Before deploying the container stack on the Hostinger VPS, complete the following hardening steps:

### 3.1 Non-Root User & Sudo Access
```bash
# Connect as root initially
ssh root@YOUR_VPS_IP

# Create dedicated administrative user
adduser physioadmin
usermod -aG sudo physioadmin
```

### 3.2 SSH Key Authentication & Password Disablement
```bash
# On your local machine: copy SSH key to VPS
ssh-copy-id -i ~/.ssh/id_ed25519.pub physioadmin@YOUR_VPS_IP

# On VPS: test login as physioadmin before disabling passwords
ssh physioadmin@YOUR_VPS_IP

# Edit SSH configuration
sudo nano /etc/ssh/sshd_config
# Set the following parameters:
#   PermitRootLogin no
#   PasswordAuthentication no
#   PubkeyAuthentication yes
#   X11Forwarding no

sudo systemctl restart ssh
```

### 3.3 UFW Firewall Configuration
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```
*(Confirms that only SSH, HTTP 80, and HTTPS 443 are accessible externally; PostgreSQL 5432 remains blocked).*

### 3.4 Fail2ban Intrusion Prevention
```bash
sudo apt-get update && sudo apt-get install -y fail2ban
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo systemctl enable --now fail2ban
```

### 3.5 Automated Security Updates
```bash
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

### 3.6 Docker & Docker Compose v2 Installation
```bash
# Install Docker official repository
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Grant physioadmin permissions to run docker
sudo usermod -aG docker physioadmin
# Log out and log back in for group change to take effect
```

---

## 4. Domain & DNS Configuration

Before launching Caddy, create the following DNS A record in your domain registrar / DNS provider:

| Record Type | Host / Name | Target Value | TTL |
|---|---|---|---|
| **A** | `app` (or `@` for apex) | `YOUR_HOSTINGER_VPS_IP` | 300 seconds (5 min) |

*Verification:*
```bash
dig +short app.yourdomain.com
# Must return your Hostinger VPS public IP address before starting Caddy
```

---

## 5. Deployment Step-by-Step Walkthrough

### Step 1: Clone Repository on VPS
```bash
sudo mkdir -p /opt/physio
sudo chown -R physioadmin:physioadmin /opt/physio
git clone https://github.com/organization/physio-one-whatsapp.git /opt/physio/app
cd /opt/physio/app/deploy/vps
```

### Step 2: Configure Environment Secrets
```bash
cp .env.example .env
chmod 600 .env

# Generate high-entropy secrets:
DB_PASS=$(openssl rand -hex 24)
APP_SEC=$(openssl rand -hex 32)
JWT_SEC=$(openssl rand -hex 32)
WRK_TOK=$(openssl rand -hex 24)

# Edit .env and insert generated secrets + your domain name:
nano .env
```

### Step 3: Run Pre-flight Verification
```bash
chmod +x scripts/*.sh
./scripts/preflight.sh
```

### Step 4: Staging Deployment (Mock Outbound Mode)
```bash
# Deploys with safe staging isolation (mock outbound, read-only appointments, draft-only campaigns):
./scripts/deploy.sh --staging
```

### Step 5: Verify Deployment Health
```bash
./scripts/verify.sh
```

### Step 6: Initial Clinic Owner Setup
Open your browser and navigate to `https://app.yourdomain.com/setup` (or execute via curl):
```bash
curl -X POST https://app.yourdomain.com/api/v1/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "director@physioone.com",
    "password": "StrongPassword2026#",
    "full_name": "Clinic Director"
  }'
```
*Verify that a second setup call is immediately rejected with HTTP 403 Forbidden.*

---

## 6. Database Backups & Disaster Recovery

### 6.1 Automated Backup Cron
Add a daily backup cron under user `physioadmin`:
```bash
crontab -e
# Add the following entry (runs daily at 02:00 AM IST):
0 2 * * * /opt/physio/app/deploy/vps/scripts/backup.sh >> /var/log/physio-backup.log 2>&1
```

### 6.2 Off-Server Replication Recommendation
To safeguard against physical VPS hardware failure, replicate the encrypted backup archives off-server:
```bash
# Example: rsync encrypted backups to an external SFTP / storage server
rsync -avz -e ssh /opt/physio/backups/ backupuser@backup.storage.com:/vault/physio-backups/
```

### 6.3 Point-in-Time Database Restoration
```bash
./scripts/restore.sh /opt/physio/backups/physio_backup_YYYYMMDD_HHMMSS.sql.gz --confirm-restore
```

---

## 7. Rollback Procedure

If an application defect is discovered after a software update:
```bash
./scripts/rollback.sh --confirm
```
*Note:* The rollback script restores container images to previous stable tags and verifies health. It **never automatically downgrades database schemas**, protecting clinical data integrity.

---

## 8. Estimated Capacity & System Limits

On a 4 GB RAM Hostinger VPS, the single-organization platform comfortably supports:
- **Active Clinic Staff:** 15–25 simultaneous dashboard operators.
- **Conversations:** 5,000–10,000 monthly active patient WhatsApp dialogues.
- **Webhook Ingestion Rate:** 20–30 messages per second burst capacity.
- **Database Capacity:** Up to ~500,000 historical messages and vector embeddings before requiring disk expansion.
