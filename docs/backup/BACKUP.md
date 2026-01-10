# GOFR Backup System

Shared backup infrastructure for all GOFR microservices.

## Overview

The backup system provides automated, zero-downtime backups for all GOFR projects (gofr-plot, gofr-doc, gofr-iq, gofr-np, etc.) with:

- ✅ **Zero Downtime** - Backups run without stopping services
- ✅ **Shared Infrastructure** - One backup solution for all GOFR projects
- ✅ **Parameterized Configuration** - Project-specific settings via environment variables
- ✅ **Retention Policies** - Age and count-based cleanup
- ✅ **Verification** - Automatic integrity checking
- ✅ **Compression** - Configurable compression (gzip/bzip2/xz)
- ✅ **Tiered Storage** - Daily/weekly/monthly retention tiers

## Architecture

### Components in gofr-common

```
gofr-common/
├── src/gofr_common/backup/
│   ├── __init__.py
│   ├── config.py          # Parameterized configuration
│   ├── service.py         # Main orchestrator
│   ├── housekeeping.py    # Retention and cleanup
│   └── verify.py          # Integrity verification
├── docker/backup/
│   ├── Dockerfile         # Shared backup image
│   └── entrypoint.sh
└── scripts/backup/
    ├── backup_now.sh      # Manual backup trigger
    ├── list_backups.sh    # List all backups
    └── restore_backup.sh  # Restore from backup
```

### Backup Manifest

The system maintains a `manifest.json` file in the root of the backup directory. This file tracks:
- Backup filenames and paths
- Creation timestamps
- File sizes
- Verification status
- Tier information (daily/weekly/monthly)

This manifest is used by the housekeeping and verification processes to manage the backup lifecycle efficiently.

Additionally, a `.sha256` checksum file is generated for each backup archive to ensure data integrity. This file is used during the verification process.

### Integration Pattern

Each GOFR project has:
1. **docker-compose.yml** - Backup service configuration
2. **scripts/** - Wrapper scripts that call shared gofr-common scripts
3. **Docker volumes** - Data volume (read-only) + backup volume (read-write)

## Quick Start

### 1. Build Shared Backup Image

```bash
cd /path/to/gofr-common
docker build -f docker/backup/Dockerfile -t gofr-common-backup:latest .
```

### 2. Add Backup Service to Your Project

Add to your project's `docker-compose.yml`:

```yaml
services:
  # ... your existing services ...

  backup:
    image: gofr-common-backup:latest
    container_name: gofr-{PROJECT}-backup  # e.g., gofr-plot-backup
    restart: unless-stopped
    depends_on:
      - mcp
      - web
    environment:
      # Project identifier (REQUIRED)
      - GOFR_PROJECT={project}  # e.g., plot, doc, iq
      
      # Backup scheduling
      - GOFR_{PROJECT}_BACKUP_ENABLED=${GOFR_{PROJECT}_BACKUP_ENABLED:-true}
      - GOFR_{PROJECT}_BACKUP_SCHEDULE=${GOFR_{PROJECT}_BACKUP_SCHEDULE:-0 2 * * *}
      
      # Retention policies
      - GOFR_{PROJECT}_BACKUP_RETENTION_DAYS=${GOFR_{PROJECT}_BACKUP_RETENTION_DAYS:-30}
      - GOFR_{PROJECT}_BACKUP_MAX_COUNT=${GOFR_{PROJECT}_BACKUP_MAX_COUNT:-90}
      
      # What to backup (paths relative to /data)
      - GOFR_{PROJECT}_BACKUP_PATHS=${GOFR_{PROJECT}_BACKUP_PATHS:-storage:storage,auth:auth,logs:../logs}
      
      # Compression
      - GOFR_{PROJECT}_BACKUP_COMPRESSION=${GOFR_{PROJECT}_BACKUP_COMPRESSION:-gzip}
      - GOFR_{PROJECT}_BACKUP_COMPRESSION_LEVEL=${GOFR_{PROJECT}_BACKUP_COMPRESSION_LEVEL:-6}
      
      # Housekeeping
      - GOFR_{PROJECT}_BACKUP_CLEANUP_ON_START=${GOFR_{PROJECT}_BACKUP_CLEANUP_ON_START:-true}
      - GOFR_{PROJECT}_BACKUP_VERIFY_AFTER_BACKUP=${GOFR_{PROJECT}_BACKUP_VERIFY_AFTER_BACKUP:-true}
    volumes:
      - gofr_{project}_data:/data:ro              # Read-only access to app data
      - gofr_{project}_backups:/backups:rw        # Write access to backups
    networks:
      - gofr-net

volumes:
  gofr_{project}_data:
    name: gofr-{project}_data
  gofr_{project}_backups:
    name: gofr-{project}_backups
```

### 3. Create Wrapper Scripts

Create wrapper scripts in your project's `scripts/` directory:

**scripts/backup_now.sh**:
```bash
#!/bin/bash
export GOFR_PROJECT={project}  # e.g., plot, doc, iq
export GOFR_BACKUP_CONTAINER=gofr-{project}-backup
export GOFR_DATA_VOLUME=gofr-{project}_data

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_BACKUP_DIR="${SCRIPT_DIR}/../../gofr-common/scripts/backup"

exec "${COMMON_BACKUP_DIR}/$(basename "$0")" "$@"
```

Copy this pattern for `list_backups.sh` and `restore_backup.sh`.

### 4. Start Backup Service

```bash
docker-compose up -d backup
docker-compose logs -f backup
```

## Configuration

All configuration via environment variables with project-specific prefixes.

### Project Identifier

**Required**: `GOFR_PROJECT` - Identifies which GOFR project (plot, doc, iq, etc.)

### Scheduling

```bash
# Enable/disable backups
GOFR_{PROJECT}_BACKUP_ENABLED=true

# Cron schedule (minute hour day month weekday)
GOFR_{PROJECT}_BACKUP_SCHEDULE="0 2 * * *"  # Daily at 2 AM
```

**Common Schedules**:
- Daily at 2 AM: `0 2 * * *`
- Every 6 hours: `0 */6 * * *`
- Weekly on Sunday: `0 3 * * 0`
- Twice daily: `0 2,14 * * *`

### Retention Policies

```bash
# Days to keep backups
GOFR_{PROJECT}_BACKUP_RETENTION_DAYS=30

