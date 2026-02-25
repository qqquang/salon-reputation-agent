#!/bin/bash
# Local dev server for the dashboard
# Usage: ./serve.sh [port]
# Default port: 8080

PORT=${1:-8080}
DASHBOARD_DIR="$(dirname "$0")/dashboard"

echo ""
echo "  🚀 Dashboard running at http://localhost:$PORT"
echo "  📄 Login page:     http://localhost:$PORT/index.html"
echo "  📊 Dashboard:      http://localhost:$PORT/app.html"
echo ""
echo "  Press Ctrl+C to stop"
echo ""

cd "$DASHBOARD_DIR" && python3 -m http.server $PORT
