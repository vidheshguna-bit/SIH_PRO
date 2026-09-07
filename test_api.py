"""
FastAPI End-to-End API Suite for Legal Metrology Auditor
"""

import sys
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_root():
    print("[TEST] GET / (Static Index)...")
    res = client.get("/")
    assert res.status_code == 200
    assert "Legal Metrology" in res.text
    print("       -> OK (200)")

def test_sample_compliant():
    print("[TEST] GET /api/sample/compliant...")
    res = client.get("/api/sample/compliant")
    assert res.status_code == 200
    data = res.json()
    assert data["overall_status"] == "PASS"
    assert data["compliance_score"] == 100.0
    assert len(data["panels"]) == 1
    assert "image_b64" in data["panels"][0]
    print(f"       -> PASS: Score {data['compliance_score']}%, Ref: {data['inspection_id']}")

def test_sample_illegal_units():
    print("[TEST] GET /api/sample/illegal_units...")
    res = client.get("/api/sample/illegal_units")
    assert res.status_code == 200
    data = res.json()
    rep = data["audit_report"]
    assert rep["rule_6_1_c_net_quantity"]["is_illegal_symbol"] == True
    print(f"       -> OK: Correctly detected illegal unit '{rep['rule_6_1_c_net_quantity']['detected_unit']}'")

def test_sample_mismatched_usp():
    print("[TEST] GET /api/sample/mismatched_usp...")
    res = client.get("/api/sample/mismatched_usp")
    assert res.status_code == 200
    data = res.json()
    rep = data["audit_report"]
    assert rep["rule_6_1_11_unit_sale_price"]["math_consistent"] == False
    print(f"       -> OK: Correctly caught math error (Expected: {rep['rule_6_1_11_unit_sale_price']['expected_usp']}, Declared: {rep['rule_6_1_11_unit_sale_price']['declared_usp']})")

def test_pdf_export():
    print("[TEST] POST /api/export-pdf...")
    res_sample = client.get("/api/sample/compliant")
    sample_data = res_sample.json()
    
    payload = {
        "inspection_id": sample_data["inspection_id"],
        "commodity_name": "Biscuits",
        "overall_status": sample_data["overall_status"],
        "compliance_score": sample_data["compliance_score"],
        "grade": sample_data["compliance_grade"],
        "report": sample_data["audit_report"]
    }
    
    res = client.post("/api/export-pdf", json=payload)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert len(res.content) > 1000
    print(f"       -> OK: Generated valid PDF Certificate ({len(res.content)} bytes)")

if __name__ == "__main__":
    print("=" * 60)
    print("Running FastAPI Integration & Endpoint Verification")
    print("=" * 60)
    test_root()
    test_sample_compliant()
    test_sample_illegal_units()
    test_sample_mismatched_usp()
    test_pdf_export()
    print("=" * 60)
    print("ALL API ENDPOINTS VERIFIED & FUNCTIONAL!")
    print("=" * 60)
