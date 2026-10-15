#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "=== Building OpenSourceLens for Vercel Deployment ==="

# Install project dependencies
echo "Installing dependencies from requirements.txt..."
python3 -m pip install -r requirements.txt

# Collect static assets into staticfiles directory
echo "Collecting static assets..."
python3 manage.py collectstatic --noinput --clear

echo "=== Build Completed Successfully ==="
