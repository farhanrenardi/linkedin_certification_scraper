#!/bin/bash

# Start Chromium in headless mode with remote debugging
echo "🚀 Starting Chromium DevTools on port 9222..."
chromium --headless \
  --no-sandbox \
  --disable-gpu \
  --disable-dev-shm-usage \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome_debug_profile &

# Wait for Chromium to start
sleep 3

# Check if Chromium is running
if netstat -tuln 2>/dev/null | grep -q :9222; then
  echo "✅ Chromium DevTools ready on localhost:9222"
else
  echo "⚠️  Chromium DevTools may not be responding, continuing anyway..."
fi

# Start Uvicorn
echo "🚀 Starting Uvicorn server on port 8000..."
exec uvicorn app:app --host 0.0.0.0 --port 8000
