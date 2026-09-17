"""Production OCR extraction hotfix for the SIH Legal Metrology prototype.

The deployed app uses browser-side Tesseract OCR. This module keeps the existing
API/UI contract but replaces fragile text parsing with label-aware extraction for
MRP, manufacturer/packer and manufacturing/packing date declarations.
"""

from __future__ import annotations

import re
import production_app


def _item(title, rule, status, value, details):
    return {
        "title": title,
        "rule": rule,
        "status": status,
        "detected_value": value,
        "details": details,
    }


def _norm_ocr(text: str) -> str:
    """Normalize common OCR punctuation/spacing errors without destroying values."""
    s = str(text or "")
    s = s.replace("₹", " ₹ ")
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _find_first(text: str, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.S)
        if m:
            return m
    return None


def _extract_mrp(text: str):
    # Handles: MRP 120, MRP: Rs.120, M.R.P. ₹ 120, MRP = 120/- and OCR spacing.
    patterns = [
        r"\bM\s*\.?\s*R\s*\.?\s*P\s*\.?\s*(?:[:=\-]|RS\.?|INR|₹)?\s*₹?\s*(\d+(?:\.\d{1,2})?)",
        r"\bMAX(?:IMUM)?\s+RETAIL\s+PRICE\s*(?:[:=\-]|RS\.?|INR|₹)?\s*₹?\s*(\d+(?:\.\d{1,2})?)",
        r"\bRETAIL\s+(?:SALE\s+)?PRICE\s*(?:[:=\-]|RS\.?|INR|₹)?\s*₹?\s*(\d+(?:\.\d{1,2})?)",
        r"\bRS\.?\s*[:=\-]?\s*₹?\s*(\d+(?:\.\d{1,2})?)\s*(?:/-)?",
        r"₹\s*(\d+(?:\.\d{1,2})?)\s*(?:/-)?",
    ]
    m = _find_first(text, patterns)
    if not m:
        return None, None
    try:
        value = float(m.group(1))
    except (ValueError, IndexError):
        return None, None
    if not 0.5 <= value <= 500000:
        return None, None
    return value, m.group(0).strip()


def _extract_tax_clause(text: str) -> bool:
    return bool(re.search(
        r"(?:incl(?:usive)?\.?\s*(?:of\s*)?(?:all\s*)?tax(?:es)?|inclusive\s+of\s+all\s+taxes)",
        text,
        re.I,
    ))


def _extract_manufacturer(text: str):
    # Keep this intentionally line-aware: it avoids treating 'MFD 08/2026'
    # as a manufacturer declaration.
    lines = [re.sub(r"\s+", " ", x).strip(" :-") for x in str(text).splitlines() if x.strip()]
    patterns = [
        r"\b(?:MANUFACTURED\s*(?:BY|AT)|MFD\s*BY|MANUFACTURER)\s*[:=\-]?\s*(.+)$",
        r"\b(?:PACKED\s*(?:BY|AT)|PKD\s*BY|PACKER)\s*[:=\-]?\s*(.+)$",
        r"\b(?:MARKETED\s*BY|IMPORTED\s*BY|DISTRIBUTED\s*BY)\s*[:=\-]?\s*(.+)$",
    ]
    for line in lines:
        for p in patterns:
            m = re.search(p, line, re.I)
            if m:
                value = m.group(1).strip(" .:-")
                if value and not re.fullmatch(r"(?:\d{1,2}[/-])?\d{2,4}", value):
                    return line, value

    # OCR sometimes removes the word BY and leaves a label followed by the name.
    m = _find_first(text, [
        r"\bMANUFACTURER\s*[:=]\s*([^\n]+)",
        r"\bPACKER\s*[:=]\s*([^\n]+)",
    ])
    if m:
        return m.group(0).strip(), m.group(1).strip()
    return None, None


def _extract_mfd_date(text: str):
    # Priority is MFD/MFG/PKD labels. This fixes the old parser which could
    # confuse a manufacturer line with a date and missed MM/YYYY in OCR text.
    month = r"(?:JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:T(?:EMBER)?)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)"
    date_value = r"(?:\d{1,2}[/-]\d{2,4}|\d{1,2}\.\d{2,4}|" + month + r"\s*[/-]?\s*\d{2,4}|\d{4}[/-]\d{1,2})"
    labelled = [
        rf"\b(?:MFD|MFG|PKD|PACKED\s*ON|DATE\s*OF\s*(?:MFG|MANUFACTURE|PACKING|PACKED))\b\s*[:=\-.]?\s*({date_value})",
        rf"\b(?:DATE\s*OF\s*(?:MANUFACTURE|PACKING|MFG|PKD))\b\s*[:=\-.]?\s*({date_value})",
    ]
    for p in labelled:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1).strip(), m.group(0).strip()

    # Standalone month/year is useful when OCR separates 'MFD' and the date.
    m = re.search(rf"\b(0?[1-9]|1[0-2])\s*[/-]\s*(20\d{{2}}|\d{{2}})\b", text, re.I)
    if m:
        return m.group(0).strip(), m.group(0).strip()
    m = re.search(rf"\b({month})\s*[/-]?\s*(20\d{{2}}|\d{{2}})\b", text, re.I)
    if m:
        return m.group(0).strip(), m.group(0).strip()
    return None, None


def _extract_quantity(text: str):
    patterns = [
        r"\bNET\s*(?:WT|WEIGHT|QTY|QUANTITY|CONTENTS?)?\s*[:=\-.]?\s*(\d+(?:\.\d+)?)\s*(kg|g|gm|gms|ml|l|ltr|litre|liter)\b",
        r"\b(\d+(?:\.\d+)?)\s*(kg|g|gm|gms|ml|l|ltr|litre|liter)\b",
    ]
    m = _find_first(text, patterns)
    return (m.group(0).strip() if m else None)


