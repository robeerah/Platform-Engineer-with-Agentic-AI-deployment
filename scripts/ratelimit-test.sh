#!/usr/bin/env bash
# Fire N requests as fast as possible and count status codes.
# With the default 300 req/60s limit, roughly the first 300 pass and the rest get 429.
HOST="${1:-invoice.localtest.me}"
N="${2:-400}"
echo "Sending $N rapid requests to $HOST…"
for i in $(seq 1 "$N"); do
  curl -s -o /dev/null -w "%{http_code}\n" -H "Host: $HOST" http://127.0.0.1:9080/invoices
done | sort | uniq -c | awk '{printf "  HTTP %s  x %s\n", $2, $1}'
