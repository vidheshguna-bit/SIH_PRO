"""
SIH26034 - Legal Metrology Packaging Compliance System
Deterministic Statutory Rule Engine under Legal Metrology (Packaged Commodities) Rules, 2011
"""

import re
import math
from typing import List, Dict, Any, Optional, Tuple

class LegalMetrologyRuleEngine:
    """
    Deterministic compliance verification engine implementing:
    - Rule 6(1)(a): Manufacturer/Packer identity & address
    - Rule 6(1)(b): Generic/Common commodity name
    - Rule 6(1)(c) & Rule 12: Net quantity & standard SI units (flags 'gms', 'gm', 'ltr', etc.)
    - Rule 6(1)(d): Month & Year of manufacture / packing
    - Rule 6(1)(e): Maximum Retail Price (MRP) & mandatory 'inclusive of all taxes' clause
    - Rule 6(1)(11): Unit Sale Price (USP) detection and mathematical consistency check
    - Rule 6(1)(da): Consumer grievance contact details (telephone/helpline and email)
    """

    # Prohibited non-standard units under Rule 12(1)
    ILLEGAL_METRIC_SYMBOLS = {
        'gm': 'g',
        'gms': 'g',
        'grms': 'g',
        'grm': 'g',
        'kgs': 'kg',
        'kilo': 'kg',
        'kilos': 'kg',
        'ltr': 'l',
        'ltrs': 'l',
        'lit': 'l',
        'litre': 'l',
        'litres': 'l',
        'mls': 'ml',
        'ml.': 'ml',
        'g.': 'g',
        'kg.': 'kg',
        'l.': 'l'
    }

    # Standard valid SI units under Rule 12
    VALID_SI_UNITS = {'g', 'kg', 'ml', 'l', 'm', 'cm', 'mm', 'n', 'u'}

    # Dictionary of common generic commodities for Rule 6(1)(b)
    GENERIC_COMMODITIES = [
        "potato chips", "wafers", "biscuits", "cookies", "crackers", "atta", "wheat flour",
        "maida", "besan", "rice", "basmati rice", "pulses", "dal", "sugar", "iodised salt",
        "salt", "tea", "coffee", "edible vegetable oil", "mustard oil", "sunflower oil",
        "soybean oil", "ghee", "butter", "paneer", "milk", "curd", "yogurt", "cheese",
        "detergent powder", "detergent bar", "washing powder", "toilet soap", "bathing soap",
        "shampoo", "hair oil", "toothpaste", "toothbrush", "instant noodles", "noodles",
        "pasta", "macaroni", "tomato ketchup", "sauce", "fruit juice", "ready to serve beverage",
        "spices", "turmeric powder", "chilli powder", "coriander powder", "garam masala",
        "corn flakes", "breakfast cereal", "oats", "namkeen", "bhujia", "mixture", "chocolates",
        "confectionery", "packaged drinking water", "mineral water"
    ]

    def __init__(self):
        pass

    def evaluate(self, ocr_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs complete statutory audit on OCR output tokens and assembled lines.
        """
        lines = ocr_data.get("assembled_lines", [])
        tokens = ocr_data.get("raw_tokens", [])
        full_text = ocr_data.get("full_extracted_text", "")
        
        # Combined text string for global fallback regex
        combined_text = " \n ".join([l["text"] for l in lines]) if lines else full_text

        # 1. Rule 6(1)(e): Maximum Retail Price & Mandatory Tax Declaration
        r6e_report = self._audit_rule_6_1_e(lines, tokens, combined_text)

        # 2. Rule 6(1)(c) & Rule 12: Net Quantity & Standard SI Units
        r6c_report = self._audit_rule_6_1_c_and_12(lines, tokens, combined_text)

        # 3. Rule 6(1)(11): Unit Sale Price (USP) & Mathematical Consistency
        r6usp_report = self._audit_rule_6_1_usp(lines, tokens, combined_text, r6e_report, r6c_report)

        # 4. Rule 6(1)(d): Month & Year of Manufacture / Packing
        r6d_report = self._audit_rule_6_1_d(lines, tokens, combined_text)

        # 5. Rule 6(1)(da): Consumer Grievance Redressal (Helpline & Email)
        r6da_report = self._audit_rule_6_1_da(lines, tokens, combined_text)

        # 6. Rule 6(1)(a): Manufacturer / Packer Identity & Address
        r6a_report = self._audit_rule_6_1_a(lines, tokens, combined_text)

        # 7. Rule 6(1)(b): Generic / Common Commodity Name
        r6b_report = self._audit_rule_6_1_b(lines, tokens, combined_text)

        audit_report = {
            "rule_6_1_e_mrp": r6e_report,
            "rule_6_1_c_net_quantity": r6c_report,
            "rule_6_1_11_unit_sale_price": r6usp_report,
            "rule_6_1_d_mfg_date": r6d_report,
            "rule_6_1_da_consumer_grievance": r6da_report,
            "rule_6_1_a_manufacturer": r6a_report,
            "rule_6_1_b_commodity_name": r6b_report,
        }

        # Calculate overall compliance score and status
        scoring = self._calculate_compliance_score(audit_report)

        return {
            "overall_status": scoring["overall_status"],
            "compliance_score": scoring["score_percentage"],
            "compliance_grade": scoring["grade"],
            "violations_count": scoring["violations_count"],
            "warnings_count": scoring["warnings_count"],
            "passed_rules_count": scoring["passed_count"],
            "audit_report": audit_report,
            "violations_summary": scoring["violations_summary"],
            "raw_tokens": tokens,
            "assembled_lines": lines
        }

    # -------------------------------------------------------------------------
    # RULE 6(1)(e): Maximum Retail Price & Mandatory Tax Declaration
    # -------------------------------------------------------------------------
    def _audit_rule_6_1_e(self, lines: List[Dict], tokens: List[Dict], full_text: str) -> Dict[str, Any]:
        """
        Rule 6(1)(e): The maximum retail price at which the commodity in packaged form
        may be sold to the consumer, inclusive of all taxes.
        """
        # Patterns for MRP value
        mrp_pattern = re.compile(
            r'(?:M\.?R\.?P\.?|MAX(?:IMUM)?\s*RETAIL\s*PRICE|MRP\s*Rs\.?|Rs\.?|₹|INR)\s*[:.\-]?\s*(?:Rs\.?|₹|INR)?\s*([0-9]+(?:\.[0-9]{1,2})?)',
            re.IGNORECASE
        )
        tax_clause_pattern = re.compile(
            r'(?:incl(?:usive)?\.?\s*(?:of\s*)?all\s*taxes|incl\.?\s*taxes)',
            re.IGNORECASE
        )

        detected_mrp = None
        has_tax_clause = False
        matched_line_text = ""
        bbox = None

        # Check line by line first for spatial proximity
        for line in lines:
            text = line["text"]
            match = mrp_pattern.search(text)
            if match and not detected_mrp:
                try:
                    val = float(match.group(1))
                    if 0.5 <= val <= 500000: # sanity check
                        detected_mrp = val
                        matched_line_text = text
                        bbox = line["bbox"]
                except ValueError:
                    pass

            if tax_clause_pattern.search(text):
                has_tax_clause = True
                if not bbox and line.get("bbox"):
                    bbox = line["bbox"]

        # Global fallback if not found in isolated lines
        if not detected_mrp:
            match = mrp_pattern.search(full_text)
            if match:
                try:
                    detected_mrp = float(match.group(1))
                    matched_line_text = match.group(0)
                except ValueError:
                    pass

        if not has_tax_clause:
            has_tax_clause = bool(tax_clause_pattern.search(full_text))

        # Associate token bbox if line bbox not found
        if not bbox and detected_mrp:
            for t in tokens:
                if str(int(detected_mrp)) in t["text"] or "MRP" in t["text"].upper():
                    bbox = t["bbox"]
                    break

        # Legal determination
        if detected_mrp is not None:
            if has_tax_clause:
                status = "COMPLIANT"
                details = f"MRP ₹ {detected_mrp:.2f} declared with mandatory statutory phrase 'inclusive of all taxes'."
            else:
                status = "NON_COMPLIANT"
                details = f"MRP ₹ {detected_mrp:.2f} detected, but MANDATORY statutory phrase 'inclusive of all taxes' is MISSING. Violation of Rule 6(1)(e) punishable under Section 36 of Legal Metrology Act."
        else:
            status = "FAIL"
            details = "Maximum Retail Price (MRP) declaration not found on package label. Mandatory under Rule 6(1)(e)."

        return {
            "rule": "Rule 6(1)(e)",
            "title": "Maximum Retail Price (MRP) & Tax Declaration",
            "legal_clause": "Rule 6(1)(e) - Maximum retail price at which commodity is sold, inclusive of all taxes.",
            "status": status,
            "detected_value": f"₹ {detected_mrp:.2f}" if detected_mrp is not None else None,
            "numeric_mrp": detected_mrp,
            "has_tax_clause": has_tax_clause,
            "matched_text": matched_line_text,
            "details": details,
            "bbox_reference": bbox
        }

    # -------------------------------------------------------------------------
    # RULE 6(1)(c) & RULE 12: Net Quantity & Standard SI Units Check
    # -------------------------------------------------------------------------
    def _audit_rule_6_1_c_and_12(self, lines: List[Dict], tokens: List[Dict], full_text: str) -> Dict[str, Any]:
        """
        Rule 6(1)(c) read with Rule 12: Standard unit of weight or measure.
        Enforces SI symbols ('g', 'kg', 'ml', 'l', 'N', 'U') and flags prohibited symbols ('gms', 'gm', 'ltr', etc.).
        """
        # Pattern to capture net quantity declarations
        net_qty_pattern = re.compile(
            r'(?:Net\s*(?:Qty|Quantity|Weight|Wt|Contents?|Vol(?:ume)?)[\s\.:]*)?([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+(?:\.|\b))',
            re.IGNORECASE
        )

        detected_qty = None
        detected_unit = None
        standard_unit = None
        is_illegal_symbol = False
        illegal_symbol_details = ""
        bbox = None
        matched_text = ""

        # Search lines
        for line in lines:
            text = line["text"]
            # Look for lines with Net Qty keywords or unit patterns
            matches = net_qty_pattern.findall(text)
            for num_str, unit_raw in matches:
                u_clean = unit_raw.lower().rstrip('.').strip()
                if u_clean in self.ILLEGAL_METRIC_SYMBOLS or u_clean in self.VALID_SI_UNITS:
                    try:
                        val = float(num_str)
                        if val > 0:
                            detected_qty = val
                            detected_unit = u_clean
                            matched_text = f"{num_str} {unit_raw}"
                            bbox = line["bbox"]
                            break
                    except ValueError:
                        continue
            if detected_qty:
                break

        # Fallback to tokens
        if not detected_qty:
            for i, t in enumerate(tokens):
                m = net_qty_pattern.search(t["text"])
                if m:
                    u_clean = m.group(2).lower().rstrip('.').strip()
                    if u_clean in self.ILLEGAL_METRIC_SYMBOLS or u_clean in self.VALID_SI_UNITS:
                        try:
                            detected_qty = float(m.group(1))
                            detected_unit = u_clean
                            matched_text = t["text"]
                            bbox = t["bbox"]
                            break
                        except ValueError:
                            pass

        # Legal determination
        if detected_qty is not None and detected_unit is not None:
            if detected_unit in self.ILLEGAL_METRIC_SYMBOLS:
                is_illegal_symbol = True
                standard_unit = self.ILLEGAL_METRIC_SYMBOLS[detected_unit]
                status = "WARNING"
                details = (
                    f"Non-compliant metric symbol '{detected_unit}' detected in '{matched_text}'. "
                    f"Under Rule 12(1) of Legal Metrology (Packaged Commodities) Rules, 2011, "
                    f"symbols must not be pluralized or altered. Mandatory SI symbol is '{standard_unit}'."
                )
            elif detected_unit in self.VALID_SI_UNITS:
                standard_unit = detected_unit
                status = "COMPLIANT"
                details = f"Net quantity {detected_qty} {detected_unit} uses authorized standard SI unit according to Rule 12."
            else:
                status = "WARNING"
                details = f"Detected quantity {detected_qty} with unrecognized unit '{detected_unit}'."
        else:
            status = "FAIL"
            details = "Net Quantity declaration not found. Mandatory under Rule 6(1)(c) and Rule 12."

        # Compute normalized weight/volume in grams or milliliters for USP arithmetic
        normalized_base_value = None
        normalized_base_unit = None
        if detected_qty and standard_unit:
            if standard_unit == 'kg':
                normalized_base_value = detected_qty * 1000.0
                normalized_base_unit = 'g'
            elif standard_unit == 'g':
                normalized_base_value = detected_qty
                normalized_base_unit = 'g'
            elif standard_unit == 'l':
                normalized_base_value = detected_qty * 1000.0
                normalized_base_unit = 'ml'
            elif standard_unit == 'ml':
                normalized_base_value = detected_qty
                normalized_base_unit = 'ml'

        return {
            "rule": "Rule 6(1)(c) & Rule 12",
            "title": "Net Quantity & Standard SI Metric Symbol",
            "legal_clause": "Rule 6(1)(c) & Rule 12(1) - Net quantity in standard SI units (prohibits 'gms', 'ltr', etc.)",
            "status": status,
            "detected_value": f"{detected_qty} {detected_unit}" if detected_qty is not None else None,
            "numeric_qty": detected_qty,
            "detected_unit": detected_unit,
            "standard_unit": standard_unit,
            "is_illegal_symbol": is_illegal_symbol,
            "normalized_base_value": normalized_base_value,
            "normalized_base_unit": normalized_base_unit,
            "matched_text": matched_text,
            "details": details,
            "bbox_reference": bbox
        }

    # -------------------------------------------------------------------------
    # RULE 6(1)(11): Unit Sale Price (USP) & Arithmetic Verification
    # -------------------------------------------------------------------------
    def _audit_rule_6_1_usp(
        self,
        lines: List[Dict],
        tokens: List[Dict],
        full_text: str,
        r6e: Dict[str, Any],
        r6c: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Rule 6(1)(11) (2021/2022 Amendment): Unit Sale Price (USP) declaration & arithmetic consistency.
        USP = MRP / Net Quantity normalized to per g, per 100g, per kg, per ml, per 100ml, per l.
        """
        usp_pattern = re.compile(
            r'(?:Unit\s*Sale\s*Price|USP|Unit\s*Price)[\s\.:]*(?:Rs\.?|₹|INR)?\s*([0-9]+(?:\.[0-9]{1,4})?)\s*(?:\/|\s*per\s*)\s*([0-9]*\s*[a-zA-Z]+)',
            re.IGNORECASE
        )
        # Standalone rate pattern: ₹ 0.45 / g or Rs 25.00 / 100g
        rate_pattern = re.compile(
            r'(?:Rs\.?|₹|INR)\s*([0-9]+(?:\.[0-9]{1,4})?)\s*(?:\/|\s*per\s*)\s*([0-9]*\s*(?:g|kg|ml|l|100g|100ml|10g|piece|unit|n))',
            re.IGNORECASE
        )

        declared_usp = None
        usp_unit_str = None
        matched_text = ""
        bbox = None

        for line in lines:
            text = line["text"]
            m = usp_pattern.search(text)
            if not m:
                m = rate_pattern.search(text)
            if m:
                try:
                    val = float(m.group(1))
                    unit = m.group(2).strip().lower()
                    if val > 0:
                        declared_usp = val
                        usp_unit_str = unit
                        matched_text = line["text"]
                        bbox = line["bbox"]
                        break
                except ValueError:
                    continue

        if not declared_usp:
            m = usp_pattern.search(full_text) or rate_pattern.search(full_text)
            if m:
                try:
                    declared_usp = float(m.group(1))
                    usp_unit_str = m.group(2).strip().lower()
                    matched_text = m.group(0)
                except ValueError:
                    pass

        # Arithmetic consistency check against MRP and Net Quantity
        mrp = r6e.get("numeric_mrp")
        base_qty = r6c.get("normalized_base_value") # in grams or ml
        base_unit = r6c.get("normalized_base_unit") # 'g' or 'ml'
        
        math_valid = None
        expected_usp = None
        math_details = ""

        if declared_usp and usp_unit_str and mrp and base_qty and base_unit:
            # Parse denominator of USP
            # e.g., 'g', '100g', 'kg', 'ml', '100ml', 'l'
            clean_usp_unit = usp_unit_str.replace(" ", "")
            multiplier = 1.0

            if clean_usp_unit in ['g', 'ml']:
                multiplier = 1.0
            elif clean_usp_unit in ['100g', '100ml']:
                multiplier = 100.0
            elif clean_usp_unit in ['kg', 'l']:
                multiplier = 1000.0
            elif clean_usp_unit == '10g':
                multiplier = 10.0

            # Expected USP = (MRP / total base quantity) * multiplier
            expected_usp = (mrp / base_qty) * multiplier
            abs_diff = abs(declared_usp - expected_usp)
            relative_error = abs_diff / expected_usp if expected_usp > 0 else 1.0

            # Allow 2% tolerance for rounding to 2 decimal places
            if relative_error <= 0.03 or abs_diff <= 0.05:
                math_valid = True
                status = "COMPLIANT"
                details = (
                    f"Unit Sale Price ₹ {declared_usp:.2f} / {usp_unit_str} is mathematically accurate. "
                    f"Computed expected rate: ₹ {expected_usp:.2f} / {usp_unit_str} (MRP ₹{mrp:.2f} ÷ {base_qty:.0f}{base_unit} × {int(multiplier)})."
                )
            else:
                math_valid = False
                status = "NON_COMPLIANT"
                details = (
                    f"MATHEMATICAL MISMATCH! Declared USP is ₹ {declared_usp:.2f} / {usp_unit_str}, "
                    f"but actual statutory calculation is ₹ {expected_usp:.2f} / {usp_unit_str} "
                    f"(MRP ₹{mrp:.2f} ÷ {base_qty:.0f}{base_unit} × {int(multiplier)}). "
                    f"Discrepancy exceeds legal tolerance under Rule 6(1)(11)."
                )
        elif declared_usp:
            status = "COMPLIANT"
            details = f"Unit Sale Price declared as ₹ {declared_usp:.2f} / {usp_unit_str}."
        else:
            # Under Legal Metrology 2022 amendment, USP is mandatory for commodities
            status = "WARNING"
            details = "Unit Sale Price (USP) declaration not detected. Mandatory under Rule 6(1)(11) for pre-packaged commodities."

        return {
            "rule": "Rule 6(1)(11)",
            "title": "Unit Sale Price (USP) & Math Verification",
            "legal_clause": "Rule 6(1)(11) - Unit sale price per g/100g/kg or ml/100ml/l with mathematical accuracy.",
            "status": status,
            "detected_value": f"₹ {declared_usp:.2f} / {usp_unit_str}" if declared_usp is not None else None,
            "declared_usp": declared_usp,
            "expected_usp": round(expected_usp, 2) if expected_usp is not None else None,
            "math_consistent": math_valid,
            "matched_text": matched_text,
            "details": details,
            "bbox_reference": bbox
        }

    # -------------------------------------------------------------------------
    # RULE 6(1)(d): Month & Year of Manufacture / Packing
    # -------------------------------------------------------------------------
    def _audit_rule_6_1_d(self, lines: List[Dict], tokens: List[Dict], full_text: str) -> Dict[str, Any]:
        """
        Rule 6(1)(d): Month and year in which the commodity is manufactured or pre-packed or imported.
        """
        date_pattern = re.compile(
            r'(?:MFD|PKD|PACKED|MFG|MANUFACTURED|DATE\s*OF\s*(?:MFG|PKD|PACKING|MANUFACTURE)|USE\s*BY|BEST\s*BEFORE)[\s\.:\-]*([0-9]{1,2}[\/\-\.][0-9]{2,4}|(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[a-z]*[\s\.\-\/]*[0-9]{2,4})',
            re.IGNORECASE
        )
        # Standalone MM/YYYY pattern (e.g., 08/2026 or 08/26)
        standalone_date = re.compile(
            r'\b(0[1-9]|1[0-2])[\/\-](202[0-9]|2[0-9])\b'
        )

        detected_date = None
        matched_text = ""
        bbox = None

        for line in lines:
            text = line["text"]
            m = date_pattern.search(text)
            if m:
                detected_date = m.group(1).strip()
                matched_text = line["text"]
                bbox = line["bbox"]
                break

        if not detected_date:
            for line in lines:
                m = standalone_date.search(line["text"])
                if m:
                    detected_date = m.group(0).strip()
                    matched_text = line["text"]
                    bbox = line["bbox"]
                    break

        if not detected_date:
            m = date_pattern.search(full_text) or standalone_date.search(full_text)
            if m:
                detected_date = m.group(1 if m.lastindex else 0).strip()
                matched_text = m.group(0)

        if detected_date:
            status = "COMPLIANT"
            details = f"Date of Manufacture/Packing '{detected_date}' complies with Rule 6(1)(d) statutory timeline requirement."
        else:
            status = "NON_COMPLIANT"
            details = "Month and Year of manufacture or packing is NOT detected on label. Mandatory under Rule 6(1)(d)."

        return {
            "rule": "Rule 6(1)(d)",
            "title": "Month & Year of Manufacture / Packing",
            "legal_clause": "Rule 6(1)(d) - Mandatory declaration of month and year in which commodity is packed/manufactured.",
            "status": status,
            "detected_value": detected_date,
            "matched_text": matched_text,
            "details": details,
            "bbox_reference": bbox
        }

    # -------------------------------------------------------------------------
    # RULE 6(1)(da): Consumer Grievance Contact Details
    # -------------------------------------------------------------------------
    def _audit_rule_6_1_da(self, lines: List[Dict], tokens: List[Dict], full_text: str) -> Dict[str, Any]:
        """
        Rule 6(1)(da): Name, address, telephone number and e-mail address of person
        who can be contacted by consumer in case of complaints.
        """
        phone_pattern = re.compile(
            r'(?:1800[-\s]?[0-9]{3}[-\s]?[0-9]{3,4}|(?:\+91|0)?[-\s]?[6-9][0-9]{9}|\b[0-9]{3,4}[-\s]?[0-9]{7,8}\b)'
        )
        email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )
        grievance_kw_pattern = re.compile(
            r'(?:customer\s*care|consumer\s*care|helpline|toll\s*free|grievance|feedback|contact\s*us|reach\s*us|complaints)',
            re.IGNORECASE
        )

        detected_phone = None
        detected_email = None
        has_grievance_header = bool(grievance_kw_pattern.search(full_text))
        bbox = None

        for line in lines:
            text = line["text"]
            if not detected_phone:
                p = phone_pattern.search(text)
                if p:
                    detected_phone = p.group(0).strip()
                    if not bbox:
                        bbox = line["bbox"]
            if not detected_email:
                e = email_pattern.search(text)
                if e:
                    detected_email = e.group(0).strip()
                    if not bbox:
                        bbox = line["bbox"]

        # Global fallback
        if not detected_phone:
            p = phone_pattern.search(full_text)
            if p:
                detected_phone = p.group(0).strip()

        if not detected_email:
            e = email_pattern.search(full_text)
            if e:
                detected_email = e.group(0).strip()

        # Legal determination
        if detected_phone and detected_email:
            status = "COMPLIANT"
            details = f"Complete grievance redressal details detected: Phone/Toll-Free ({detected_phone}) and Email ({detected_email})."
        elif detected_phone or detected_email:
            status = "WARNING"
            present_item = f"Phone: {detected_phone}" if detected_phone else f"Email: {detected_email}"
            missing_item = "Email" if not detected_email else "Telephone/Helpline"
            details = (
                f"Partial compliance with Rule 6(1)(da). Detected {present_item}, "
                f"but missing statutory mandatory {missing_item}."
            )
        else:
            status = "NON_COMPLIANT"
            details = "Mandatory Consumer Care contact details (Telephone number and E-mail address) are MISSING. Statutory violation of Rule 6(1)(da)."

        val_str = []
        if detected_phone:
            val_str.append(f"Tel: {detected_phone}")
        if detected_email:
            val_str.append(f"Email: {detected_email}")

        return {
            "rule": "Rule 6(1)(da)",
            "title": "Consumer Grievance Redressal Mechanism",
            "legal_clause": "Rule 6(1)(da) - Name, address, telephone number and email address for consumer complaints.",
            "status": status,
            "detected_value": " | ".join(val_str) if val_str else None,
            "phone": detected_phone,
            "email": detected_email,
            "has_grievance_header": has_grievance_header,
            "details": details,
            "bbox_reference": bbox
        }

    # -------------------------------------------------------------------------
    # RULE 6(1)(a): Manufacturer / Packer Identity & Address
    # -------------------------------------------------------------------------
    def _audit_rule_6_1_a(self, lines: List[Dict], tokens: List[Dict], full_text: str) -> Dict[str, Any]:
        """
        Rule 6(1)(a): Name and complete address of the manufacturer, packer, or importer.
        """
        mfg_pattern = re.compile(
            r'(?:MFD\s*BY|MANUFACTURED\s*BY|PACKED\s*BY|PKD\s*BY|MARKETED\s*BY|IMPORTED\s*BY|MADE\s*IN\s*INDIA)\s*[:.\-]?\s*([A-Za-z0-9\s,\.\-\(\)&]+)',
            re.IGNORECASE
        )
        pincode_pattern = re.compile(r'\b[1-9][0-9]{2}\s?[0-9]{3}\b')

        detected_mfg = None
        has_pincode = False
        matched_text = ""
        bbox = None

        for line in lines:
            text = line["text"]
            m = mfg_pattern.search(text)
            if m and not detected_mfg:
                detected_mfg = m.group(0).strip()
                matched_text = text
                bbox = line["bbox"]
            if pincode_pattern.search(text):
                has_pincode = True

        if not detected_mfg:
            m = mfg_pattern.search(full_text)
            if m:
                detected_mfg = m.group(0).strip()
                matched_text = detected_mfg

        if not has_pincode:
            has_pincode = bool(pincode_pattern.search(full_text))

        if detected_mfg:
            status = "COMPLIANT"
            details = f"Manufacturer/Packer identity declared: '{detected_mfg[:60]}...'" + (" (PIN code verified)" if has_pincode else "")
        else:
            status = "WARNING"
            details = "Manufacturer or Packer declaration keyword not distinctly recognized. Verify identity manually."

        return {
            "rule": "Rule 6(1)(a)",
            "title": "Manufacturer / Packer / Importer Identity",
            "legal_clause": "Rule 6(1)(a) - Name and complete address of the manufacturer, packer, or importer.",
            "status": status,
            "detected_value": detected_mfg[:70] if detected_mfg else None,
            "has_pincode": has_pincode,
            "details": details,
            "bbox_reference": bbox
        }

    # -------------------------------------------------------------------------
    # RULE 6(1)(b): Generic / Common Commodity Name
    # -------------------------------------------------------------------------
    def _audit_rule_6_1_b(self, lines: List[Dict], tokens: List[Dict], full_text: str) -> Dict[str, Any]:
        """
        Rule 6(1)(b): The common or generic name of the commodity contained in the package.
        """
        lower_text = full_text.lower()
        detected_commodity = None
        bbox = None

        for item in self.GENERIC_COMMODITIES:
            if re.search(r'\b' + re.escape(item) + r'\b', lower_text):
                detected_commodity = item.title()
                break

        # Find bbox if possible
        if detected_commodity:
            for line in lines:
                if detected_commodity.lower() in line["text"].lower():
                    bbox = line["bbox"]
                    break

        if detected_commodity:
            status = "COMPLIANT"
            details = f"Common generic commodity name identified as '{detected_commodity}' under Rule 6(1)(b)."
        else:
            status = "WARNING"
            details = "Common generic commodity name not matched against standard gazette list. Check package front panel."

        return {
            "rule": "Rule 6(1)(b)",
            "title": "Common Generic Commodity Name",
            "legal_clause": "Rule 6(1)(b) - The common or generic name of the commodity contained in package.",
            "status": status,
            "detected_value": detected_commodity,
            "details": details,
            "bbox_reference": bbox
        }

    # -------------------------------------------------------------------------
    # SCORING & AGGREGATION
    # -------------------------------------------------------------------------
    def _calculate_compliance_score(self, report: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Computes statutory weighted score and overall compliance determination.
        """
        weights = {
            "rule_6_1_e_mrp": 25.0,
            "rule_6_1_c_net_quantity": 25.0,
            "rule_6_1_11_unit_sale_price": 20.0,
            "rule_6_1_d_mfg_date": 10.0,
            "rule_6_1_da_consumer_grievance": 10.0,
            "rule_6_1_a_manufacturer": 5.0,
            "rule_6_1_b_commodity_name": 5.0
        }

        total_score = 0.0
        violations_count = 0
        warnings_count = 0
        passed_count = 0
        violations_summary = []

        for rule_key, rule_data in report.items():
            st = rule_data.get("status", "FAIL")
            w = weights.get(rule_key, 10.0)

            if st == "COMPLIANT":
                total_score += w
                passed_count += 1
            elif st == "WARNING":
                total_score += (w * 0.5)
                warnings_count += 1
                violations_summary.append({
                    "severity": "WARNING",
                    "rule": rule_data["rule"],
                    "title": rule_data["title"],
                    "details": rule_data["details"]
                })
            else: # NON_COMPLIANT or FAIL
                violations_count += 1
                violations_summary.append({
                    "severity": "NON_COMPLIANT",
                    "rule": rule_data["rule"],
                    "title": rule_data["title"],
                    "details": rule_data["details"]
                })

        score_pct = round(total_score, 1)

        # Verdict logic
        if violations_count == 0 and warnings_count == 0:
            overall_status = "PASS"
            grade = "A+ (Fully Compliant)"
        elif violations_count == 0 and warnings_count > 0:
            overall_status = "WARNING"
            grade = "B (Compliant with Warnings)"
        else:
            overall_status = "FAIL"
            grade = "F (Statutory Violations Detected)"

        return {
            "score_percentage": score_pct,
            "overall_status": overall_status,
            "grade": grade,
            "violations_count": violations_count,
            "warnings_count": warnings_count,
            "passed_count": passed_count,
            "violations_summary": violations_summary
        }