# Maximum number of backups
GOFR_{PROJECT}_BACKUP_MAX_COUNT=90
```

### Backup Paths

Specify what to backup as comma-separated `name:path` pairs:

```bash
# Default for most projects
GOFR_{PROJECT}_BACKUP_PATHS="storage:storage,auth:auth,logs:../logs"

# Custom paths
GOFR_IQ_BACKUP_PATHS="data:.,logs:../logs,embeddings:embeddings"
```

Paths are relative to `/data` mount point.

### Compression

```bash
# Algorithm: gzip (fast), bzip2 (medium), xz (slow/best), none
GOFR_{PROJECT}_BACKUP_COMPRESSION=gzip

# Level: 1-9 (higher = better compression, slower)
GOFR_{PROJECT}_BACKUP_COMPRESSION_LEVEL=6
```

### Tiered Retention (Optional)

```bash
GOFR_{PROJECT}_BACKUP_ENABLE_WEEKLY=true
GOFR_{PROJECT}_BACKUP_WEEKLY_RETENTION_WEEKS=8

GOFR_{PROJECT}_BACKUP_ENABLE_MONTHLY=true
GOFR_{PROJECT}_BACKUP_MONTHLY_RETENTION_MONTHS=12
```

## Usage

### Manual Backup

```bash
cd /path/to/gofr-{project}
./scripts/backup_now.sh [tier]  # tier: daily (default), weekly, monthly
```

### List Backups

```bash
./scripts/list_backups.sh
```

Output shows all backups by tier with size, age, and verification status.

### Restore Backup

```bash
# Interactive mode (select from list)
./scripts/restore_backup.sh --interactive

# Restore specific backup
./scripts/restore_backup.sh gofr-plot_daily_20251213_020000.tar.gz

# Restore latest backup
./scripts/restore_backup.sh --latest
```

**Important**: Stop services before restore:
```bash
docker-compose stop mcp mcpo web
./scripts/restore_backup.sh --interactive
docker-compose restart mcp mcpo web
```

## Project-Specific Examples

### gofr-plot

```yaml
environment:
  - GOFR_PROJECT=plot
  - GOFR_PLOT_BACKUP_ENABLED=true
  - GOFR_PLOT_BACKUP_SCHEDULE=0 2 * * *
  - GOFR_PLOT_BACKUP_PATHS=storage:storage,auth:auth,logs:../logs
