#!/usr/bin/env bash
# Steady traffic through the gateway (~4 req/s, under the rate limit).
# Usage: scripts/load.sh [host] [seconds]
HOST="${1:-invoice.localtest.me}"
DURATION="${2:-300}"
URL="http://127.0.0.1:9080"
END=$(( $(date +%s) + DURATION ))
echo "Sending traffic to $HOST for ${DURATION}s (Ctrl+C to stop)…"
while [ "$(date +%s)" -lt "$END" ]; do
  curl -s -o /dev/null -H "Host: $HOST" "$URL/invoices" &
  curl -s -o /dev/null -H "Host: $HOST" -H 'Content-Type: application/json' \
       -d "{\"customer\":\"cust-$RANDOM\",\"amount\":$(( RANDOM % 90000 + 1000 ))}" "$URL/invoices" &
  sleep 0.5
done
wait
echo "Done."
