# SignalScope AI — Production Deployment Guide

This guide covers deploying SignalScope AI to production. Because SignalScope consists of a Next.js frontend, a FastAPI backend, Celery workers processing RF recordings from a shared volume, PostgreSQL, Redis, and an optional local Gemma 4 AI analyst, **Docker Compose on a Linux VM/VPS is the fastest, most reliable, and recommended deployment method.**

---

## Architecture Overview

```text
               Internet (HTTPS :443)
                         │
                         ▼
        ┌───────────────────────────────────┐
        │   Reverse Proxy (Caddy / Nginx)   │
        │   - Automatic Let's Encrypt SSL   │
        │   - Domain routing & compression │
        └──────────────┬────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌──────────────────┐       ┌───────────────────┐
│ Next.js Web UI   │       │ FastAPI Backend   │
│ (:3000)          │       │ (:8000)           │
└──────────────────┘       └─────────┬─────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
┌──────────────────┐       ┌───────────────────┐       ┌───────────────────┐
│ PostgreSQL 16    │       │ Redis 7           │       │ Celery DSP Worker │
│ (:5432)          │       │ (:6379)           │       │ (reads /data)     │
└──────────────────┘       └───────────────────┘       └─────────┬─────────┘
                                                                 │
         ┌───────────────────────────────────────────────────────┘
         ▼ (optional)
┌───────────────────────────────┐
│ Gemma 4 AI Sidecar (:8100)    │
│ - Local offline inference     │
│ - Optional NVIDIA GPU support │
└───────────────────────────────┘
```

---

## Method 1: Docker Compose on a Linux VPS (Recommended)

### 1. Server Sizing Recommendations

| Profile | Specs | Recommended Providers |
|---|---|---|
| **Standard (No GPU, Fake/Light AI)** | 4 vCPU, 8 GB RAM, 50 GB SSD | Hetzner CPX31 (~€14/mo), DigitalOcean Droplet ($48/mo), AWS `t3.xlarge` |
| **GPU Accelerated (Gemma 4 E4B-it)** | 4+ vCPU, 16 GB RAM, 1x NVIDIA GPU (>= 8 GB VRAM: RTX 3060, T4, A10G) | RunPod, Lambda Labs, Vast.ai, AWS `g4dn.xlarge` (~$0.52/hr) |

---

### 2. Initial Server Setup (Ubuntu 22.04 / 24.04 LTS)

SSH into your server and install Docker with Compose:

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose plugin
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Log out and log back in for docker group to take effect, or run:
newgrp docker

# Verify installation
docker compose version
```

If using a **GPU server** for Gemma 4:
```bash
# Install NVIDIA Container Toolkit
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

---

### 3. Clone and Configure SignalScope

```bash
# Clone the repository
git clone https://github.com/Manas-Dikshit/SignalScope.git /opt/signalscope
cd /opt/signalscope

# Create production environment file
cp .env.example .env
```

Generate secure production secrets:
```bash
# Generate a 64-character hex secret for JWT signing
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate a strong database password
python3 -c "import secrets; print(secrets.token_urlsafe(24))"

# Generate an internal API token for the DSP tools route
python3 -c "import secrets; print(secrets.token_hex(24))"
```

Edit `/opt/signalscope/.env` with your production values:

```dotenv
# Security (REQUIRED)
SECRET_KEY=<paste_generated_jwt_secret>
INTERNAL_API_TOKEN=<paste_generated_internal_token>

# Database Credentials
POSTGRES_USER=signalscope_admin
POSTGRES_PASSWORD=<paste_generated_db_password>
POSTGRES_DB=signalscope_prod

DATABASE_URL=postgresql+asyncpg://signalscope_admin:<paste_generated_db_password>@postgres:5432/signalscope_prod
DATABASE_URL_SYNC=postgresql://signalscope_admin:<paste_generated_db_password>@postgres:5432/signalscope_prod

# Domain and CORS
# Replace with your actual domain name:
CORS_ORIGINS=https://signalscope.yourdomain.com

# Storage Limits (200 MB max upload)
MAX_UPLOAD_BYTES=209715200

# Optional Gemma 4 AI Analyst configuration
AI_ENABLED=true
AI_BACKEND=fake                # Set to 'transformers' if running with GPU/PyTorch
AI_MODEL=google/gemma-4-E4B-it
```

