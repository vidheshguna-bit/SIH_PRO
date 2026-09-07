"""
Verification Suite for Multi-Panel, Bulk Audit, and Analytics Features
"""

import os
from fastapi.testclient import TestClient
from app import app, SAMPLES_DIR

client = TestClient(app)

def test_analytics_endpoints():
    print("[TEST] 1. Testing POST /api/analytics/demo...")
    res = client.post("/api/analytics/demo")
    assert res.status_code == 200, f"Failed: {res.text}"
    data = res.json()
    assert data["total_audited"] >= 12, f"Expected >=12 products, got {data['total_audited']}"
    assert "pass_rate" in data
    assert "defect_frequency" in data
    assert len(data["products"]) >= 12
    print(f"       -> OK: Loaded {data['total_audited']} products. Pass rate: {data['pass_rate']}%")

    print("[TEST] 2. Testing GET /api/analytics...")
    res = client.get("/api/analytics")
    assert res.status_code == 200
    data = res.json()
    assert data["total_audited"] >= 12
    assert "rule_6_1_e" in data["defect_frequency"]
    assert "rule_12_units" in data["defect_frequency"]
    print(f"       -> OK: Defect distribution verified. Total: {data['total_audited']}")

    print("[TEST] 3. Testing GET /api/analytics/export-csv...")
    res = client.get("/api/analytics/export-csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "Inspection Reference ID" in res.text
    print(f"       -> OK: CSV export generated ({len(res.text)} bytes)")

def test_bulk_audit_endpoint():
    print("[TEST] 4. Testing POST /api/audit/bulk with sample images...")
    sample1 = os.path.join(SAMPLES_DIR, "sample_compliant.png")
    sample2 = os.path.join(SAMPLES_DIR, "sample_illegal_units.png")
    sample3 = os.path.join(SAMPLES_DIR, "sample_mismatched_usp.png")

    files = [
        ("files", ("cookies.png", open(sample1, "rb"), "image/png")),
        ("files", ("chips.png", open(sample2, "rb"), "image/png")),
        ("files", ("ghee.png", open(sample3, "rb"), "image/png"))
    ]

    res = client.post("/api/audit/bulk", files=files)
    assert res.status_code == 200, f"Failed: {res.text}"
    batch = res.json()
    assert batch["total_processed"] == 3
    assert "batch_id" in batch
    assert len(batch["products"]) == 3
    print(f"       -> OK: Processed bulk batch of {batch['total_processed']} products. ID: {batch['batch_id']}")

    # Test retrieving one product from the batch by inspection_id
    sample_id = batch["products"][0]["inspection_id"]
    print(f"[TEST] 5. Testing GET /api/audit/product/{sample_id}...")
    res = client.get(f"/api/audit/product/{sample_id}")
    assert res.status_code == 200
    prod = res.json()
    assert prod["inspection_id"] == sample_id
    assert len(prod["panels"]) == 1
    assert "image_b64" in prod["panels"][0]
    print(f"       -> OK: Retrieved full product data for canvas rendering.")

def test_multi_panel_single_product():
    print("[TEST] 6. Testing multi-panel upload for single product (/api/audit)...")
    sample1 = os.path.join(SAMPLES_DIR, "sample_compliant.png")
    sample2 = os.path.join(SAMPLES_DIR, "sample_illegal_units.png")

    files = [
        ("files", ("panel_front.png", open(sample1, "rb"), "image/png")),
        ("files", ("panel_back.png", open(sample2, "rb"), "image/png"))
    ]

    res = client.post("/api/audit", files=files)
    assert res.status_code == 200, f"Failed: {res.text}"
    data = res.json()
    assert data["panels_count"] == 2
    assert len(data["panels"]) == 2
    print(f"       -> OK: Unified audit completed for 2 panels. Verdict: {data['overall_status']}")

if __name__ == "__main__":
    print("=" * 65)
    print("RUNNING MULTI-PANEL, BULK & ANALYTICS TEST SUITE")
    print("=" * 65)
    test_analytics_endpoints()
    test_bulk_audit_endpoint()
    test_multi_panel_single_product()
    print("=" * 65)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)
