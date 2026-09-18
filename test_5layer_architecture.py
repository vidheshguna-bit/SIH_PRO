"""
Unit test suite verifying the 5-layer state-of-the-art packaging inspection architecture:
1. CV Preprocessing (OpenCV CLAHE + Bilateral Filter + Canny + Glare Suppression)
2. Fast OCR Detection (RapidOCR ONNX Runtime with Latency & Confidence Gating)
3. High-Fidelity Fallback (Vision-Language Models: Qwen 2.5-VL / Gemini 2.5 Flash)
4. Entity Extraction & Typo Repair (GLiNER + RapidFuzz)
5. Statutory Auditing (Pydantic + Exact Python Decimal Arithmetic)
"""
import sys
import os
import unittest
from decimal import Decimal
import numpy as np

# Import layers
from ocr_engine import (
    preprocess_image,
    detect_canny_edges,
    suppress_glare,
    extract_text_from_image,
    run_ocr_with_metadata,
)
from vlm_fallback import VLMFallbackEngine
from entity_extractor import RapidFuzzRepairEngine, GLiNERPackagingExtractor
from statutory_auditor import (
    PackagingDeclarationModel,
    MRPAuditModel,
    NetQuantityAuditModel,
    USPAuditModel,
    StatutoryComplianceAuditResult,
    verify_unit_sale_price,
    audit_packaging_declaration,
)
from rule_engine import verify_packaging_compliance


class TestLayer1CVPreprocessing(unittest.TestCase):
    """Layer 1: OpenCV CLAHE + Bilateral Filter + Canny Edge Detection + Glare Suppression."""

    def setUp(self):
        # Synthetic image (100x100, 3 channels)
        self.synthetic_img = np.full((100, 100, 3), 180, dtype=np.uint8)
        # Contrast square to test Canny edges
        self.synthetic_img[30:70, 30:70] = 30

    def test_canny_edge_detection(self):
        edges = detect_canny_edges(self.synthetic_img, low_threshold=80, high_threshold=180)
        self.assertIsNotNone(edges)
        self.assertEqual(edges.shape, (100, 100))
        self.assertGreater(np.sum(edges > 0), 50)

    def test_clahe_and_bilateral_preprocessing(self):
        preprocessed = preprocess_image(self.synthetic_img)
        self.assertIsNotNone(preprocessed)
        self.assertEqual(preprocessed.shape, (100, 100, 3))
        self.assertEqual(preprocessed.dtype, np.uint8)

    def test_glare_suppression_localized(self):
        glare_img = self.synthetic_img.copy()
        glare_img[40:50, 40:50] = 255
        suppressed = suppress_glare(glare_img)
        self.assertIsNotNone(suppressed)
        self.assertEqual(suppressed.shape, (100, 100, 3))

    def test_glare_suppression_ignores_full_white_label(self):
        white_label = np.full((100, 100, 3), 255, dtype=np.uint8)
        result = suppress_glare(white_label)
        np.testing.assert_array_equal(result, white_label)


class TestLayer2FastOCR(unittest.TestCase):
    """Layer 2: Fast OCR Detection with Latency & Confidence Gating."""

    def test_ocr_metadata_structure(self):
        img = np.full((80, 200, 3), 255, dtype=np.uint8)
        metadata = run_ocr_with_metadata(img)
        
        self.assertIn("raw_text", metadata)
        self.assertIn("boxes", metadata)
        self.assertIn("latency_ms", metadata)
        self.assertIn("mean_confidence", metadata)
        self.assertIn("needs_vlm_fallback", metadata)
        self.assertIn("ocr_engine", metadata)
        self.assertGreaterEqual(metadata["latency_ms"], 0.0)
        self.assertIsInstance(metadata["needs_vlm_fallback"], bool)


class TestLayer3VLMFallback(unittest.TestCase):
    """Layer 3: High-Fidelity Fallback with Vision-Language Models."""

    def setUp(self):
        self.vlm_engine = VLMFallbackEngine()

    def test_vlm_offline_fallback(self):
        img = np.full((100, 100, 3), 255, dtype=np.uint8)
        res = self.vlm_engine.extract_declarations_vlm(img, "MRP Rs. 250.00 incl. of all taxes Net Qty: 500 g")
        
        self.assertIn("vlm_engine", res)
        self.assertIn("extracted_fields", res)
        self.assertIn("mrp", res["extracted_fields"])
        self.assertEqual(res["extracted_fields"]["mrp"], "250.00")
        self.assertEqual(res["extracted_fields"]["net_quantity"], "500 g")

    def test_vlm_trigger_decision(self):
        self.assertTrue(self.vlm_engine.should_trigger_fallback(0.45, 10))
        self.assertTrue(self.vlm_engine.should_trigger_fallback(0.85, 1))
        self.assertFalse(self.vlm_engine.should_trigger_fallback(0.88, 8))


