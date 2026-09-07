from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Dict, Any, List, Optional

import cv2
import numpy as np

from ocr_engine import OCREngine


LANGUAGE_NAMES = {
    "en": "English",
    "ta": "Tamil",
    "hi": "Hindi",
    "te": "Telugu",
    "mixed": "Mixed",
}

TRANSLATION_HINTS = {
    "ta": {
        "அதிகபட்ச சில்லறை விலை": "maximum retail price",
        "நிகர எடை": "net quantity",
        "உற்பத்தியாளர்": "manufacturer",
        "முகவரி": "address",
        "தொகுதி": "batch",
    },
    "hi": {
        "अधिकतम खुदरा मूल्य": "maximum retail price",
        "शुद्ध मात्रा": "net quantity",
        "निर्माता": "manufacturer",
        "पता": "address",
        "बैच": "batch",
    },
    "te": {
        "గరిష్ట చిల్లర ధర": "maximum retail price",
        "నికర పరిమాణం": "net quantity",
        "తయారీదారు": "manufacturer",
        "చిరునామా": "address",
        "బ్యాచ్": "batch",
    },
}


class LanguageService:
    @staticmethod
    def detect(text: str) -> Dict[str, Any]:
        counts = {"ta": 0, "hi": 0, "te": 0, "en": 0}
        for ch in text:
            code = ord(ch)
            if 0x0B80 <= code <= 0x0BFF:
                counts["ta"] += 1
            elif 0x0900 <= code <= 0x097F:
                counts["hi"] += 1
            elif 0x0C00 <= code <= 0x0C7F:
                counts["te"] += 1
            elif ch.isascii() and ch.isalpha():
                counts["en"] += 1
        nonzero = [k for k, v in counts.items() if v > 2]
        if len(nonzero) > 1:
            language = "mixed"
        elif nonzero:
            language = max(nonzero, key=lambda k: counts[k])
        else:
            language = "en"
        total = max(1, sum(counts.values()))
        confidence = round(max(counts.values()) / total, 3)
        return {"code": language, "name": LANGUAGE_NAMES.get(language, language), "confidence": confidence, "script_counts": counts}

    @staticmethod
    def normalize_to_english(text: str, language_code: str) -> str:
        normalized = text
        if language_code in TRANSLATION_HINTS:
            for source, target in TRANSLATION_HINTS[language_code].items():
                normalized = normalized.replace(source, target)
        if language_code == "mixed":
            for mapping in TRANSLATION_HINTS.values():
                for source, target in mapping.items():
                    normalized = normalized.replace(source, target)
        return normalized


class ProductCategoryClassifier:
    KEYWORDS = {
        "food": ["nutrition", "ingredients", "fssai", "best before", "calories", "protein", "snack", "biscuit", "rice", "oil", "milk"],
        "cosmetic": ["cosmetic", "shampoo", "cream", "lotion", "skin", "hair", "soap", "beauty", "fragrance"],
        "electronics": ["voltage", "watt", "adapter", "charger", "model", "input", "output", "electronic", "battery"],
    }

    @classmethod
    def classify(cls, text: str, image: Optional[np.ndarray] = None) -> Dict[str, Any]:
        lower = text.lower()
        scores = {category: sum(1 for keyword in words if keyword in lower) for category, words in cls.KEYWORDS.items()}
        category = max(scores, key=scores.get) if max(scores.values(), default=0) > 0 else "general"
        visual_hint = "unknown"
        if image is not None and image.size:
            h, w = image.shape[:2]
            ratio = w / max(1, h)
            visual_hint = "wide-package" if ratio > 1.35 else ("tall-package" if ratio < 0.75 else "standard-package")
        confidence = 0.55 if category == "general" else min(0.95, 0.62 + scores[category] * 0.08)
        return {"category": category, "confidence": round(confidence, 2), "keyword_scores": scores, "visual_hint": visual_hint}


class ComputerVisionAnalyzer:
    @staticmethod
    def inspect(image: np.ndarray, tokens: List[Dict[str, Any]]) -> Dict[str, Any]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        edges = cv2.Canny(gray, 80, 180)
        edge_density = float(np.count_nonzero(edges)) / float(edges.size)
        h, w = gray.shape[:2]
        text_area = 0
        for token in tokens:
            x, y, bw, bh = token.get("bbox", [0, 0, 0, 0])
            text_area += max(0, bw) * max(0, bh)
        text_coverage = min(1.0, text_area / max(1.0, w * h))
        quality = 100.0
        if brightness < 45 or brightness > 225:
            quality -= 20
        if sharpness < 70:
            quality -= 25
        if edge_density < 0.015:
            quality -= 10
        quality = max(0.0, min(100.0, quality))
        return {
            "brightness": round(brightness, 1),
            "sharpness": round(sharpness, 1),
            "edge_density": round(edge_density, 4),
            "text_coverage": round(text_coverage, 4),
            "quality_score": round(quality, 1),
            "layout_analysis": {
                "image_width": w,
                "image_height": h,
                "text_regions": len(tokens),
                "dense_text_layout": len(tokens) >= 10,
            },
        }


