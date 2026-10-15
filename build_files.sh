#!/bin/bash
# OpenSourceLens Build Script
# In modern Vercel deployments, Python dependencies are automatically installed from requirements.txt
# by Vercel's managed Python runtime.
# Manual package installation is omitted to comply with PEP 668 and prevent 'externally-managed-environment' errors.
set -e

echo "=== Building OpenSourceLens for Vercel Deployment ==="

# Collect static assets into staticfiles directory
echo "Collecting static assets..."
python3 manage.py collectstatic --noinput --clear

echo "=== Build Completed Successfully ==="