Configure frontend environment:
```bash
# Create web env
cp apps/web/.env.example apps/web/.env.production
```
Edit `apps/web/.env.production`:
```dotenv
NEXT_PUBLIC_API_URL=https://signalscope.yourdomain.com
```

---

### 4. Configure Reverse Proxy with Automatic SSL (Caddy)

Caddy handles automatic HTTPS provisioning and renewal through Let's Encrypt with zero maintenance.

Install Caddy:
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Create `/etc/caddy/Caddyfile`:
```caddy
signalscope.yourdomain.com {
    # Increase upload limit for 200MB RF captures
    request_body {
        max_size 250MB
    }

    # Route API and Swagger Docs to FastAPI
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle /docs* {
        reverse_proxy localhost:8000
    }
    handle /openapi.json {
        reverse_proxy localhost:8000
    }

    # Route everything else to Next.js Web UI
    handle {
        reverse_proxy localhost:3000
    }
}
```

Restart Caddy:
```bash
sudo systemctl reload caddy
```

---

### 5. Launch the Production Stack

```bash
cd /opt/signalscope

# For standard deployment (PostgreSQL, Redis, API, Worker, Next.js):
docker compose up --build -d

# OR if you are including the local Gemma 4 AI Analyst sidecar:
docker compose --profile ai up --build -d
```

Verify all containers are healthy:
```bash
docker compose ps
```

You should see:
```text
NAME                     STATUS                   PORTS
signalscope-postgres-1   Up (healthy)             127.0.0.1:5432->5432/tcp
signalscope-redis-1      Up (healthy)             127.0.0.1:6379->6379/tcp
signalscope-api-1        Up (healthy)             0.0.0.0:8000->8000/tcp
signalscope-worker-1     Up (healthy)             
signalscope-web-1        Up (healthy)             0.0.0.0:3000->3000/tcp
signalscope-ai-1         Up (healthy)             0.0.0.0:8100->8100/tcp (if profile ai enabled)
```

Database migrations execute automatically on container boot via `alembic upgrade head` in `docker/entrypoint-api.sh`.

---

## Method 2: Systemd Auto-Start on Boot

To ensure SignalScope automatically resumes after server reboots:

Create `/etc/systemd/system/signalscope.service`:
```ini
[Unit]
Description=SignalScope AI Production Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/signalscope
ExecStart=/usr/bin/docker compose --profile ai up -d
ExecStop=/usr/bin/docker compose --profile ai down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable signalscope.service
```

---

## Method 3: Platform as a Service (Railway / Render)

If deploying to a PaaS without full Docker Compose:

1. **Managed Database & Redis**:
   - Create a PostgreSQL 16 database and Redis 7 instance via the provider dashboard.
2. **API Service (`services/api`)**:
   - Dockerfile: `docker/Dockerfile.api`
   - Set environment variables (`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, etc.).
   - Attach a persistent storage volume mounted at `/data`.
3. **Worker Service (`services/dsp-worker`)**:
   - Dockerfile: `docker/Dockerfile.worker`
   - Point to the same `DATABASE_URL`, `REDIS_URL`, and **mount the same persistent volume at `/data`**.
4. **Web UI (`apps/web`)**:
   - Dockerfile: `docker/Dockerfile.web`
   - Set `NEXT_PUBLIC_API_URL` to the public URL of your API service.

---

## Operational Maintenance

### Viewing Service Logs
```bash
# View live logs of all services
docker compose logs -f

# View live logs of API or Worker specifically
docker compose logs -f api
docker compose logs -f worker
```

### Performing Updates
To pull new changes and perform zero-downtime rolling reload:
```bash
cd /opt/signalscope
git pull origin main
docker compose --profile ai build
docker compose --profile ai up -d --no-deps api worker web
```

### Backups
Back up PostgreSQL database:
```bash
docker compose exec postgres pg_dump -U signalscope_admin signalscope_prod > backup_$(date +%Y%m%d).sql
```

Back up uploaded signal recordings:
```bash
tar -czvf signalscope_uploads_$(date +%Y%m%d).tar.gz /var/lib/docker/volumes/signalscope_uploads_data/_data
```