volumes:
  - gofr_data:/data:ro
  - gofr_backups:/backups:rw
```

### gofr-doc

```yaml
environment:
  - GOFR_PROJECT=doc
  - GOFR_DOC_BACKUP_ENABLED=true
  - GOFR_DOC_BACKUP_SCHEDULE=0 2 * * *
  - GOFR_DOC_BACKUP_PATHS=storage:storage,auth:auth,logs:../logs
volumes:
  - gofr_doc_data:/data:ro
  - gofr_doc_backups:/backups:rw
```

### gofr-iq

```yaml
environment:
  - GOFR_PROJECT=iq
  - GOFR_IQ_BACKUP_ENABLED=true
  - GOFR_IQ_BACKUP_SCHEDULE=0 2 * * *
  - GOFR_IQ_BACKUP_PATHS=data:.,logs:../logs
volumes:
  - gofr_iq_data:/data:ro
  - gofr_iq_backups:/backups:rw
```

## Monitoring

### View Logs

```bash
docker-compose logs -f backup
```

### Check Status

```bash
docker-compose ps backup
```

### Backup Statistics

```bash
./scripts/list_backups.sh
```

## Development

### Adding Backup to a New GOFR Project

1. **Update docker-compose.yml** - Add backup service
2. **Create wrapper scripts** - backup_now.sh, list_backups.sh, restore_backup.sh
3. **Set environment variables** - Project-specific configuration
4. **Build shared image** - `docker build -f gofr-common/docker/backup/Dockerfile ...`
5. **Test** - Manual backup, list, restore

### Customizing Backup Paths

Each project can specify custom paths via `GOFR_{PROJECT}_BACKUP_PATHS`:

```bash
# Include everything in data directory
GOFR_PROJECT_BACKUP_PATHS="all:."

# Specific subdirectories
GOFR_PROJECT_BACKUP_PATHS="models:models,config:config,cache:cache"

# Mix of files and directories
GOFR_PROJECT_BACKUP_PATHS="db:database.db,logs:logs,config:config.json"
```

## Best Practices

1. **Test Restores Regularly** - Verify backups are functional
2. **Monitor Disk Usage** - Ensure adequate backup volume space
3. **Off-Site Backups** - Periodically copy backup volume externally
4. **Keep Verification Enabled** - `VERIFY_AFTER_BACKUP=true`
5. **Document Recovery Procedures** - Test and document restore process
6. **Appropriate Retention** - Balance storage cost vs. recovery needs

## Security

- Backup service runs as non-privileged user
- Read-only mount of application data
- Checksums ensure integrity
- Separate backup volume
- No network ports exposed

## Performance

- Minimal impact (runs during low-usage hours)
- Read-only access (no locking)
- Configurable compression (balance speed vs. size)

## Troubleshooting

### Backup Service Not Starting
1. Check logs: `docker-compose logs backup`
2. Verify `GOFR_PROJECT` environment variable is set.
3. Verify `gofr_{project}_data` and `gofr_{project}_backups` volumes exist.
4. Ensure gofr-common is up to date: `cd lib/gofr-common && git pull`

### Backups Not Running
1. Check `GOFR_{PROJECT}_BACKUP_ENABLED=true`
2. Verify cron schedule format
3. View next scheduled run in logs
4. Test manual backup: `./scripts/backup_now.sh`

### Backup Verification Failed
- Check disk space on the backup volume.
- Verify the integrity of the source files (are they locked?).
- Check logs for specific error messages during the verification step.

### "No data found to backup"
- Verify `GOFR_{PROJECT}_BACKUP_PATHS` is correct.
- Ensure paths are relative to the `/data` mount point inside the container.
- Check if the source directories actually contain files.

### Restore Fails
1. Verify backup integrity first (automatic during restore)
2. Stop services before restoring
3. Check disk space
4. Review logs

## Support

For issues or questions:
1. Check service logs
2. Verify configuration
3. Test manual operations
4. Review this documentation
5. Check gofr-common repository for updates
