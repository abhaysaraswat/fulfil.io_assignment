#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting FastAPI + Celery on Render Free Tier"
echo "================================================"

# Check if REDIS_URL is set
if [ -z "$REDIS_URL" ]; then
    echo "❌ ERROR: REDIS_URL environment variable not set!"
    echo "Please add REDIS_URL in Render Dashboard > Environment Variables"
    exit 1
fi

echo "✅ REDIS_URL configured"
echo "🔄 Starting Celery worker in background..."

# Start Celery worker with limited concurrency (free tier has low resources)
celery -A app.tasks.celery_app worker \
    --loglevel=info \
    --concurrency=1 \
    --max-tasks-per-child=50 \
    &

# Store the Celery PID
CELERY_PID=$!
echo "✅ Celery worker started (PID: $CELERY_PID)"

echo "🌐 Starting FastAPI web server on port $PORT..."

# Start FastAPI (this runs in foreground)
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers 1

# If uvicorn stops, kill the Celery worker too
kill $CELERY_PID 2>/dev/null || true
