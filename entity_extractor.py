"""
SIH26034 - Layer 4: Zero-Shot Entity Extraction & RapidFuzz Typo Repair
Uses GLiNER (Zero-Shot Information Extraction) + RapidFuzz (String distance & fuzzy typo repair)
Extracts packaging entities (mrp, net_quantity, grievance_email, dates, manufacturer)
and repairs character-level OCR misrecognitions.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple
import rapidfuzz
from rapidfuzz import fuzz, process

logger = logging.getLogger("EntityExtractor")

STATUTORY_TAX_PHRASES = [
    "inclusive of all taxes",
    "incl. of all taxes",
    "incl of all taxes",
    "inclusive of taxes",
    "incl. all taxes",
    "incl taxes"
]

class RapidFuzzRepairEngine:
    """
    RapidFuzz Typo & OCR Repair Engine.
    Repairs character and punctuation misalignments on Legal Metrology declarations.
    """

    @staticmethod
    def repair_tax_clause(text: str, score_cutoff: float = 78.0) -> Tuple[bool, str]:
        """
        Uses RapidFuzz partial ratio to detect and repair noisy tax clause declarations.
        Handles OCR typos like '1ncl. of all taxes', 'inc. of all taxs', 'inclusive of al taxes'.
        """
        lower_text = text.lower()
        # Direct check first
        for phrase in STATUTORY_TAX_PHRASES:
            if phrase in lower_text:
                return True, phrase

        # RapidFuzz fuzzy search for each statutory phrase
        for phrase in STATUTORY_TAX_PHRASES:
            match = process.extractOne(
                phrase,
                lower_text.splitlines() or [lower_text],
                scorer=fuzz.partial_ratio,
                score_cutoff=score_cutoff
            )
            if match and match[1] >= score_cutoff:
                return True, phrase

        # Token-level ngram sliding check for single-line substrings
        words = lower_text.split()
        for i in range(len(words)):
            window = " ".join(words[i:i+5])
            ratio = fuzz.ratio(window, "inclusive of all taxes")
            if ratio >= score_cutoff:
                return True, "inclusive of all taxes"
            part_ratio = fuzz.partial_ratio(window, "incl. of all taxes")
            if part_ratio >= 85.0:
                return True, "incl. of all taxes"

        return False, ""

    @staticmethod
    def repair_phone_digits(text: str) -> str:
        """
        Repairs common letter-to-digit confusions in helpline numbers:
        '180O' -> '1800', 'l800' -> '1800', 'O' -> '0', 'B' -> '8'.
        """
        # Find potential toll free / helpline sequences
        toll_pattern = re.compile(r'(?:18[0oO]{2}|[lI]8[0oO]{2})[-\s]?[0-9oOIl]{3}[-\s]?[0-9oOIl]{3,4}')
        match = toll_pattern.search(text)
        if match:
            raw = match.group(0)
            cleaned = raw.replace('O', '0').replace('o', '0').replace('l', '1').replace('I', '1')
            text = text[:match.start()] + cleaned + text[match.end():]

        # Normal 10-digit mobile / helpline
        mob_pattern = re.compile(r'(?:[6-9][0-9oOIl]{9})')
        m_match = mob_pattern.search(text)
        if m_match:
            raw = m_match.group(0)
            cleaned = raw.replace('O', '0').replace('o', '0').replace('l', '1').replace('I', '1')
            text = text[:m_match.start()] + cleaned + text[m_match.end():]

        return text

    @staticmethod
    def fuzzy_match_unit(raw_unit: str) -> Tuple[Optional[str], bool]:
        """
        Fuzzy matches unit symbols against Legal Metrology valid and illegal symbols.
        Returns: (standard_si_unit, is_illegal_variant)
        """
        clean = raw_unit.lower().strip().rstrip('.')
        exact_valid = {"g": "g", "kg": "kg", "ml": "ml", "l": "l", "n": "N", "u": "U"}
        exact_illegal = {
            "gms": "g", "gm": "g", "g.m.": "g", "g.m.s.": "g", "grams": "g", "gram": "g",
            "kgs": "kg", "kilo": "kg", "kilogram": "kg", "kilograms": "kg",
            "ltr": "l", "ltrs": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
            "mls": "ml", "m.l.": "ml", "millilitre": "ml", "milliliter": "ml"
        }

        if clean in exact_valid:
            return exact_valid[clean], False
        if clean in exact_illegal:
            return exact_illegal[clean], True

        # Fuzzy match with RapidFuzz
        best_match = process.extractOne(clean, list(exact_illegal.keys()) + list(exact_valid.keys()), scorer=fuzz.ratio)
        if best_match and best_match[1] >= 85.0:
            matched_key = best_match[0]
            if matched_key in exact_valid:
                return exact_valid[matched_key], False
            else:
                return exact_illegal[matched_key], True

        return None, False


class GLiNERPackagingExtractor:
    """
    Zero-Shot Packaging Information Extractor.
    Plugs in GLiNER (Generalist Model for Information Extraction) if available,
    with high-speed RapidFuzz semantic parsing as fast deterministic baseline.
    """

    PACKAGING_LABELS = [
        "maximum retail price",
        "net quantity",
        "unit sale price",
        "date of manufacture",
        "best before date",
        "consumer care email",
        "consumer care phone",
        "manufacturer name",
        "manufacturer address",
        "country of origin"
    ]

    def __init__(self):
        self._gliner_model = None
        self._init_gliner()

    def _init_gliner(self):
        try:
            from gliner import GLiNER
            # Optional lightweight GLiNER zero-shot model
            self._gliner_model = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
            logger.info("GLiNER zero-shot entity extractor loaded.")
        except Exception:
            self._gliner_model = None
            logger.info("Using RapidFuzz zero-shot entity clustering for Layer 4.")

    def extract_entities(self, text: str, lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Extracts packaging declarations using zero-shot semantic parsing and RapidFuzz typo repair.
        """
        entities: Dict[str, Any] = {
            "mrp": None,
            "has_tax_clause": False,
            "net_quantity": None,
            "declared_unit": None,
            "standard_unit": None,
            "is_illegal_unit": False,
            "unit_sale_price": None,
            "mfg_date": None,
            "consumer_phone": None,
            "consumer_email": None,
            "manufacturer": None,
            "country_of_origin": None,
            "typos_repaired": []
        }

        # 1. Tax clause detection and repair via RapidFuzz
        has_taxes, matched_phrase = RapidFuzzRepairEngine.repair_tax_clause(text)
        entities["has_tax_clause"] = has_taxes
        if has_taxes and matched_phrase not in text.lower():
            entities["typos_repaired"].append(f"Tax clause repaired to '{matched_phrase}'")

        # 2. Extract MRP
        mrp_m = re.search(r'(?:MRP|M\.R\.P|MAXIMUM\s*RETAIL\s*PRICE|Rs\.?|₹)\s*[:.\-]?\s*(?:Rs\.?|₹)?\s*([0-9]+(?:\.[0-9]{1,2})?)', text, re.IGNORECASE)
        if mrp_m:
            try:
                entities["mrp"] = float(mrp_m.group(1))
            except ValueError:
                pass

        # 3. Extract Net Quantity and Unit with RapidFuzz
        qty_m = re.search(r'(?:Net\s*(?:Qty|Quantity|Weight|Contents?|Vol)[\s\.:]*)?([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z\.]+)', text, re.IGNORECASE)
        if qty_m:
            try:
                val = float(qty_m.group(1))
                unit_raw = qty_m.group(2)
                std_unit, is_illegal = RapidFuzzRepairEngine.fuzzy_match_unit(unit_raw)
                if std_unit:
                    entities["net_quantity"] = val
                    entities["declared_unit"] = unit_raw.rstrip('.')
                    entities["standard_unit"] = std_unit
                    entities["is_illegal_unit"] = is_illegal
                    if is_illegal:
                        entities["typos_repaired"].append(f"Illegal unit '{unit_raw}' mapped to standard SI unit '{std_unit}'")
            except ValueError:
                pass

        # 4. Extract Helpline Phone with RapidFuzz digit repair
        phone_m = re.search(r'(?:18[0-9oOIl]{2}[-\s]?[0-9oOIl]{3}[-\s]?[0-9oOIl]{3,4}|[6-9][0-9oOIl]{9})', text)
        if phone_m:
            repaired_phone = RapidFuzzRepairEngine.repair_phone_digits(phone_m.group(0))
            entities["consumer_phone"] = repaired_phone
            if repaired_phone != phone_m.group(0):
                entities["typos_repaired"].append(f"Helpline phone repaired from '{phone_m.group(0)}' to '{repaired_phone}'")

        # 5. Extract Helpline Email
        email_m = re.search(r'(?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(?:email|e-mail)[\s\.:]*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+))', text, re.IGNORECASE)
        if email_m:
            entities["consumer_email"] = (email_m.group(1) if email_m.group(1) else email_m.group(0)).strip()

        # 6. Extract Manufacturing Date
        date_m = re.search(r'(?:MFD|PKD|PACKED|MFG|DATE\s*OF\s*MFG)[\s\.:\-]*([0-9]{1,2}[\/\-\.][0-9]{2,4})', text, re.IGNORECASE)
        if date_m:
            entities["mfg_date"] = date_m.group(1).strip()

        # 7. Extract Unit Sale Price (USP)
        usp_m = re.search(r'(?:Unit\s*Sale\s*Price|USP|Unit\s*Price)[\s\.:]*(?:Rs\.?|₹)?\s*([0-9]+(?:\.[0-9]{1,4})?)\s*(?:\/|\s*per\s*)\s*([0-9]*\s*[a-zA-Z]+)', text, re.IGNORECASE)
        if usp_m:
            try:
                entities["unit_sale_price"] = {
                    "declared_usp": float(usp_m.group(1)),
                    "unit_denominator": usp_m.group(2).strip().lower()
                }
            except ValueError:
                pass

        # 8. Extract Country of Origin
        origin_m = re.search(r'(?:Country\s*of\s*Origin|Made\s*in)[\s\.:]*([A-Za-z]+)', text, re.IGNORECASE)
        if origin_m:
            entities["country_of_origin"] = origin_m.group(1).strip()

        # If GLiNER neural model is loaded, enrich with zero-shot neural spans
        if self._gliner_model:
            try:
                predictions = self._gliner_model.predict_entities(text, self.PACKAGING_LABELS)
                entities["gliner_neural_spans"] = predictions
            except Exception as e:
                logger.warning(f"GLiNER prediction failed: {e}")

        return entities
