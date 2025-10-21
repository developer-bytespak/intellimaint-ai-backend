#!/bin/bash
# Restore database and S3 data from backup

set -e

if [ -z "$1" ]; then
  echo "Usage: ./restore.sh <backup_directory>"
  exit 1
fi

BACKUP_DIR=$1

echo "Restoring from: ${BACKUP_DIR}"

# Restore PostgreSQL database
echo "Restoring database..."
psql $DATABASE_URL < "${BACKUP_DIR}/database.sql"

# Restore S3 bucket
echo "Restoring S3 data..."
aws s3 sync "${BACKUP_DIR}/s3_data" s3://intellimaint-media

echo "Restore completed!"

