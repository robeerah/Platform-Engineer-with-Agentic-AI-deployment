#!/usr/bin/env bash
# Inject (or clear) failures on EVERY instance of a service.
# Instances are looked up in Consul — the same registry the platform uses.
# Usage: scripts/chaos.sh <service> <error_rate 0..1> [extra_latency_ms]
SERVICE="${1:-invoice-api}"
RATE="${2:-0.5}"
LATENCY="${3:-0}"
INSTANCES=$(curl -s "http://127.0.0.1:8500/v1/health/service/${SERVICE}" \
  | jq -r '.[].Service | "\(.Address):\(.Port)"')
if [ -z "$INSTANCES" ]; then
  echo "No instances of $SERVICE found in Consul"; exit 1
fi
for addr in $INSTANCES; do
  echo -n "$addr → "
  curl -s -X POST -H 'Content-Type: application/json' \
       -d "{\"error_rate\": $RATE, \"extra_latency_ms\": $LATENCY}" "http://$addr/chaos"
  echo
done
