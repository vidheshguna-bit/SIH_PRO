from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
from fastapi import File, UploadFile, HTTPException
from pydantic import BaseModel

from app import app
from dynamic_rule_engine import DynamicRuleEngine
from hybrid_ai import HybridAIAnalyzer
from inspection_db import initialize_database, save_inspection, list_inspections, manufacturer_risk, add_complaint, enqueue_offline, pending_sync


hybrid_analyzer = HybridAIAnalyzer()
dynamic_rules = DynamicRuleEngine()
initialize_database()


class DynamicRulePayload(BaseModel):
    id: str
    category: str
    field: str
    title: str
    severity: str = "major"
    required: bool = True
    pattern: Optional[str] = None
    explanation: str = ""
    source_note: str = "Prototype rule profile. Verify against the currently applicable statutory text before enforcement use."
    version: int = 1
    active: bool = True


class ComplaintPayload(BaseModel):
    manufacturer: str
    product_name: Optional[str] = None
    complaint_type: str
    details: str = ""


class OfflinePayload(BaseModel):
    record_id: str
    payload: Dict[str, Any]


def _decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unsupported or corrupted image")
    return image


def _pick_product_name(fields: Dict[str, Any], text: str) -> str:
    for key in ("product_name", "commodity_name", "model_number"):
        if fields.get(key):
            return str(fields[key])[:120]
    for line in text.splitlines():
        cleaned = line.strip()
        if 3 < len(cleaned) < 80 and not any(token in cleaned.lower() for token in ("mrp", "net", "batch", "mfg", "exp")):
            return cleaned
    return "Packaged Commodity"


def _field_keywords(field: str) -> List[str]:
    return {
        "mrp": ["mrp", "retail", "₹", "rs"],
        "net_quantity": ["net", "qty", "quantity", "weight", "kg", " g", "ml"],
        "manufacturer": ["manufacturer", "manufactured", "packed by", "निर्माता", "உற்பத்தியாளர்", "తయారీదారు"],
        "manufacturer_address": ["address", "முகவரி", "पता", "చిరునామా"],
        "consumer_care": ["consumer", "customer", "helpline", "complaint", "email", "phone"],
        "manufactured_date": ["mfg", "mfd", "manufactured", "packed"],
        "batch_number": ["batch", "lot"],
        "expiry_date": ["exp", "expiry", "best before"],
        "model_number": ["model"],
    }.get(field, [field.replace("_", " ")])


def _evidence_for_rule(rule: Dict[str, Any], panels: List[Dict[str, Any]]) -> Dict[str, Any]:
    keywords = _field_keywords(rule["field"])
    best = None
    for panel_index, panel in enumerate(panels):
        for token in panel.get("ocr", {}).get("raw_tokens", []):
            text = str(token.get("text", ""))
            if any(keyword.lower() in text.lower() for keyword in keywords):
                candidate = {
                    "panel_index": panel_index,
                    "token_text": text,
                    "bbox": token.get("bbox"),
                    "normalized_bbox": token.get("normalized_bbox"),
                    "confidence": token.get("confidence"),
                }
                if best is None or float(candidate.get("confidence") or 0) > float(best.get("confidence") or 0):
                    best = candidate
    if best:
        return {"type": "highlight", **best, "message": "Related declaration region detected; inspector should verify the highlighted area."}
    return {
        "type": "absence-evidence",
        "panel_index": None,
        "bbox": None,
        "message": "No matching declaration region was detected across the submitted panels.",
    }


@app.get("/api/v4/capabilities")
async def v4_capabilities():
    return {
        "version": "4.0",
        "architecture": [
            "multi-image scanner",
            "computer vision preprocessing and layout analysis",
            "OCR with spatial bounding boxes",
            "Tamil/Hindi/English/Telugu script detection and normalization",
            "product category classification",
            "semantic/LLM verification adapter with offline fallback",
            "dynamic deterministic rule engine",
            "explainable evidence-linked compliance report",
            "historical manufacturer risk database",
            "offline inspection sync queue",
        ],
        "decision_boundary": "AI extracts, classifies and explains. Deterministic versioned rules decide compliance.",
    }