class TestLayer4EntityExtractionAndTypoRepair(unittest.TestCase):
    """Layer 4: Zero-Shot Entity Extraction & RapidFuzz Typo Repair."""

    def setUp(self):
        self.fuzz = RapidFuzzRepairEngine()
        self.gliner = GLiNERPackagingExtractor()

    def test_rapidfuzz_tax_clause_repair(self):
        # OCR typo: "1ncl. of all taxes"
        has_taxes, phrase = self.fuzz.repair_tax_clause("MRP Rs 150 (1ncl. of all taxes)")
        self.assertTrue(has_taxes)
        self.assertIn("taxes", phrase)

    def test_rapidfuzz_telephone_ocr_typo_repair(self):
        # OCR typo: "180O-267-89OO" (letter 'O' instead of digit '0')
        repaired = self.fuzz.repair_phone_digits("Helpline: 180O-267-89OO")
        self.assertIn("1800", repaired)
        self.assertNotIn("180O", repaired)

    def test_rapidfuzz_metric_unit_normalization(self):
        std_unit, is_illegal = self.fuzz.fuzzy_match_unit("gms")
        self.assertEqual(std_unit, "g")
        self.assertTrue(is_illegal)

        std_unit, is_illegal = self.fuzz.fuzzy_match_unit("g")
        self.assertEqual(std_unit, "g")
        self.assertFalse(is_illegal)

        std_unit, is_illegal = self.fuzz.fuzzy_match_unit("ltr")
        self.assertEqual(std_unit, "l")
        self.assertTrue(is_illegal)

    def test_gliner_zero_shot_extraction(self):
        raw_text = (
            "Manufactured by: Nestlé India Ltd.\n"
            "Net Weight: 400 g\n"
            "MRP: Rs. 180.00 (inclusive of all taxes)\n"
            "USP: Rs. 0.45 / g\n"
            "Customer Care: care@nestle.com or 1800 103 1947\n"
            "Mfg Date: 03/2024\n"
            "Expiry Date: 03/2025\n"
        )
        entities = self.gliner.extract_entities(raw_text)
        self.assertIsNotNone(entities.get("mrp"))
        self.assertEqual(entities["mrp"], 180.0)
        self.assertIsNotNone(entities.get("net_quantity"))
        self.assertEqual(entities["net_quantity"], 400.0)
        self.assertEqual(entities.get("consumer_email"), "care@nestle.com")


class TestLayer5StatutoryAuditing(unittest.TestCase):
    """Layer 5: Pydantic + Python Decimal Exact Symbolic Auditing."""

    def test_decimal_usp_exact_arithmetic(self):
        # MRP 180.00, Qty 400 g -> 180.00 / 400 = 0.45
        valid, expected_usp, reason = verify_unit_sale_price(
            mrp_val=Decimal("180.00"),
            net_qty_val=Decimal("400"),
            net_qty_unit="g",
            declared_usp_val=Decimal("0.45"),
            declared_usp_unit="g",
        )
        self.assertTrue(valid)
        self.assertEqual(expected_usp, Decimal("0.45"))

    def test_decimal_usp_mismatch_detected(self):
        # Declared USP is 0.50, but expected is 0.45
        valid, expected_usp, reason = verify_unit_sale_price(
            mrp_val=Decimal("180.00"),
            net_qty_val=Decimal("400"),
            net_qty_unit="g",
            declared_usp_val=Decimal("0.50"),
            declared_usp_unit="g",
        )
        self.assertFalse(valid)
        self.assertEqual(expected_usp, Decimal("0.45"))
        self.assertIn("MISMATCH", reason)

    def test_decimal_usp_rounding_half_up(self):
        # 100 / 3 = 33.333... -> 33.33
        valid, expected_usp, reason = verify_unit_sale_price(
            mrp_val=Decimal("100.00"),
            net_qty_val=Decimal("3"),
            net_qty_unit="kg",
            declared_usp_val=Decimal("33.33"),
            declared_usp_unit="kg",
        )
        self.assertTrue(valid)
        self.assertEqual(expected_usp, Decimal("33.33"))

    def test_pydantic_packaging_declaration_validation(self):
        model = PackagingDeclarationModel(
            mrp=Decimal("250.00"),
            has_tax_clause=True,
            net_quantity=Decimal("500"),
            standard_unit="g",
            declared_usp=Decimal("0.50"),
            usp_unit_denominator="g",
            mfg_date="01/2024",
            consumer_phone="1800-267-8900",
            consumer_email="care@haldirams.com",
            manufacturer="Haldiram Snacks Pvt Ltd",
            country_of_origin="India"
        )
        audit_res = audit_packaging_declaration(model)
        self.assertIsInstance(audit_res, StatutoryComplianceAuditResult)
        self.assertEqual(audit_res.overall_status, "PASS")
        self.assertEqual(audit_res.compliance_score, 100.0)
        self.assertEqual(audit_res.audit_report["rule_6_1_11_unit_sale_price"]["status"], "COMPLIANT")


class TestEndToEndRuleEngineIntegration(unittest.TestCase):
    """Verifying integration of RapidFuzz and Decimal auditing inside RuleEngine."""

    def test_rule_engine_repaired_tax_clause_and_decimal_usp(self):
        ocr_text = (
            "Manufactured by: Haldiram Snacks Pvt Ltd, Sector 62 Noida 201301\n"
            "Namkeen - Bhujia\n"
            "Net Qty: 400 g\n"
            "MRP Rs. 180.00 (1ncl. of all taxes)\n"
            "USP: Rs. 0.45 / g\n"
            "Customer Care: 180O-267-89OO or support@haldirams.com\n"
            "Mfg: 01/2024 Exp: 01/2025\n"
        )
        result = verify_packaging_compliance(ocr_text)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["score"], 100)
        self.assertEqual(len(result["violations"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
