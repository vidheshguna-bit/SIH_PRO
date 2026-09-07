"""
Unit and Integration Test for Legal Metrology OCR & Rule Engine Pipeline
"""

import os
import sys
from ocr_engine import OCREngine
from rule_engine import LegalMetrologyRuleEngine

def run_tests():
    ocr = OCREngine()
    rule_engine = LegalMetrologyRuleEngine()

    base_dir = os.path.dirname(__file__)
    samples_dir = os.path.join(base_dir, "samples")

    samples = [
        ("sample_compliant.png", "PASS", "Fully compliant biscuit label"),
        ("sample_illegal_units.png", ["WARNING", "FAIL"], "Illegal 'gms' unit & missing taxes"),
        ("sample_mismatched_usp.png", "FAIL", "Arithmetic mismatch in Unit Sale Price"),
        ("sample_missing_grievance.png", "FAIL", "Missing Grievance and Mfg Date")
    ]

    print("=" * 60)
    print(f"Running Legal Metrology Pipeline Verification (Engine: {ocr.engine_type})")
    print("=" * 60)

    for filename, expected_status, description in samples:
        filepath = os.path.join(samples_dir, filename)
        assert os.path.exists(filepath), f"File not found: {filepath}"

        print(f"\n[TEST] Processing {filename} ({description})...")
        ocr_result = ocr.process(filepath)
        print(f"       Extracted {ocr_result['token_count']} tokens, {ocr_result['line_count']} lines.")
        
        audit_result = rule_engine.evaluate(ocr_result)
        status = audit_result["overall_status"]
        score = audit_result["compliance_score"]
        print(f"       Overall Status: {status} | Score: {score}% | Grade: {audit_result['compliance_grade']}")
        
        # Verify expectations
        if isinstance(expected_status, list):
            assert status in expected_status, f"Expected one of {expected_status}, got {status}"
        else:
            assert status == expected_status, f"Expected {expected_status}, got {status}"

        # Check rule details
        rep = audit_result["audit_report"]
        if filename == "sample_compliant.png":
            assert rep["rule_6_1_e_mrp"]["status"] == "COMPLIANT"
            assert rep["rule_6_1_c_net_quantity"]["status"] == "COMPLIANT"
            assert rep["rule_6_1_11_unit_sale_price"]["status"] == "COMPLIANT"
            print("       -> Rule 6(1)(e) MRP: COMPLIANT")
            print("       -> Rule 6(1)(c) Net Qty: COMPLIANT")
            print("       -> Rule 6(1)(11) USP Math: COMPLIANT")

        elif filename == "sample_illegal_units.png":
            assert rep["rule_6_1_c_net_quantity"]["is_illegal_symbol"] == True
            assert rep["rule_6_1_e_mrp"]["has_tax_clause"] == False
            print("       -> Correctly flagged illegal unit 'gms' under Rule 12(1)!")
            print("       -> Correctly flagged missing 'inclusive of all taxes' under Rule 6(1)(e)!")

        elif filename == "sample_mismatched_usp.png":
            assert rep["rule_6_1_11_unit_sale_price"]["math_consistent"] == False
            print("       -> Correctly flagged mathematical discrepancy in USP under Rule 6(1)(11)!")

    print("\n" + "=" * 60)
    print("ALL STATUTORY COMPLIANCE AUDIT TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
