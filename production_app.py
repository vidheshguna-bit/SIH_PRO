from __future__ import annotations

import io
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="SmartMetrology AI", version="stable-browser-ocr")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class TextAuditPayload(BaseModel):
    texts: List[str]
    filenames: List[str] = []


class PdfPayload(BaseModel):
    inspection_id: str
    commodity_name: str = "Packaged Commodity"
    overall_status: str = "REVIEW"
    compliance_score: float = 0
    grade: str = "—"
    report: dict = {}


def item(title, rule, status, value, details):
    return {"title": title, "rule": rule, "status": status, "detected_value": value, "details": details}


def present(text, patterns):
    return any(re.search(p, text, re.I | re.S) for p in patterns)


def extract(text, pattern, default="Not detected"):
    m = re.search(pattern, text, re.I)
    return m.group(0).strip() if m else default


def analyse_text(text: str):
    compact = re.sub(r"\s+", " ", text).strip()
    upper = compact.upper()

    qty_ok = present(compact, [r"\bnet\s*(?:wt|weight|qty|quantity)?\s*[:.-]?\s*\d+(?:\.\d+)?\s*(?:kg|g|gm|ml|l|litre|liter)\b", r"\b\d+(?:\.\d+)?\s*(?:kg|g|gm|ml|l)\b"])
    mrp_ok = present(compact, [r"\bmrp\b", r"maximum retail price", r"retail sale price"])
    tax_ok = present(compact, [r"incl(?:usive)?\.?\s*(?:of)?\s*all\s*tax", r"inclusive of taxes", r"incl\.?\s*tax"])
    date_ok = present(compact, [r"\b(?:mfd|mfg|manufactur(?:ed|ing)|packed|pkd)\b.{0,30}\b(?:20\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*20\d{2}\b"])
    care_ok = present(compact, [r"consumer\s*(?:care|complaint|grievance)", r"customer\s*care", r"helpline", r"care@", r"support@"])
    maker_ok = present(compact, [r"manufactur(?:ed|er)", r"packed by", r"marketed by", r"imported by"])
    product_ok = len([w for w in re.findall(r"[A-Za-z]{3,}", compact[:250])]) >= 2
    usp_ok = present(compact, [r"unit\s*(?:sale\s*)?price", r"₹\s*\d+(?:\.\d+)?\s*/\s*(?:g|kg|ml|l)"])

    qty = extract(compact, r"(?:net\s*(?:wt|weight|qty|quantity)?\s*[:.-]?\s*)?\d+(?:\.\d+)?\s*(?:kg|g|gm|ml|l|litre|liter)\b")
    mrp = extract(compact, r"(?:mrp|maximum retail price|retail sale price)\s*[:.-]?\s*(?:rs\.?|₹)?\s*\d+(?:\.\d+)?")
    date = extract(compact, r"(?:mfd|mfg|manufactur(?:ed|ing)|packed|pkd)\s*[:.-]?\s*[A-Za-z0-9/\- ]{3,20}")

    report = {
        "product": item("Product Name", "Rule 6(1)(b)", "COMPLIANT" if product_ok else "WARNING", "Detected from front label" if product_ok else "Not confidently detected", "Common/generic product identity should be clearly declared."),
        "manufacturer": item("Manufacturer / Packer", "Rule 6(1)(a)", "COMPLIANT" if maker_ok else "NON_COMPLIANT", "Declaration detected" if maker_ok else "Not detected", "Manufacturer/packer/importer identity and address are required."),
        "quantity": item("Net Quantity", "Rule 6(1)(c)", "COMPLIANT" if qty_ok else "NON_COMPLIANT", qty, "Net quantity must use an approved standard unit."),
        "mrp": item("MRP inclusive of taxes", "Rule 6(1)(e)", "COMPLIANT" if (mrp_ok and tax_ok) else "NON_COMPLIANT", mrp, "Retail sale price and inclusive-of-taxes declaration are checked."),
        "date": item("Manufacturing / Packing Date", "Rule 6(1)(d)", "COMPLIANT" if date_ok else "WARNING", date, "Month/year manufacturing or packing declaration is checked."),
        "care": item("Consumer Care Details", "Rule 6(1)(da)", "COMPLIANT" if care_ok else "NON_COMPLIANT", "Contact details detected" if care_ok else "Not detected", "Consumer grievance/contact details are mandatory where applicable."),
        "usp": item("Unit Sale Price", "Rule 6(11)", "COMPLIANT" if usp_ok else "WARNING", "Detected" if usp_ok else "Not confidently detected", "Unit sale price is checked where applicable."),
        "quality": item("OCR quality", "Evidence quality policy", "WARNING" if len(compact) < 80 else "COMPLIANT", f"{len(compact)} OCR characters", "Human review is recommended for unclear or incomplete label text."),
    }

    statuses = [v["status"] for v in report.values()]
    fails = sum(s == "NON_COMPLIANT" for s in statuses)
    warns = sum(s == "WARNING" for s in statuses)
    passes = sum(s == "COMPLIANT" for s in statuses)
    score = round((passes + warns * 0.5) / max(1, len(statuses)) * 100)
    overall = "FAIL" if fails else ("WARNING" if warns else "PASS")

    words = re.findall(r"[A-Za-z][A-Za-z0-9&'\-]{2,}", compact[:180])
    blacklist = {"net","weight","quantity","mrp","maximum","retail","price","manufactured","packed","consumer","care"}
    name_words = [w for w in words if w.lower() not in blacklist][:5]
    product_name = " ".join(name_words[:3]) or "Packaged Commodity"

    return report, overall, score, fails, warns, product_name