class SemanticVerifier:
    def __init__(self):
        self.endpoint = os.getenv("SMARTMETROLOGY_LLM_URL", "").strip()
        self.api_key = os.getenv("SMARTMETROLOGY_LLM_KEY", "").strip()

    def _remote(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.endpoint:
            return None
        try:
            body = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=8) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {"result": parsed}
        except Exception:
            return None

    @staticmethod
    def _extract_fields(text: str) -> Dict[str, Any]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        joined = "\n".join(lines)
        patterns = {
            "mrp": r"(?:MRP|maximum retail price)\s*[:\-]?\s*((?:₹|Rs\.?|INR)?\s*\d+(?:\.\d{1,2})?)",
            "net_quantity": r"(?:net\s*(?:qty|quantity|weight)?\s*[:\-]?\s*)?(\d+(?:\.\d+)?\s*(?:kg|g|gm|ml|l|litre|liter|pcs?|pieces?))\b",
            "batch_number": r"(?:batch|lot)\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9\-/]{2,})",
            "manufactured_date": r"(?:mfg|mfd|manufactured|packed)\s*(?:on|date)?\s*[:\-]?\s*([0-9A-Z\-/\. ]{4,20})",
            "expiry_date": r"(?:exp|expiry|best before|use before)\s*[:\-]?\s*([0-9A-Z\-/\. ]{3,24})",
            "model_number": r"(?:model)\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9\-/]{2,})",
        }
        fields: Dict[str, Any] = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, joined, re.IGNORECASE)
            if match:
                fields[key] = match.group(1).strip()
        manufacturer_line = next((line for line in lines if re.search(r"manufacturer|manufactured by|packed by|உற்பத்தியாளர்|निर्माता|తయారీదారు", line, re.IGNORECASE)), None)
        if manufacturer_line:
            fields["manufacturer"] = manufacturer_line
        address_line = next((line for line in lines if re.search(r"address|முகவரி|पता|చిరునామా", line, re.IGNORECASE)), None)
        if address_line:
            fields["manufacturer_address"] = address_line
        consumer_line = next((line for line in lines if re.search(r"consumer|customer care|helpline|email|phone|complaint", line, re.IGNORECASE)), None)
        if consumer_line:
            fields["consumer_care"] = consumer_line
        return fields

    def verify(self, text: str, category: str, cv_result: Dict[str, Any]) -> Dict[str, Any]:
        local_fields = self._extract_fields(text)
        remote = self._remote({
            "task": "legal_metrology_label_semantic_extraction",
            "text": text,
            "category": category,
            "computer_vision": cv_result,
            "required_output": ["fields", "uncertainties", "explanations"],
        })
        if remote and isinstance(remote.get("fields"), dict):
            merged = {**local_fields, **remote["fields"]}
            return {"provider": "configured-llm", "fields": merged, "llm_response": remote}
        return {
            "provider": "offline-semantic-fallback",
            "fields": local_fields,
            "llm_response": None,
            "note": "Set SMARTMETROLOGY_LLM_URL to enable a remote LLM verifier; deterministic offline extraction remains available.",
        }


class HybridAIAnalyzer:
    def __init__(self):
        self.ocr = OCREngine()
        self.semantic = SemanticVerifier()

    def analyze(self, image: np.ndarray) -> Dict[str, Any]:
        ocr = self.ocr.process(image)
        raw_text = ocr.get("full_extracted_text", "")
        language = LanguageService.detect(raw_text)
        normalized_text = LanguageService.normalize_to_english(raw_text, language["code"])
        category = ProductCategoryClassifier.classify(normalized_text, image)
        cv_result = ComputerVisionAnalyzer.inspect(image, ocr.get("raw_tokens", []))
        semantic = self.semantic.verify(normalized_text, category["category"], cv_result)
        return {
            "pipeline": "OCR + Computer Vision + semantic/LLM verification",
            "ocr": ocr,
            "language": language,
            "translated_normalized_text": normalized_text,
            "category": category,
            "computer_vision": cv_result,
            "semantic": semantic,
            "fields": semantic.get("fields", {}),
        }
