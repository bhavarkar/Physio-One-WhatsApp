# Physio One Host Nginx Virtual Host Setup & Integration Guide

**Host Infrastructure:** Hostinger Ubuntu 24.04.5 LTS VPS  
**Coexistence Context:** Coexists safely alongside existing `n8n.dataagent.in` on host Nginx (ports 80 & 443).  
**Security Invariant:** Zero modification to existing Nginx virtual hosts. Clean rollback path.

---

## 1. Overview

Host Nginx acts as the primary reverse proxy for all external web traffic on ports 80 and 443:
- `n8n.dataagent.in` $\rightarrow$ existing n8n Docker container (untouched)
- `physio.dataagent.in` $\rightarrow$ Physio One platform:
  - `/api/*`, `/health`, `/docs` $\rightarrow$ FastAPI backend container on `127.0.0.1:8000`
  - `/` (all other routes) $\rightarrow$ Next.js frontend container on `127.0.0.1:3000`

---

## 2. DNS Requirement

Before requesting an SSL certificate, add a DNS **A record** with your DNS provider:

| Record Type | Host / Name | Target IP | TTL |
|---|---|---|---|
| **A** | `physio` | `YOUR_HOSTINGER_VPS_IP` | 300 seconds |

*Verification:*
```bash
dig +short physio.dataagent.in
# Must return your Hostinger VPS public IPv4 address
```

---

## 3. Step-by-Step Operator Installation

### Step 1: Copy Configuration to Nginx
```bash
# From the repository root on the VPS:
sudo cp /opt/physio/app/deploy/vps/nginx/physio.conf /etc/nginx/sites-available/physio.conf

# Edit domain if different from physio.dataagent.in:
sudo nano /etc/nginx/sites-available/physio.conf
```

### Step 2: Obtain SSL Certificate via Certbot
Run Certbot in `--nginx` mode (which uses the existing Nginx server on port 80 without disrupting n8n):
```bash
sudo certbot --nginx -d physio.dataagent.in
```
*Note: Certbot will automatically issue certificates to `/etc/letsencrypt/live/physio.dataagent.in/`.*

### Step 3: Enable the Site
```bash
sudo ln -sf /etc/nginx/sites-available/physio.conf /etc/nginx/sites-enabled/
```

### Step 4: Validate Nginx Configuration (Safety Gate)
**Always** test the configuration syntax before reloading:
```bash
sudo nginx -t
```
*Output must report:*
```text
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### Step 5: Gracefully Reload Nginx
```bash
sudo systemctl reload nginx
```
*(A reload is zero-downtime and will NOT terminate or restart active n8n sessions).*

---

## 4. Emergency Rollback Procedure

If any issue occurs with Nginx routing:
```bash
# 1. Unlink the Physio virtual host
sudo rm -f /etc/nginx/sites-enabled/physio.conf

# 2. Test Nginx syntax
sudo nginx -t

# 3. Reload Nginx to return to pure n8n routing
sudo systemctl reload nginx
```
`n8n.dataagent.in` remains 100% operational throughout.
