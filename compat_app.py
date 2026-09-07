from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import List

import cv2
import numpy as np
from fastapi import File, Request, UploadFile
from fastapi.responses import HTMLResponse

from smart_app import app, hybrid_audit


STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.middleware("http")
async def immersive_frontend(request: Request, call_next):
    if request.url.path == "/":
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        if "/static/immersive.css" not in html:
            html = html.replace(
                "</head>",
                '<link rel="stylesheet" href="/static/immersive.css">\n'
                '<link rel="stylesheet" href="/static/login3d.css">\n</head>',
            )
        elif "/static/login3d.css" not in html:
            html = html.replace(
                "</head>",
                '<link rel="stylesheet" href="/static/login3d.css">\n</head>',
            )
        scripts = []
        if "/static/immersive.js" not in html:
            scripts.append('<script src="/static/immersive.js"></script>')
        if "/static/login3d.js" not in html:
            scripts.append('<script src="/static/login3d.js"></script>')
        if "/static/runtime-hotfix.js" not in html:
            scripts.append('<script src="/static/runtime-hotfix.js"></script>')
        if "/static/offline.js" not in html:
            scripts.append('<script src="/static/offline.js"></script>')
        if scripts:
            html = html.replace("</body>", "\n".join(scripts) + "\n</body>")
        return HTMLResponse(html)
    return await call_next(request)


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


async def _optimize_uploads(files: List[UploadFile], max_edge: int = 1600) -> None:
    for upload in files:
        data = await upload.read()
        arr = np.frombuffer(data, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            upload.file = BytesIO(data)
            upload.size = len(data)
            continue
        h, w = image.shape[:2]
        longest = max(h, w)
        if longest > max_edge:
            scale = max_edge / float(longest)
            image = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if ok:
                data = encoded.tobytes()
        upload.file = BytesIO(data)
        upload.size = len(data)


@app.post("/api/v4/audit-compatible")
async def audit_compatible(files: List[UploadFile] = File(...)):
    await _optimize_uploads(files)
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
