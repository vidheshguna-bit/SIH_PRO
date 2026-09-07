from __future__ import annotations

import base64
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
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
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
    images: List[str] = []
    image_labels: List[str] = []
    analysis_mode: str = "AI-assisted screening"


def item(title, rule, status, value, details):
    return {"title": title, "rule": rule, "status": status, "detected_value": value, "details": details}


def present(text, patterns):
    return any(re.search(p, text, re.I | re.S) for p in patterns)


def extract(text, pattern, default="Not detected"):
    m = re.search(pattern, text, re.I)
    return m.group(0).strip() if m else default


def analyse_text(text: str):
    compact = re.sub(r"\s+", " ", text).strip()
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
        scripts = '<script src="https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js"></script><script src="/static/immersive.js"></script><script src="/static/login3d.js"></script><script src="/static/direct-audit.js?v=20260907-pdfphotos2"></script>'
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


def decode_data_url(value: str):
    try:
        encoded = value.split(",", 1)[1] if "," in value else value
        return io.BytesIO(base64.b64decode(encoded))
    except Exception:
        return None


def wrap_text(c, text, x, y, max_chars=74, leading=12, font="Helvetica", size=8.5):
    c.setFont(font, size)
    words = str(text or "").split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


@app.post("/api/export-pdf")
def export_pdf(payload: PdfPayload):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    graphite = HexColor("#2F2418")
    gold = HexColor("#C98216")
    emerald = HexColor("#0F7A5A")
    amber = HexColor("#B86A00")
    red = HexColor("#B54233")
    cream = HexColor("#FFFAF0")
    beige = HexColor("#F3ECDF")
    line = HexColor("#DDCDB3")
    muted = HexColor("#786C5C")

    def header(page_no):
        c.setFillColor(graphite)
        c.rect(0, height - 72, width, 72, fill=1, stroke=0)
        c.setFillColor(gold)
        c.roundRect(38, height - 54, 28, 28, 6, fill=1, stroke=0)
        c.setFillColor(graphite)
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(52, height - 44, "SM")
        c.setFillColor(cream)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(78, height - 38, "SmartMetrology AI")
        c.setFont("Helvetica", 8)
        c.setFillColor(HexColor("#E8D9C5"))
        c.drawString(78, height - 52, "AI-assisted Legal Metrology packaged commodity inspection")
        c.setFillColor(muted)
        c.setFont("Helvetica", 7.5)
        c.drawRightString(width - 38, 22, f"Inspection {payload.inspection_id}  •  Page {page_no}")
        c.setStrokeColor(line)
        c.line(38, 30, width - 38, 30)

    def new_page(page_no):
        c.showPage()
        header(page_no)
        return height - 96

    header(1)
    y = height - 102

    status_raw = str(payload.overall_status or "REVIEW").upper()
    if status_raw in {"PASS", "COMPLIANT"}:
        status_label, status_color = "COMPLIANT", emerald
    elif status_raw in {"FAIL", "NON_COMPLIANT", "NON-COMPLIANT"}:
        status_label, status_color = "NON-COMPLIANT", red
    else:
        status_label, status_color = "REVIEW REQUIRED", amber

    c.setFillColor(beige)
    c.roundRect(38, y - 100, width - 76, 92, 12, fill=1, stroke=0)
    c.setFillColor(graphite)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(54, y - 31, payload.commodity_name[:54])
    c.setFillColor(muted)
    c.setFont("Helvetica", 8.5)
    c.drawString(54, y - 48, f"Inspection ID  {payload.inspection_id}")
    c.drawString(54, y - 63, f"Analysis mode  {payload.analysis_mode[:65]}")
    c.setFillColor(status_color)
    c.roundRect(width - 190, y - 78, 136, 47, 10, fill=1, stroke=0)
    c.setFillColor(cream)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width - 122, y - 50, status_label)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(width - 122, y - 66, f"{round(payload.compliance_score)}%  •  Grade {payload.grade}")
    y -= 118

    if payload.images:
        c.setFillColor(graphite)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(38, y, "Submitted Product Evidence")
        y -= 16
        gap = 12
        card_w = (width - 76 - gap) / 2
        card_h = 186
        for i, raw in enumerate(payload.images[:4]):
            if i and i % 2 == 0:
                y -= card_h + 16
            x = 38 + (i % 2) * (card_w + gap)
            card_y = y - card_h
            c.setFillColor(HexColor("#FFF7E8"))
            c.setStrokeColor(line)
            c.roundRect(x, card_y, card_w, card_h, 10, fill=1, stroke=1)
            label = payload.image_labels[i] if i < len(payload.image_labels) else f"Product Panel {i+1}"
            img_buf = decode_data_url(raw)
            if img_buf:
                try:
                    img = ImageReader(img_buf)
                    iw, ih = img.getSize()
                    max_w, max_h = card_w - 18, card_h - 38
                    scale = min(max_w / iw, max_h / ih)
                    dw, dh = iw * scale, ih * scale
                    ix = x + (card_w - dw) / 2
                    iy = card_y + 26 + (max_h - dh) / 2
                    c.drawImage(img, ix, iy, dw, dh, preserveAspectRatio=True, mask="auto")
                except Exception:
                    c.setFillColor(muted)
                    c.setFont("Helvetica", 8)
                    c.drawCentredString(x + card_w / 2, card_y + 88, "Image preview unavailable")
            c.setFillColor(graphite)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawCentredString(x + card_w / 2, card_y + 10, label[:38])
        rows = (min(len(payload.images), 4) + 1) // 2
        y -= rows * (card_h + 16) + 4

    if y < 250:
        y = new_page(2)
        page_no = 2
    else:
        page_no = 1

    c.setFillColor(graphite)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(38, y, "Compliance Findings")
    y -= 17

    for value in payload.report.values():
        if not isinstance(value, dict):
            continue
        if y < 125:
            page_no += 1
            y = new_page(page_no)
        state = str(value.get("status", "REVIEW")).upper()
        state_color = emerald if state == "COMPLIANT" else red if state == "NON_COMPLIANT" else amber
        c.setFillColor(HexColor("#FFFDF8"))
        c.setStrokeColor(line)
        c.roundRect(38, y - 75, width - 76, 68, 8, fill=1, stroke=1)
        c.setFillColor(state_color)
        c.roundRect(49, y - 32, 92, 19, 6, fill=1, stroke=0)
        c.setFillColor(cream)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(95, y - 25, state.replace("_", "-"))
        c.setFillColor(graphite)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(151, y - 24, str(value.get("title", "Requirement"))[:58])
        c.setFillColor(gold)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawRightString(width - 49, y - 24, str(value.get("rule", ""))[:30])
        c.setFillColor(graphite)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(49, y - 45, "Observed:")
        c.setFont("Helvetica", 8)
        c.drawString(92, y - 45, str(value.get("detected_value", "Not established"))[:76])
        c.setFillColor(muted)
        wrap_text(c, value.get("details", "Inspector verification required."), 49, y - 59, 88, 10, "Helvetica", 7.5)
        y -= 82

    if y < 150:
        page_no += 1
        y = new_page(page_no)

    c.setFillColor(HexColor("#E6F5EE"))
    c.setStrokeColor(HexColor("#BFDCCF"))
    c.roundRect(38, y - 78, width - 76, 70, 10, fill=1, stroke=1)
    c.setFillColor(emerald)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y - 27, "Human Review & Legal Use")
    c.setFillColor(graphite)
    wrap_text(c, "This is an AI-assisted SIH 2026 prototype screening report. Findings are evidence for inspector review and are not a digitally signed statutory order or final enforcement determination.", 50, y - 44, 91, 10, "Helvetica", 7.8)

    c.save()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="SmartMetrology_{payload.inspection_id}.pdf"'})
