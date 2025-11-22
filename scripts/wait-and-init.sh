#!/usr/bin/env bash
set -euo pipefail

# Wait until mongo1 is reachable, then run the JS to initiate the replica set.
MAX_TRIES=60
TRY=0

until mongo --host mongo1 --eval "print(\"ok\")" >/dev/null 2>&1; do
  TRY=$((TRY+1))
  if [ "$TRY" -ge "$MAX_TRIES" ]; then
    echo "Timed out waiting for mongo1"
    exit 1
  fi
  echo "Waiting for mongo1... ($TRY/$MAX_TRIES)"
  sleep 2
done

echo "mongo1 reachable, initiating replica set (if not already initiated)"
# Run the initialization script. If it's already initiated, ignore errors.
mongo --host mongo1 /scripts/init-replica.js || true

echo "Init script finished"
