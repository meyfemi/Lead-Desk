#!/usr/bin/env bash
# Launch the Lead Desk dashboard.
cd "$(dirname "$0")" || exit 1
exec python3 ui/server.py "$@"
