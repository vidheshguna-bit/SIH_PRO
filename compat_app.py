from __future__ import annotations

import base64
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List

import cv2
import numpy as np
from fastapi import File, Request, UploadFile, HTTPException
from fastapi.responses import HTMLResponse

from app import AUDIT_STORE, _extract_product_name, ocr_pipeline, rule_evaluator
from ocr_engine import PreprocessingPipeline
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
                '<link rel="stylesheet" href="/static/login3d.css">\n'
                '<link rel="stylesheet" href="/static/unified-theme.css">\n</head>',
            )
        else:
            if "/static/login3d.css" not in html:
                html = html.replace("</head>", '<link rel="stylesheet" href="/static/login3d.css">\n</head>')
            if "/static/unified-theme.css" not in html:
                html = html.replace("</head>", '<link rel="stylesheet" href="/static/unified-theme.css">\n</head>')
        scripts = []
        if "/static/immersive.js" not in html:
            scripts.append('<script src="/static/immersive.js"></script>')
        if "/static/login3d.js" not in html:
            scripts.append('<script src="/static/login3d.js"></script>')
        scripts.append('<script src="/static/runtime-hotfix.js?v=20260907-1326"></script>')
        if (STATIC_DIR / "offline.js").exists() and "/static/offline.js" not in html:
            scripts.append('<script src="/static/offline.js"></script>')
        html = html.replace("</body>", "\n".join(scripts) + "\n</body>")
        return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
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


def _resize_image(image: np.ndarray, max_edge: int = 800) -> np.ndarray:
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= max_edge:
        return image
    scale = max_edge / float(longest)
    return cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)


def _fast_ocr(image: np.ndarray) -> dict:
    image = _resize_image(image)
    enhanced_bgr, _ = PreprocessingPipeline.enhance_for_ocr(image)
    tokens = ocr_pipeline.extract_tokens(enhanced_bgr)
    lines = ocr_pipeline.assemble_lines(tokens)
    text = "\n".join(line["text"] for line in lines) if lines else " ".join(token["text"] for token in tokens)
    h, w = image.shape[:2]
    return {
        "image": image,
        "image_dimensions": {"width": w, "height": h},
        "raw_tokens": tokens,
        "assembled_lines": lines,
        "full_extracted_text": text,
        "token_count": len(tokens),
        "line_count": len(lines),
    }


@app.post("/api/fast-audit")
async def fast_audit(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="At least one product image is required")
    if len(files) > 4:
        raise HTTPException(status_code=400, detail="Upload up to 4 product panels")

    panels = []
    combined_tokens = []
    combined_lines = []
    combined_texts = []

    for index, upload in enumerate(files):
        data = await upload.read()
        if len(data) > 12 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{upload.filename}: image exceeds 12 MB")
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail=f"{upload.filename}: unsupported or corrupted image")

        result = _fast_ocr(image)
        preview = _resize_image(result["image"], 640)
        ok, encoded = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 68])
        image_b64 = ""
        if ok:
            image_b64 = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")

        panel = {
            "panel_index": index,
            "filename": upload.filename,
            "image_b64": image_b64,
            "dimensions": result["image_dimensions"],
            "token_count": result["token_count"],
            "line_count": result["line_count"],
            "raw_tokens": result["raw_tokens"],
            "ocr_text": result["full_extracted_text"],
        }
        panels.append(panel)

        for token in result["raw_tokens"]:
            item = dict(token)
            item["panel_index"] = index
            combined_tokens.append(item)
        for line in result["assembled_lines"]:
            item = dict(line)
            item["panel_index"] = index
            combined_lines.append(item)
        combined_texts.append(result["full_extracted_text"])

    aggregated_ocr = {
        "raw_tokens": combined_tokens,
        "assembled_lines": combined_lines,
        "full_extracted_text": "\n\n".join(combined_texts),
    }
    verdict = rule_evaluator.evaluate(aggregated_ocr)
    inspection_id = f"LM-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    primary_name = files[0].filename or "Product"
    product_name = _extract_product_name(aggregated_ocr["full_extracted_text"], verdict.get("audit_report", {}), primary_name)

    verdict["inspection_id"] = inspection_id
    verdict["product_name"] = product_name
    verdict["timestamp"] = datetime.now().isoformat()
    verdict["panels"] = panels
    verdict["panels_count"] = len(panels)
    verdict["analysis_mode"] = "fast_single-pass_ocr"
    verdict["report_ready"] = True
    verdict["report_endpoint"] = "/api/export-pdf"
    AUDIT_STORE[inspection_id] = verdict
    return verdict


async def _optimize_uploads(files: List[UploadFile], max_edge: int = 1200) -> None:
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
            ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 86])
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
