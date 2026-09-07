from __future__ import annotations

import base64
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

import cv2
import numpy as np
from fastapi import File, Request, UploadFile, HTTPException
from fastapi.responses import HTMLResponse

from app import app, AUDIT_STORE, _extract_product_name, ocr_pipeline, rule_evaluator

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.middleware("http")
async def production_frontend(request: Request, call_next):
    if request.url.path == "/":
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        css = (
            '<link rel="stylesheet" href="/static/immersive.css">\n'
            '<link rel="stylesheet" href="/static/login3d.css">\n'
            '<link rel="stylesheet" href="/static/unified-theme.css">\n'
        )
        html = html.replace("</head>", css + "</head>")
        scripts = (
            '<script src="/static/immersive.js"></script>\n'
            '<script src="/static/login3d.js"></script>\n'
            '<script src="/static/runtime-hotfix.js?v=20260907-stable1"></script>\n'
        )
        html = html.replace("</body>", scripts + "</body>")
        return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
    return await call_next(request)


def _resize(image: np.ndarray, max_edge: int = 512) -> np.ndarray:
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= max_edge:
        return image
    scale = max_edge / float(longest)
    return cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)


def _grade(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    return "D"


@app.post("/api/fast-audit")
async def fast_audit(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="At least one product image is required")
    if len(files) > 4:
        raise HTTPException(status_code=400, detail="Upload up to 4 product panels")

    panels = []
    all_tokens = []
    all_lines = []
    texts = []

    for index, upload in enumerate(files):
        data = await upload.read()
        if len(data) > 12 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{upload.filename}: image exceeds 12 MB")
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail=f"{upload.filename}: unsupported image")

        image = _resize(image, 512)
        tokens = ocr_pipeline.extract_tokens(image)
        lines = ocr_pipeline.assemble_lines(tokens)
        text = "\n".join(line["text"] for line in lines) if lines else " ".join(t["text"] for t in tokens)
        h, w = image.shape[:2]

        preview = _resize(image, 420)
        ok, encoded = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
        image_b64 = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii") if ok else ""

        panels.append({
            "panel_index": index,
            "filename": upload.filename,
            "image_b64": image_b64,
            "dimensions": {"width": w, "height": h},
            "token_count": len(tokens),
            "line_count": len(lines),
            "raw_tokens": tokens,
            "ocr_text": text,
        })
        for token in tokens:
            item = dict(token); item["panel_index"] = index; all_tokens.append(item)
        for line in lines:
            item = dict(line); item["panel_index"] = index; all_lines.append(item)
        texts.append(text)

    aggregated = {
        "raw_tokens": all_tokens,
        "assembled_lines": all_lines,
        "full_extracted_text": "\n\n".join(texts),
    }
    verdict = rule_evaluator.evaluate(aggregated)
    inspection_id = f"LM-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    product_name = _extract_product_name(aggregated["full_extracted_text"], verdict.get("audit_report", {}), files[0].filename or "Product")
    score = float(verdict.get("compliance_score", 0) or 0)

    verdict.update({
        "inspection_id": inspection_id,
        "product_name": product_name,
        "timestamp": datetime.now().isoformat(),
        "panels": panels,
        "panels_count": len(panels),
        "analysis_mode": "stable_single_engine_fast_ocr",
        "compliance_grade": verdict.get("compliance_grade") or _grade(score),
        "report_ready": True,
        "report_endpoint": "/api/export-pdf",
    })
    AUDIT_STORE[inspection_id] = verdict
    return verdict
