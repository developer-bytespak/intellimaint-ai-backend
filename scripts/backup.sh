#!/bin/bash
# Backup database and S3 data

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/${TIMESTAMP}"

echo "Creating backup directory: ${BACKUP_DIR}"
mkdir -p "${BACKUP_DIR}"

# Backup PostgreSQL database
echo "Backing up database..."
pg_dump $DATABASE_URL > "${BACKUP_DIR}/database.sql"

# Backup S3 bucket (if AWS CLI is configured)
echo "Backing up S3 data..."
aws s3 sync s3://intellimaint-media "${BACKUP_DIR}/s3_data"

echo "Backup completed: ${BACKUP_DIR}"

