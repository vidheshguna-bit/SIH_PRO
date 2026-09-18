"""
Test suite verifying /api/lens-detect real-time Google Lens hover detection
and multi-panel /api/audit without mocks.
"""
import os
import base64
import unittest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

class TestLensAndAudit(unittest.TestCase):
    def setUp(self):
        self.samples_dir = os.path.join(os.path.dirname(__file__), "samples")
        self.compliant_path = os.path.join(self.samples_dir, "sample_compliant.png")
        self.missing_grievance_path = os.path.join(self.samples_dir, "sample_missing_grievance.png")
        self.illegal_units_path = os.path.join(self.samples_dir, "sample_illegal_units.png")

    def test_lens_detect_compliant(self):
        with open(self.compliant_path, "rb") as f:
            file_bytes = f.read()
        res = client.post("/api/lens-detect-file", files={"file": ("compliant.png", file_bytes, "image/png")})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("detected_declarations", data)
        self.assertIn("missing_declarations", data)
        self.assertIn("raw_text", data)
        self.assertGreater(len(data["raw_text"]), 10)
        self.assertNotIn("Fresh Farm Atta", data["raw_text"])

        # Check detected rules
        detected_keys = [d["key"] for d in data["detected_declarations"]]
        self.assertIn("rule_6_1_e_mrp", detected_keys)
        self.assertIn("rule_6_1_c_net_quantity", detected_keys)

    def test_lens_detect_missing_grievance(self):
        with open(self.missing_grievance_path, "rb") as f:
            file_bytes = f.read()
        res = client.post("/api/lens-detect-file", files={"file": ("missing.png", file_bytes, "image/png")})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        missing_keys = [m["key"] for m in data["missing_declarations"]]
        self.assertIn("rule_6_1_da_consumer_grievance", missing_keys)
        self.assertEqual(data["overall_status"], "FAIL")

    def test_lens_detect_base64_payload(self):
        with open(self.compliant_path, "rb") as f:
            file_bytes = f.read()
        b64 = "data:image/png;base64," + base64.b64encode(file_bytes).decode("utf-8")
        res = client.post("/api/lens-detect", json={"image": b64})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["tokens_count"], 0)
        self.assertIn("audit_report", data)

    def test_audit_multipart_real_results(self):
        with open(self.compliant_path, "rb") as f:
            file_bytes = f.read()
        res = client.post("/api/audit", files={"files": ("compliant.png", file_bytes, "image/png")})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["overall_status"], "PASS")
        self.assertIn("full_extracted_text", data)
        self.assertNotIn("Fresh Farm Atta", data["full_extracted_text"])

if __name__ == "__main__":
    unittest.main()
