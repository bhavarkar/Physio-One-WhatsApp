# Hostinger Ubuntu Linux VPS Preflight Inspection Checklist (Read-Only)

**Target Host:** Hostinger Ubuntu Linux VPS (Target specs: 4 GB RAM, 50 GB SSD)  
**Security Invariant:** Read-only diagnostics ONLY. Do NOT modify the server, delete data, or change network configuration during preflight.  
**Assumption Warning:** Never assume the VPS is empty. Verify existing workloads, listening ports, Docker networks, and databases before running any deployment commands.

---

## 1. Operating System & Hardware Inspection

Run the following non-mutating commands to record baseline system metrics:

```bash
# 1.1 Ubuntu Version & Kernel
lsb_release -a
uname -r
cat /etc/os-release

# Criteria: Ubuntu 22.04 LTS (Jammy) or Ubuntu 24.04 LTS (Noble) with Linux 5.15+ or 6.x

# 1.2 CPU Architecture & Cores
lscpu | grep -E "Model name|CPU\(s\):|Thread\(s\) per core|Core\(s\) per socket"

# Criteria: Minimum 1 vCPU (Recommended: 2 vCPU)

# 1.3 Total & Available System Memory (RAM)
free -m
cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree"

# Criteria: MemTotal >= 3800 MB (~4 GB VPS tier). MemAvailable >= 2500 MB prior to deployment.

# 1.4 Storage Capacity & Free Disk Space
df -hT /
lsblk

# Criteria: Root filesystem >= 40 GB total, with at least 15 GB free disk space available.
```

---

## 2. Docker Engine & Container Runtimes

```bash
# 2.1 Docker CLI & Daemon Status
docker --version
docker info

# Criteria: Docker Engine v24.0+ active and healthy.

# 2.2 Docker Compose v2 Plugin
docker compose version

# Criteria: Docker Compose v2.20+ installed as a Docker CLI plugin (`docker compose`, NOT legacy `docker-compose`).

# 2.3 Existing Containers & Active Workloads (Non-Empty Host Check)
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"

# Criteria: Document all existing containers. If non-physio services are present, ensure port and network isolation.

# 2.4 Existing Volumes & Networks
docker volume ls
docker network ls

# Criteria: Verify no naming collision with `physio_postgres_data`, `physio_media_storage`, or `physio_vps_network`.
```

---

## 3. Network, Port Exposure & Firewall Audit

```bash
# 3.1 Listening TCP/UDP Ports on Host
sudo ss -tuln
# or
sudo netstat -tuln

# Criteria:
# - Ports 80 and 443 must NOT be bound by pre-existing web servers (Apache, Nginx, LiteSpeed).
# - Port 5432 must NOT be bound on 0.0.0.0 or public interface.
# - Port 22 (or custom SSH port) must be active.

# 3.2 UFW Firewall Status & Rules
sudo ufw status verbose

# Criteria:
# - Default incoming: deny
# - Default outgoing: allow
# - Permitted incoming: 22/tcp (or SSH port), 80/tcp, 443/tcp
# - Blocked: 5432, 8000, 3000, and any other internal ports

# 3.3 Fail2ban & Intrusion Prevention
sudo systemctl status fail2ban --no-pager
sudo fail2ban-client status
```

---

## 4. SSH & Access Security

```bash
# 4.1 SSH Server Configuration
sudo sshd -T | grep -E "permitrootlogin|passwordauthentication|pubkeyauthentication|port"

# Criteria:
# - PermitRootLogin no
# - PasswordAuthentication no
# - PubkeyAuthentication yes

# 4.2 Sudo Permissions for Non-Root Operator
groups $USER
sudo -n true && echo "Sudo access OK without password prompt" || echo "Sudo requires password"
```

---

## 5. DNS Resolution & Domain Routing

```bash
# 5.1 Public A Record Propagation
dig +short app.yourdomain.com
nslookup app.yourdomain.com

# Criteria: Returned IP must match the Hostinger VPS public IPv4 address.

# 5.2 Outbound DNS Resolution
getent hosts registry-1.docker.io
getent hosts acme-v02.api.letsencrypt.org

# Criteria: Must resolve external Docker registries and Let's Encrypt ACME endpoints without timeouts.
```

---

## 6. Storage Directories, Permissions & Backup Destinations

```bash
# 6.1 Application Directory Check
ls -ld /opt/physio/app 2>/dev/null || echo "Directory does not yet exist (will be created)"

# Criteria: Owned by non-root deployment user (`physioadmin:physioadmin`).

# 6.2 Backup Directory
ls -ld /opt/physio/backups 2>/dev/null || echo "Backup directory will be created by backup.sh (chmod 700)"

# Criteria: Permission 700, sufficient disk space (> 10 GB reserved for local backup rotation).

# 6.3 Off-Server Backup Target Accessibility
# Verify external SFTP / storage credentials or SSH key readiness for offsite replication.
```

---

## 7. Preflight Verification Summary Sheet

| Item | Verified Value | Pass / Fail | Notes |
|---|---|---|---|
| OS Version | | | Ubuntu 22.04 / 24.04 LTS required |
| vCPU Count | | | >= 1 vCPU |
| Total RAM | | | >= 3.8 GB |
| Available RAM | | | >= 2.5 GB free |
| Free Disk Space | | | >= 15 GB free on root mount |
| Docker Engine | | | >= v24.0.0 |
| Docker Compose | | | >= v2.20.0 |
| Existing Containers | | | None conflicting |
| Port 80 Available | | | Must be free for Caddy |
| Port 443 Available | | | Must be free for Caddy |
| Port 5432 Blocked | | | Must NOT be public |
| UFW Status | | | Active, incoming denied |
| SSH Key Auth | | | Root/password login disabled |
| DNS A Record | | | Points to VPS public IP |
| Outbound DNS | | | Docker Hub & Let's Encrypt resolve |
| Deployment Dir | | | `/opt/physio/app` ready |