def _extract_care(text: str):
    phone = re.search(r"(?:\+91[\s-]?)?[6-9]\d{9}\b|\b1800[\s-]?\d{3}[\s-]?\d{3,4}\b", text, re.I)
    email = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    header = re.search(r"(?:CUSTOMER|CONSUMER)\s*CARE|HELPLINE|GRIEVANCE|COMPLAINT", text, re.I)
    if phone and email:
        return "COMPLIANT", f"Phone: {phone.group(0).strip()} | Email: {email.group(0).strip()}"
    if phone or email or header:
        return "WARNING", (phone.group(0).strip() if phone else email.group(0).strip() if email else "Contact section detected; verify details")
    return "NON_COMPLIANT", "Not detected"


def robust_analyse_text(text: str):
    raw = str(text or "")
    normalized = _norm_ocr(raw)
    compact = re.sub(r"\s+", " ", normalized).strip()

    mrp_value, mrp_match = _extract_mrp(compact)
    tax_ok = _extract_tax_clause(compact)
    manufacturer_line, manufacturer_value = _extract_manufacturer(raw)
    mfd_value, mfd_match = _extract_mfd_date(raw)
    quantity = _extract_quantity(compact)
    care_status, care_value = _extract_care(compact)

    product_match = re.search(r"\b(?:PRODUCT|NAME|COMMON\s+NAME)\s*[:=]\s*([^\n]+)", raw, re.I)
    if product_match:
        product_name = product_match.group(1).strip()[:80]
    else:
        # Prefer recognizable commodity words over MRP/date/administrative words.
        commodities = [
            "biscuits", "cookies", "wafers", "chips", "atta", "rice", "sugar", "salt",
            "tea", "coffee", "ghee", "butter", "milk", "noodles", "pasta", "detergent",
            "shampoo", "toothpaste", "spices", "namkeen", "bhujia", "chocolate", "oats"
        ]
        found = next((w for w in commodities if re.search(r"\b" + re.escape(w) + r"\b", compact, re.I)), None)
        product_name = found.title() if found else "Packaged Commodity"

    qty_ok = quantity is not None
    maker_ok = manufacturer_value is not None
    date_ok = mfd_value is not None
    mrp_ok = mrp_value is not None
    product_ok = product_name != "Packaged Commodity"

    report = {
        "product": _item(
            "Product Name", "Rule 6(1)(b)", "COMPLIANT" if product_ok else "WARNING",
            product_name if product_ok else "Not confidently detected",
            "Common/generic product identity should be clearly declared."
        ),
        "manufacturer": _item(
            "Manufacturer / Packer", "Rule 6(1)(a)", "COMPLIANT" if maker_ok else "NON_COMPLIANT",
            manufacturer_value if maker_ok else "Not detected",
            (f"Detected declaration: {manufacturer_line}" if maker_ok else "Manufacturer/packer/importer declaration was not detected.")
        ),
        "quantity": _item(
            "Net Quantity", "Rule 6(1)(c)", "COMPLIANT" if qty_ok else "NON_COMPLIANT",
            quantity or "Not detected",
            "Net quantity must use an approved standard unit."
        ),
        "mrp": _item(
            "MRP inclusive of taxes", "Rule 6(1)(e)",
            "COMPLIANT" if (mrp_ok and tax_ok) else ("WARNING" if mrp_ok else "NON_COMPLIANT"),
            (f"₹ {mrp_value:.2f}" if mrp_ok else "Not detected"),
            (f"Detected {mrp_match}; inclusive-of-all-taxes declaration: {'YES' if tax_ok else 'NO'}."
             if mrp_ok else "MRP declaration was not confidently detected.")
        ),
        "date": _item(
            "Manufacturing / Packing Date", "Rule 6(1)(d)", "COMPLIANT" if date_ok else "NON_COMPLIANT",
            mfd_value or "Not detected",
            (f"Detected label: {mfd_match}" if date_ok else "MFD/PKD month and year were not detected.")
        ),
        "care": _item(
            "Consumer Care Details", "Rule 6(1)(da)", care_status,
            care_value,
            "Consumer grievance/contact details should be present and legible."
        ),
        "usp": _item(
            "Unit Sale Price", "Rule 6(11)",
            "COMPLIANT" if re.search(r"(?:UNIT\s*SALE\s*PRICE|UNIT\s*PRICE|/\s*(?:100\s*)?(?:G|KG|ML|L))", compact, re.I) else "WARNING",
            "Detected" if re.search(r"(?:UNIT\s*SALE\s*PRICE|UNIT\s*PRICE|/\s*(?:100\s*)?(?:G|KG|ML|L))", compact, re.I) else "Not confidently detected",
            "Unit sale price is checked where applicable."
        ),
        "quality": _item(
            "OCR quality", "Evidence quality policy", "WARNING" if len(compact) < 80 else "COMPLIANT",
            f"{len(compact)} OCR characters",
            "Human review is recommended for unclear or incomplete label text."
        ),
    }

    statuses = [v["status"] for v in report.values()]
    fails = sum(s == "NON_COMPLIANT" for s in statuses)
    warns = sum(s == "WARNING" for s in statuses)
    passes = sum(s == "COMPLIANT" for s in statuses)
    score = round((passes + warns * 0.5) / max(1, len(statuses)) * 100)
    overall = "FAIL" if fails else ("WARNING" if warns else "PASS")
    return report, overall, score, fails, warns, product_name


try:
    from app import app
except Exception:
    app = production_app.app
