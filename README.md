# Uptime Monitor

Simple site availability monitoring via ping. Checks sites every minute and logs results.

## Quick Start

**With Docker Compose (recommended):**
```bash
git clone https://github.com/yuspax/uptime-monitor.git
docker-compose up -d

# View logs
docker-compose logs -f
```

**Local (without Docker):**
```bash
git clone https://github.com/yuspax/uptime-monitor.git
cd uptime-monitor
python app.py
```

## What It Does

Checks site availability every minute and saves results to `logs/ping_log.txt`:

```
[2025-11-29 20:45:00] google.com: UP
[2025-11-29 20:45:00] facebook.com: UP
[2025-11-29 20:45:00] github.com: UP
[2025-11-29 20:45:00] goooogle.com: DOWN
```

## Configuration

Edit the sites list in `app.py`:

```python
sites = ["google.com", "facebook.com", "github.com"]
```

Then restart:

```bash
docker-compose restart  # or just restart the script locally
```

## Useful Commands

**Docker:**
```bash
docker-compose up -d          # Start
docker-compose down           # Stop
docker-compose logs -f        # View logs
docker-compose restart        # Restart
```

**Local:**
```bash
python app.py                 # Run directly
```

## Structure

```
uptime-monitor/
├── app.py              # Main script
├── Dockerfile          # Docker image
├── docker-compose.yml  # Docker config
└── logs/               # Logs (auto-created)
    └── ping_log.txt
```
