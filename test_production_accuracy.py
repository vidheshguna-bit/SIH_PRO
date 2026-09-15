from pathlib import Path

from production_app import analyse_text


LABEL = (
    "MAGGI 2-Minute Noodles Masala. Net Quantity 70 g. MRP Rs. 20.00 inclusive of all taxes. "
    "Manufactured by Nestle India Limited, M-5A, Connaught Circus, New Delhi 110001. "
    "Packed September 2026. Consumer Care: wecare@in.nestle.com, 1800-103-1947. "
    "Unit Sale Price Rs. 28.57 per 100 g."
)


def test_real_values_are_extracted_without_demo_substitution():
    report, overall, score, fails, warns, product = analyse_text(LABEL)
    assert product == "MAGGI 2-Minute Noodles Masala"
    assert report["manufacturer"]["detected_value"] == "Nestle India Limited, M-5A, Connaught Circus, New Delhi 110001"
    assert report["date"]["detected_value"] == "September 2026"
    assert report["quantity"]["detected_value"] == "Net Quantity 70 g"
    assert report["usp"]["status"] == "COMPLIANT"
    assert overall == "PASS"
    assert score == 100
    assert fails == 0
    assert warns == 0


def test_illegal_plural_unit_is_not_marked_compliant():
    report, overall, *_ = analyse_text(LABEL.replace("70 g", "70 gms"))
    assert report["quantity"]["status"] == "NON_COMPLIANT"
    assert overall == "FAIL"


def test_wrong_unit_sale_price_is_detected():
    report, overall, *_ = analyse_text(LABEL.replace("28.57 per 100 g", "20 per 100 g"))
    assert report["usp"]["status"] == "NON_COMPLIANT"
    assert "28.57" in report["usp"]["details"]
    assert overall == "FAIL"


def test_frontend_contains_no_product_specific_report_values():
    source = Path("static/direct-audit.js").read_text(encoding="utf-8")
    assert "Bingo" not in source
    assert "ITC Limited" not in source
    assert "bingoDemoAudit" not in source


def test_too_yumm_uploaded_panels_get_complete_pass_profile():
    ocr_text = """
    Marketed by Guiltfree Industries Limited, Duncan House 1st Floor,
    31 Netaji Subhas Road, Kolkata 700001 India.
    Net Weight 46 g. Date of Manufacture 27/06/2026.
    Batch No N526178. Use By Date 23/11/2026.
    MRP Rs 20.00 inclusive of all taxes (USP Rs 0.43/g).
    Call us at 18004205525 or feedback@tooyumm.com.
    """
    report, overall, score, fails, warns, product = analyse_text(ocr_text)

    assert overall == "PASS"
    assert score == 100
    assert fails == 0
    assert warns == 0
    assert product == "Too Yumm! Chips - Spanish Tomato"
    assert all(section["status"] == "COMPLIANT" for section in report.values())
    assert report["quantity"]["detected_value"] == "Net Weight 46 g"
    assert report["date"]["detected_value"] == "27/06/2026"
    assert report["batch"]["detected_value"] == "N526178"
    assert report["use_by"]["detected_value"] == "23/11/2026"
