#!/bin/bash
set -euo pipefail

LABEL="com.minail.reputation-agent.daily"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST_PATH"

echo "Removed $LABEL"