@app.middleware("http")
async def no_cache_root(request: Request, call_next):
    if request.url.path == "/":
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("</head>", '<link rel="stylesheet" href="/static/immersive.css"><link rel="stylesheet" href="/static/login3d.css"><link rel="stylesheet" href="/static/unified-theme.css"></head>')
        scripts = '<script src="https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js"></script><script src="/static/immersive.js"></script><script src="/static/login3d.js"></script><script src="/static/direct-audit.js?v=20260907-browserocr1"></script>'
        html = html.replace("</body>", scripts + "</body>")
        return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "mode": "browser_ocr_lightweight_backend"}


@app.get("/api/analytics")
def analytics():
    return {"pass_rate": 73.4, "total_audited": 128, "pass_count": 94, "violations_count": 26}


@app.post("/api/text-audit")
def text_audit(payload: TextAuditPayload):
    if not payload.texts:
        raise HTTPException(status_code=400, detail="No OCR text received")
    combined = "\n\n".join(payload.texts)
    report, overall, score, fails, warns, product = analyse_text(combined)
    inspection_id = f"LM-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    return {
        "inspection_id": inspection_id,
        "product_name": product,
        "timestamp": datetime.now().isoformat(),
        "overall_status": overall,
        "compliance_score": score,
        "compliance_grade": "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D",
        "violations_count": fails,
        "warnings_count": warns,
        "panels": [{"panel_index": i, "filename": (payload.filenames[i] if i < len(payload.filenames) else f"panel-{i+1}"), "ocr_text": t, "token_count": len(t.split()), "line_count": len(t.splitlines())} for i, t in enumerate(payload.texts)],
        "panels_count": len(payload.texts),
        "analysis_mode": "browser_tesseract_ocr_plus_deterministic_rule_engine",
        "audit_report": report,
    }


@app.post("/api/export-pdf")
def export_pdf(payload: PdfPayload):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 15)
    c.drawString(45, y, "SmartMetrology AI - Inspection Report")
    y -= 28
    c.setFont("Helvetica", 10)
    lines = [
        f"Inspection ID: {payload.inspection_id}",
        f"Product: {payload.commodity_name}",
        f"Status: {payload.overall_status}",
        f"Compliance score: {payload.compliance_score}%",
        f"Grade: {payload.grade}",
        "",
        "Compliance findings:",
    ]
    for value in payload.report.values():
        if isinstance(value, dict):
            lines.append(f"- {value.get('title','Requirement')}: {value.get('status','')} | {value.get('detected_value','')}")
            lines.append(f"  {value.get('details','')}")
    lines += ["", "Prototype screening report for SIH 2026 evaluation.", "This is not a digitally signed statutory order."]
    for line in lines:
        if y < 55:
            c.showPage(); y = height - 50; c.setFont("Helvetica", 10)
        for part in [line[i:i+95] for i in range(0, max(1, len(line)), 95)] or [""]:
            c.drawString(45, y, part)
            y -= 14
    c.save()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="SmartMetrology_{payload.inspection_id}.pdf"'})
