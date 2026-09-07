from __future__ import annotations

from fastapi import File, UploadFile
from typing import List

from smart_app import app, hybrid_audit


def _grade(score: float) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    return "D"


@app.post("/api/v4/audit-compatible")
async def audit_compatible(files: List[UploadFile] = File(...)):
    result = await hybrid_audit(files)
    checks = result.get("compliance_summary", {}).get("checks", [])
    audit_report = {}
    for index, check in enumerate(checks):
        status = "COMPLIANT" if check.get("status") == "PASS" else "NON_COMPLIANT"
        audit_report[f"v4_{index}_{check.get('field', 'rule')}"] = {
            "title": check.get("title"),
            "rule": check.get("rule_id"),
            "status": status,
            "detected_value": check.get("detected_value") or "Not detected",
            "details": f"{check.get('reason', '')} {check.get('explanation', '')}".strip(),
            "rule_version": check.get("version"),
            "decision_source": "Dynamic Rule Engine",
        }

    panels = []
    for panel in result.get("panels", []):
        panels.append({
            "filename": panel.get("filename"),
            "ocr_text": panel.get("ocr", {}).get("full_extracted_text", ""),
            "tokens": panel.get("ocr", {}).get("raw_tokens", []),
            "language": panel.get("language"),
            "category": panel.get("category"),
            "computer_vision": panel.get("computer_vision"),
        })

    verdict = result.get("verdict", "NON_COMPLIANT")
    overall_status = "PASS" if verdict == "COMPLIANT" else ("WARNING" if verdict == "REVIEW" else "FAIL")
    score = float(result.get("compliance_score", 0))
    return {
        "inspection_id": result.get("inspection_id"),
        "product_name": result.get("product_name"),
        "timestamp": result.get("created_at"),
        "overall_status": overall_status,
        "compliance_score": score,
        "compliance_grade": _grade(score),
        "violations_count": result.get("compliance_summary", {}).get("failed", 0),
        "warnings_count": 1 if overall_status == "WARNING" else 0,
        "panels": panels,
        "audit_report": audit_report,
        "hybrid_ai": {
            "pipeline": result.get("pipeline"),
            "category": result.get("category"),
            "language": result.get("language"),
            "languages_detected": result.get("languages_detected"),
            "fields": result.get("fields"),
            "explainable_violations": result.get("explainable_violations"),
            "manufacturer_risk": result.get("manufacturer_risk"),
            "offline_ready": result.get("offline_ready"),
            "human_review_required": result.get("human_review_required"),
            "legal_notice": result.get("legal_notice"),
        },
    }
