"""invoice-api: a small demo service for the self-service platform lab.

It is deliberately simple. What matters is that it follows the platform
contract: it listens on one port, answers /healthz, and exposes /metrics.
"""
import os
import random
import socket
import time
import uuid

from flask import Flask, Response, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

SERVICE = os.getenv("SERVICE_NAME", "invoice-api")
VERSION = os.getenv("APP_VERSION", "dev")
HEALTHY = os.getenv("HEALTHY", "true").lower() == "true"
INSTANCE = socket.gethostname()

app = Flask(__name__)

# Golden-signal metrics. "path" uses the route template (e.g. /invoices/<invoice_id>)
# rather than the raw URL, so label cardinality stays small.
REQUESTS = Counter("app_requests_total", "HTTP requests handled", ["method", "path", "status"])
LATENCY = Histogram(
    "app_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
INVOICES_CREATED = Counter("invoices_created_total", "Invoices created (business metric)")
APP_INFO = Gauge("app_info", "Build information", ["version"])
APP_INFO.labels(VERSION).set(1)

# Chaos settings let you rehearse incidents (see docs/WALKTHROUGH.md, step 8).
chaos = {"error_rate": 0.0, "extra_latency_ms": 0}
invoices = {}

UNTRACKED = {"/metrics", "/healthz"}
CHAOS_PATHS = {"/invoices", "/invoices/<invoice_id>"}


@app.before_request
def before():
    g.start = time.perf_counter()
    rule = request.url_rule.rule if request.url_rule else None
    if rule in CHAOS_PATHS:
        if chaos["extra_latency_ms"]:
            time.sleep(chaos["extra_latency_ms"] / 1000)
        if random.random() < chaos["error_rate"]:
            return jsonify(error="injected failure (chaos mode)"), 500
    return None


@app.after_request
def after(resp):
    path = request.url_rule.rule if request.url_rule else "unmatched"
    if path not in UNTRACKED:
        REQUESTS.labels(request.method, path, str(resp.status_code)).inc()
        LATENCY.labels(request.method, path).observe(time.perf_counter() - g.start)
    resp.headers["X-Served-By"] = INSTANCE
    return resp


@app.get("/")
def index():
    return jsonify(service=SERVICE, version=VERSION, instance=INSTANCE)


@app.get("/healthz")
def healthz():
    if not HEALTHY:
        return jsonify(status="unhealthy", version=VERSION), 500
    return jsonify(status="ok", version=VERSION)


@app.get("/invoices")
def list_invoices():
    return jsonify(invoices=list(invoices.values()), count=len(invoices))


@app.post("/invoices")
def create_invoice():
    body = request.get_json(silent=True) or {}
    amount = body.get("amount")
    if not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify(error="amount must be a positive number"), 400
    invoice = {
        "id": uuid.uuid4().hex[:8],
        "customer": body.get("customer", "unknown"),
        "amount": amount,
        "currency": body.get("currency", "NGN"),
        "created_by_instance": INSTANCE,
    }
    invoices[invoice["id"]] = invoice
    INVOICES_CREATED.inc()
    return jsonify(invoice), 201


@app.get("/invoices/<invoice_id>")
def get_invoice(invoice_id):
    invoice = invoices.get(invoice_id)
    if invoice is None:
        return jsonify(error="not found"), 404
    return jsonify(invoice)


@app.post("/chaos")
def set_chaos():
    body = request.get_json(silent=True) or {}
    chaos["error_rate"] = max(0.0, min(1.0, float(body.get("error_rate", 0))))
    chaos["extra_latency_ms"] = max(0, int(body.get("extra_latency_ms", 0)))
    return jsonify(instance=INSTANCE, chaos=chaos)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
