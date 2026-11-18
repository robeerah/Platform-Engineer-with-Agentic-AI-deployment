import app as service


def client():
    service.chaos.update(error_rate=0.0, extra_latency_ms=0)
    service.invoices.clear()
    return service.app.test_client()


def test_healthz_ok():
    resp = client().get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_create_and_fetch_invoice():
    c = client()
    created = c.post("/invoices", json={"customer": "Ada Stores", "amount": 25000})
    assert created.status_code == 201
    invoice_id = created.get_json()["id"]
    fetched = c.get(f"/invoices/{invoice_id}")
    assert fetched.status_code == 200
    assert fetched.get_json()["amount"] == 25000


def test_rejects_bad_amount():
    resp = client().post("/invoices", json={"amount": -5})
    assert resp.status_code == 400


def test_metrics_exposed_with_route_template_labels():
    c = client()
    c.get("/invoices/abc123")
    body = c.get("/metrics").get_data(as_text=True)
    assert "app_requests_total" in body
    assert 'path="/invoices/<invoice_id>"' in body
    assert "abc123" not in body  # raw IDs must never become labels


def test_chaos_injects_errors():
    c = client()
    c.post("/chaos", json={"error_rate": 1.0})
    assert c.get("/invoices").status_code == 500
    c.post("/chaos", json={"error_rate": 0})
    assert c.get("/invoices").status_code == 200