@app.post("/api/v4/hybrid-audit")
async def hybrid_audit(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="At least one product image is required")
    if len(files) > 8:
        raise HTTPException(status_code=400, detail="Maximum 8 images per product inspection")

    panels: List[Dict[str, Any]] = []
    merged_fields: Dict[str, Any] = {}
    languages: Dict[str, int] = {}
    categories: Dict[str, float] = {}
    full_text_parts: List[str] = []

    for upload in files:
        content = await upload.read()
        if len(content) > 12 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{upload.filename}: image exceeds 12 MB")
        try:
            image = _decode_image(content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{upload.filename}: {exc}")

        result = hybrid_analyzer.analyze(image)
        text = result.get("ocr", {}).get("full_extracted_text", "")
        full_text_parts.append(text)
        merged_fields.update({k: v for k, v in result.get("fields", {}).items() if v})
        language_code = result.get("language", {}).get("code", "en")
        languages[language_code] = languages.get(language_code, 0) + 1
        category = result.get("category", {}).get("category", "general")
        confidence = float(result.get("category", {}).get("confidence", 0))
        categories[category] = categories.get(category, 0.0) + confidence
        panels.append({"filename": upload.filename, **result})

    dominant_language = max(languages, key=languages.get) if languages else "en"
    category = max(categories, key=categories.get) if categories else "general"
    combined_text = "\n".join(full_text_parts)
    rule_result = dynamic_rules.evaluate(merged_fields, category)

    explainable_failures = []
    for failed in [r for r in rule_result["results"] if r["status"] == "FAIL"]:
        explainable_failures.append({
            "rule_id": failed["rule_id"],
            "requirement": failed["title"],
            "reason": failed["reason"],
            "explanation": failed["explanation"],
            "evidence": _evidence_for_rule(failed, panels),
            "rule_version": failed["version"],
            "source_note": failed["source_note"],
        })

    inspection_id = f"LM-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    product_name = _pick_product_name(merged_fields, combined_text)
    manufacturer = str(merged_fields.get("manufacturer") or "Unknown")
    history_risk = manufacturer_risk(manufacturer) if manufacturer != "Unknown" else None

    response = {
        "inspection_id": inspection_id,
        "created_at": datetime.utcnow().isoformat(),
        "pipeline": "Image → CV/Layout → OCR → Language → Category → Semantic/LLM → Dynamic Rule Engine → Explainable Report",
        "product_name": product_name,
        "category": category,
        "language": dominant_language,
        "languages_detected": languages,
        "manufacturer": manufacturer,
        "fields": merged_fields,
        "compliance_score": rule_result["score"],
        "verdict": rule_result["verdict"],
        "compliance_summary": {
            "passed": rule_result["passed"],
            "failed": rule_result["failed"],
            "checks": rule_result["results"],
        },
        "explainable_violations": explainable_failures,
        "manufacturer_risk": history_risk,
        "panels": panels,
        "offline_ready": True,
        "human_review_required": bool(explainable_failures) or rule_result["score"] < 95,
        "legal_notice": "Prototype screening output. Rule profiles and AI evidence require authorized inspector verification before statutory action.",
    }

    save_inspection(response)
    return response


@app.get("/api/v4/rules")
async def v4_rules(category: Optional[str] = None):
    return {"rules": dynamic_rules.list_rules(category), "update_model_required": False}


@app.post("/api/v4/rules", status_code=201)
async def v4_add_rule(payload: DynamicRulePayload):
    return {"saved": True, "rule": dynamic_rules.upsert(payload.model_dump()), "model_retraining_required": False}


@app.get("/api/v4/history")
async def v4_history(limit: int = 50):
    return {"items": list_inspections(limit)}


@app.get("/api/v4/manufacturer-risk/{manufacturer}")
async def v4_manufacturer_risk(manufacturer: str):
    return manufacturer_risk(manufacturer)


@app.post("/api/v4/complaints", status_code=201)
async def v4_complaint(payload: ComplaintPayload):
    add_complaint(payload.manufacturer, payload.product_name, payload.complaint_type, payload.details)
    return {"saved": True, "manufacturer_risk": manufacturer_risk(payload.manufacturer)}


@app.post("/api/v4/offline/queue", status_code=202)
async def v4_offline_queue(payload: OfflinePayload):
    enqueue_offline(payload.record_id, payload.payload)
    return {"queued": True, "record_id": payload.record_id}


@app.get("/api/v4/offline/pending")
async def v4_offline_pending():
    return {"pending": pending_sync()}
