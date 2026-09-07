"""
SIH26034 - Legal Metrology Compliance System
FastAPI Backend Application serving Single/Multi-Panel Audits, Bulk Auditing, Analytics, and PDF Export
"""

import os
import io
import csv
import base64
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ocr_engine import OCREngine
from rule_engine import LegalMetrologyRuleEngine

# Initialize FastAPI App
app = FastAPI(
    title="SmartMetrology AI (SIH26034)",
    description="AI-assisted extraction with deterministic Legal Metrology compliance validation",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(SAMPLES_DIR, exist_ok=True)

ocr_pipeline = OCREngine()
rule_evaluator = LegalMetrologyRuleEngine()

# In-Memory Session Audit Ledger
AUDIT_STORE: Dict[str, Dict[str, Any]] = {}
REVIEW_STORE: Dict[str, Dict[str, Any]] = {}
RULE_STORE: Dict[str, Dict[str, Any]] = {
    "LM-PC-001": {"id": "LM-PC-001", "number": "6(1)(a)", "title": "Manufacturer / Packer Declaration", "category": "General Packaged Commodity", "effective_from": "2026-01-01", "effective_to": None, "amendment": "G.S.R. 2026", "status": "ACTIVE", "version": 2026},
    "LM-PC-005": {"id": "LM-PC-005", "number": "6(1)(da)", "title": "Consumer Grievance Details", "category": "General Packaged Commodity", "effective_from": "2026-01-01", "effective_to": None, "amendment": "2022 / 2026", "status": "ACTIVE", "version": 2026},
    "LM-PC-006": {"id": "LM-PC-006", "number": "6(11)", "title": "Unit Sale Price Declaration", "category": "Retail Package", "effective_from": "2022-10-01", "effective_to": None, "amendment": "G.S.R. 2022", "status": "ACTIVE", "version": 2022},
}


class HumanReviewRequest(BaseModel):
    inspection_id: str
    inspector: str
    decision: str
    comments: Optional[str] = ""
    timestamp: Optional[str] = None


class RuleRecord(BaseModel):
    id: str
    number: str
    title: str
    category: str
    effective_from: str
    effective_to: Optional[str] = None
    amendment: Optional[str] = None
    status: str = "INACTIVE"
    version: int


def _read_image_bytes(file_bytes: bytes) -> np.ndarray:
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image from provided bytes.")
    return img


def _extract_product_name(ocr_text: str, rep: dict, default_name: str) -> str:
    """Derive clean product or commodity name for analytics identification."""
    commodity = rep.get("rule_6_1_b_commodity_name", {}).get("detected_value")
    if commodity:
        return f"{commodity}"
    # Check first prominent uppercase line
    for line in ocr_text.splitlines():
        clean = line.strip()
        if len(clean) > 3 and clean.isupper() and not any(k in clean for k in ["MRP", "RS", "NET", "PKD", "MFD"]):
            return clean[:35].title()
    return default_name.rsplit(".", 1)[0].replace("_", " ").title()


def _process_single_product_panels(files_data: List[tuple], product_label: Optional[str] = None) -> Dict[str, Any]:
    """
    Core function to process one or multiple panel photos for a SINGLE product.
    files_data is a list of (filename, file_bytes)
    """
    panels_data = []
    combined_tokens = []
    combined_lines = []
    combined_texts = []

    for index, (filename, content) in enumerate(files_data):
        cv_img = _read_image_bytes(content)
        ocr_result = ocr_pipeline.process(cv_img)

        _, buffer = cv2.imencode('.png', cv_img)
        img_b64 = base64.b64encode(buffer).decode('utf-8')

        panel_info = {
            "panel_index": index,
            "filename": filename,
            "image_b64": f"data:image/png;base64,{img_b64}",
            "dimensions": ocr_result["image_dimensions"],
            "token_count": ocr_result["token_count"],
            "line_count": ocr_result["line_count"],
            "raw_tokens": ocr_result["raw_tokens"]
        }
        panels_data.append(panel_info)

        for token in ocr_result["raw_tokens"]:
            t_copy = dict(token)
            t_copy["panel_index"] = index
            combined_tokens.append(t_copy)

        for line in ocr_result["assembled_lines"]:
            l_copy = dict(line)
            l_copy["panel_index"] = index
            combined_lines.append(l_copy)

        combined_texts.append(ocr_result["full_extracted_text"])

    aggregated_ocr = {
        "raw_tokens": combined_tokens,
        "assembled_lines": combined_lines,
        "full_extracted_text": "\n\n".join(combined_texts)
    }

    audit_verdict = rule_evaluator.evaluate(aggregated_ocr)
    inspection_id = f"LM-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    # Determine product name
    primary_file = files_data[0][0] if files_data else "Product"
    product_name = product_label or _extract_product_name(
        aggregated_ocr["full_extracted_text"],
        audit_verdict["audit_report"],
        primary_file
    )

    audit_verdict["inspection_id"] = inspection_id
    audit_verdict["product_name"] = product_name
    audit_verdict["timestamp"] = datetime.now().isoformat()
    audit_verdict["panels"] = panels_data
    audit_verdict["panels_count"] = len(panels_data)

    # Save into in-memory ledger
    AUDIT_STORE[inspection_id] = audit_verdict

    return audit_verdict


# ---------------------------------------------------------------------------
# AUDIT ENDPOINTS (Single Product & Multi-Panel)
# ---------------------------------------------------------------------------

@app.post("/api/audit")
async def audit_product_labels(files: List[UploadFile] = File(...)):
    """
    Accepts 1 or more images representing multiple panels of a single product.
    Cross-checks all panels and returns a unified compliance report.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No image files provided.")

    files_data = []
    for f in files:
        content = await f.read()
        files_data.append((f.filename, content))

    try:
        audit_result = _process_single_product_panels(files_data)
        return JSONResponse(content=audit_result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Audit processing failed: {str(e)}")


@app.post("/api/audit/bulk")
async def audit_bulk_products(files: List[UploadFile] = File(...)):
    """
    Bulk Auditing Endpoint: Accepts multiple images where EACH file represents a distinct product.
    Audits each product individually, stores it in the ledger, and returns batch metrics.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No image files provided for bulk audit.")

    batch_id = f"BATCH-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    results = []
    pass_cnt = 0
    warn_cnt = 0
    fail_cnt = 0

    for file in files:
        content = await file.read()
        try:
            audit_result = _process_single_product_panels([(file.filename, content)])
            st = audit_result["overall_status"]
            if st == "PASS":
                pass_cnt += 1
            elif st == "WARNING":
                warn_cnt += 1
            else:
                fail_cnt += 1

            # Thumbnail summary for the batch list
            first_panel = audit_result["panels"][0] if audit_result["panels"] else {}
            results.append({
                "inspection_id": audit_result["inspection_id"],
                "product_name": audit_result["product_name"],
                "filename": file.filename,
                "overall_status": st,
                "compliance_score": audit_result["compliance_score"],
                "compliance_grade": audit_result["compliance_grade"],
                "violations_count": audit_result["violations_count"],
                "warnings_count": audit_result["warnings_count"],
                "panels_count": audit_result["panels_count"],
                "thumbnail": first_panel.get("image_b64", ""),
                "timestamp": audit_result["timestamp"]
            })
        except Exception as e:
            continue

    return JSONResponse(content={
        "batch_id": batch_id,
        "total_processed": len(results),
        "pass_count": pass_cnt,
        "warnings_count": warn_cnt,
        "violations_count": fail_cnt,
        "pass_rate": round((pass_cnt / max(1, len(results))) * 100, 1),
        "products": results
    })


@app.get("/api/audit/product/{inspection_id}")
async def get_audited_product(inspection_id: str):
    """Retrieve full audit data (including canvas image base64 and bboxes) by inspection ID."""
    if inspection_id not in AUDIT_STORE:
        raise HTTPException(status_code=404, detail="Product audit record not found.")
    return JSONResponse(content=AUDIT_STORE[inspection_id])


# ---------------------------------------------------------------------------
# SAMPLES & BENCHMARKS
# ---------------------------------------------------------------------------

@app.get("/api/sample/{sample_name}")
async def audit_sample(sample_name: str):
    """1-Click test runner for pre-loaded benchmark samples."""
    valid_samples = {
        "compliant": ("sample_compliant.png", "Royal Delight Cookies (Biscuits)"),
        "illegal_units": ("sample_illegal_units.png", "Crunchy Masala Chips (Rule 12 gms)"),
        "mismatched_usp": ("sample_mismatched_usp.png", "Himalayan Desi Ghee (Math Error)"),
        "missing_grievance": ("sample_missing_grievance.png", "Fresh Farm Atta (Missing Helpline)")
    }

    if sample_name not in valid_samples:
        raise HTTPException(
            status_code=404,
            detail=f"Sample '{sample_name}' not found. Available: {list(valid_samples.keys())}"
        )

    filename, product_label = valid_samples[sample_name]
    file_path = os.path.join(SAMPLES_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="Sample image missing on disk.")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    audit_result = _process_single_product_panels([(filename, file_bytes)], product_label=product_label)
    return JSONResponse(content=audit_result)


# ---------------------------------------------------------------------------
# ANALYTICS & INSIGHTS ENGINE
# ---------------------------------------------------------------------------

@app.get("/api/analytics")
async def get_analytics():
    """
    Computes aggregated compliance analytics across all audited products in session.
    Returns KPIs, defect distributions across statutory rules, and product audit history table.
    """
    # If store is empty, automatically load demo batch so UI is never blank
    if not AUDIT_STORE:
        _populate_demo_batch()

    total_products = len(AUDIT_STORE)
    pass_cnt = sum(1 for p in AUDIT_STORE.values() if p.get("overall_status") == "PASS")
    warn_cnt = sum(1 for p in AUDIT_STORE.values() if p.get("overall_status") == "WARNING")
    fail_cnt = sum(1 for p in AUDIT_STORE.values() if p.get("overall_status") == "FAIL")

    scores = [p.get("compliance_score", 0.0) for p in AUDIT_STORE.values()]
    avg_score = round(sum(scores) / max(1, total_products), 1)

    # Defect Frequency per Statutory Legal Rule
    defect_counts = {
        "rule_6_1_e": 0,    # MRP & Tax phrase missing
        "rule_12_units": 0, # Prohibited metric symbols 'gms', 'ltr'
        "rule_6_1_11_usp": 0, # USP math discrepancies
        "rule_6_1_d_date": 0, # Mfg date missing
        "rule_6_1_da_care": 0, # Grievance details missing
        "rule_6_1_a_b": 0    # Manufacturer / Commodity identification
    }

    products_list = []
    for p in reversed(list(AUDIT_STORE.values())):
        rep = p.get("audit_report", {})

        # Count specific rule defects
        if rep.get("rule_6_1_e_mrp", {}).get("status") in ["FAIL", "NON_COMPLIANT"]:
            defect_counts["rule_6_1_e"] += 1
        if rep.get("rule_6_1_c_net_quantity", {}).get("is_illegal_symbol"):
            defect_counts["rule_12_units"] += 1
        if rep.get("rule_6_1_11_unit_sale_price", {}).get("math_consistent") is False or rep.get("rule_6_1_11_unit_sale_price", {}).get("status") == "NON_COMPLIANT":
            defect_counts["rule_6_1_11_usp"] += 1
        if rep.get("rule_6_1_d_mfg_date", {}).get("status") in ["FAIL", "NON_COMPLIANT"]:
            defect_counts["rule_6_1_d_date"] += 1
        if rep.get("rule_6_1_da_consumer_grievance", {}).get("status") in ["FAIL", "NON_COMPLIANT", "WARNING"]:
            defect_counts["rule_6_1_da_care"] += 1
        if rep.get("rule_6_1_a_manufacturer", {}).get("status") in ["FAIL", "WARNING"]:
            defect_counts["rule_6_1_a_b"] += 1
        panels_list = p.get("panels") or []
        first_panel = panels_list[0] if len(panels_list) > 0 else {}
        products_list.append({
            "inspection_id": p.get("inspection_id"),
            "product_name": p.get("product_name", "Packaged Commodity"),
            "overall_status": p.get("overall_status"),
            "compliance_score": p.get("compliance_score"),
            "compliance_grade": p.get("compliance_grade"),
            "violations_count": p.get("violations_count", 0),
            "warnings_count": p.get("warnings_count", 0),
            "panels_count": p.get("panels_count", 1),
            "violations_summary": p.get("violations_summary", []),
            "thumbnail": first_panel.get("image_b64", ""),
            "timestamp": p.get("timestamp")
        })

    return JSONResponse(content={
        "total_audited": total_products,
        "pass_count": pass_cnt,
        "warnings_count": warn_cnt,
        "violations_count": fail_cnt,
        "pass_rate": round((pass_cnt / max(1, total_products)) * 100, 1),
        "warn_rate": round((warn_cnt / max(1, total_products)) * 100, 1),
        "fail_rate": round((fail_cnt / max(1, total_products)) * 100, 1),
        "avg_compliance_score": avg_score,
        "defect_frequency": defect_counts,
        "products": products_list
    })


@app.post("/api/analytics/demo")
async def load_demo_analytics():
    """Explicit endpoint to populate the analytics store with a diverse 12-product benchmark dataset."""
    _populate_demo_batch(force=True)
    return await get_analytics()


def _populate_demo_batch(force: bool = False):
    """Internal helper to seed realistic packaged commodities for SIH evaluation."""
    if AUDIT_STORE and not force:
        return

    demo_products = [
        ("Royal Delight Butter Cookies", "Biscuits", "PASS", 100.0, "A+ (Fully Compliant)", 0, 0, []),
        ("Crunchy Masala Potato Chips", "Potato Chips", "FAIL", 60.0, "F (Defects Detected)", 1, 1, [
            {"severity": "NON_COMPLIANT", "rule": "Rule 6(1)(e)", "title": "Tax Missing", "details": "Mandatory 'inclusive of all taxes' omitted."},
            {"severity": "WARNING", "rule": "Rule 12(1)", "title": "Illegal Unit", "details": "Non-compliant symbol 'gms' detected."}
        ]),
        ("Himalayan Pure Cow Ghee", "Ghee", "FAIL", 80.0, "F (Defects Detected)", 1, 0, [
            {"severity": "NON_COMPLIANT", "rule": "Rule 6(1)(11)", "title": "Math Error", "details": "Declared USP ₹0.25/g vs Calculated ₹0.40/g."}
        ]),
        ("Golden Harvest Stoneground Atta", "Atta", "FAIL", 80.0, "F (Defects Detected)", 2, 0, [
            {"severity": "NON_COMPLIANT", "rule": "Rule 6(1)(da)", "title": "Missing Grievance", "details": "No customer care email or helpline."},
            {"severity": "NON_COMPLIANT", "rule": "Rule 6(1)(d)", "title": "Missing Date", "details": "Month and Year of packing omitted."}
        ]),
        ("Sunrise Pure Assam Tea", "Tea", "PASS", 100.0, "A+ (Fully Compliant)", 0, 0, []),
        ("UltraClean Active Detergent Bar", "Detergent Bar", "WARNING", 85.0, "B (Compliant with Warning)", 0, 1, [
            {"severity": "WARNING", "rule": "Rule 12(1)", "title": "Symbol Period", "details": "Used non-standard 'gm.' with punctuation."}
        ]),
        ("Nourish Farm Fresh Toned Milk", "Milk", "PASS", 100.0, "A+ (Fully Compliant)", 0, 0, []),
        ("Heritage Cold-Pressed Mustard Oil", "Edible Oil", "FAIL", 75.0, "F (Defects Detected)", 1, 0, [
            {"severity": "NON_COMPLIANT", "rule": "Rule 6(1)(e)", "title": "Tax Missing", "details": "Omitted mandatory phrase 'inclusive of all taxes'."}
        ]),
        ("SpiceKing Kashmiri Red Chilli Powder", "Spices", "WARNING", 80.0, "B (Partial Compliance)", 0, 1, [
            {"severity": "WARNING", "rule": "Rule 6(1)(da)", "title": "Partial Grievance", "details": "Customer care phone detected, but email missing."}
        ]),
        ("Crisp Delight Salted Cashews", "Namkeen", "PASS", 100.0, "A+ (Fully Compliant)", 0, 0, []),
        ("Zesty Farmhouse Tomato Ketchup", "Sauce", "FAIL", 80.0, "F (Defects Detected)", 1, 0, [
            {"severity": "NON_COMPLIANT", "rule": "Rule 6(1)(11)", "title": "USP Mismatch", "details": "Declared rate ₹0.15/g deviates from calculated ₹0.28/g."}
        ]),
        ("AquaPure Natural Drinking Water", "Packaged Drinking Water", "PASS", 100.0, "A+ (Fully Compliant)", 0, 0, [])
    ]

    for name, commodity, st, score, grade, v_cnt, w_cnt, violations in demo_products:
        uid = f"LM-BATCH-{uuid.uuid4().hex[:6].upper()}"
        AUDIT_STORE[uid] = {
            "inspection_id": uid,
            "product_name": name,
            "overall_status": st,
            "compliance_score": score,
            "compliance_grade": grade,
            "violations_count": v_cnt,
            "warnings_count": w_cnt,
            "passed_rules_count": 7 - v_cnt - w_cnt,
            "panels_count": 1 if "Cookies" not in name else 2,
            "violations_summary": violations,
            "audit_report": {
                "rule_6_1_e_mrp": {
                    "rule": "Rule 6(1)(e)",
                    "title": "Maximum Retail Price (MRP)",
                    "status": "NON_COMPLIANT" if any(v["rule"] == "Rule 6(1)(e)" for v in violations) else "COMPLIANT",
                    "detected_value": "₹ 120.00",
                    "details": "Statutory MRP and tax clause evaluation."
                },
                "rule_6_1_c_net_quantity": {
                    "rule": "Rule 6(1)(c) & Rule 12",
                    "title": "Net Quantity & SI Units",
                    "status": "WARNING" if any(v["rule"] == "Rule 12(1)" for v in violations) else "COMPLIANT",
                    "detected_value": "250 g",
                    "is_illegal_symbol": any(v["rule"] == "Rule 12(1)" for v in violations),
                    "details": "Standard SI unit validation."
                },
                "rule_6_1_11_unit_sale_price": {
                    "rule": "Rule 6(1)(11)",
                    "title": "Unit Sale Price (USP)",
                    "status": "NON_COMPLIANT" if any(v["rule"] == "Rule 6(1)(11)" for v in violations) else "COMPLIANT",
                    "math_consistent": not any(v["rule"] == "Rule 6(1)(11)" for v in violations),
                    "detected_value": "₹ 0.48 / g",
                    "details": "USP mathematical consistency verification."
                },
                "rule_6_1_d_mfg_date": {
                    "rule": "Rule 6(1)(d)",
                    "title": "Date of Mfg / Packing",
                    "status": "NON_COMPLIANT" if any(v["rule"] == "Rule 6(1)(d)" for v in violations) else "COMPLIANT",
                    "detected_value": "08/2026",
                    "details": "Manufacturing date presence."
                },
                "rule_6_1_da_consumer_grievance": {
                    "rule": "Rule 6(1)(da)",
                    "title": "Consumer Grievance",
                    "status": "NON_COMPLIANT" if any(v["rule"] == "Rule 6(1)(da)" for v in violations) else "COMPLIANT",
                    "detected_value": "1800-202-3344",
                    "details": "Customer care telephone and email address."
                },
                "rule_6_1_a_manufacturer": {
                    "rule": "Rule 6(1)(a)",
                    "title": "Manufacturer Identity",
                    "status": "COMPLIANT",
                    "detected_value": "Packer Ltd",
                    "details": "Registered manufacturer address."
                },
                "rule_6_1_b_commodity_name": {
                    "rule": "Rule 6(1)(b)",
                    "title": "Commodity Name",
                    "status": "COMPLIANT",
                    "detected_value": commodity,
                    "details": "Generic classification."
                }
            },
            "timestamp": datetime.now().isoformat(),
            "panels": []
        }


@app.get("/api/analytics/export-csv")
async def export_analytics_csv():
    """Generates and downloads a CSV spreadsheet of the entire compliance audit ledger."""
    if not AUDIT_STORE:
        _populate_demo_batch()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Inspection Reference ID",
        "Timestamp",
        "Product Name / Commodity",
        "Overall Statutory Verdict",
        "Compliance Score (%)",
        "Grade",
        "Panels Scanned",
        "Statutory Violations Count",
        "Warnings Count",
        "Violations & Defect Summary"
    ])

    for p in AUDIT_STORE.values():
        v_summary = " | ".join([f"{v.get('rule')}: {v.get('details')}" for v in p.get("violations_summary", [])])
        writer.writerow([
            p.get("inspection_id"),
            p.get("timestamp"),
            p.get("product_name"),
            p.get("overall_status"),
            p.get("compliance_score"),
            p.get("compliance_grade"),
            p.get("panels_count", 1),
            p.get("violations_count", 0),
            p.get("warnings_count", 0),
            v_summary
        ])

    csv_data = output.getvalue()
    filename = f"Legal_Metrology_Audit_Ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(content=csv_data, media_type="text/csv", headers=headers)


# ---------------------------------------------------------------------------
# PDF EXPORT & STATIC SERVING
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ACCOUNTABLE HUMAN REVIEW & VERSIONED RULE ADMINISTRATION
# ---------------------------------------------------------------------------

@app.post("/api/reviews")
async def record_human_review(payload: HumanReviewRequest):
    """Record the accountable inspector decision separately from AI extraction."""
    record = payload.model_dump()
    record["timestamp"] = payload.timestamp or datetime.now().isoformat()
    REVIEW_STORE[payload.inspection_id] = record
    return {"saved": True, "review": record}


@app.get("/api/reviews/{inspection_id}")
async def get_human_review(inspection_id: str):
    if inspection_id not in REVIEW_STORE:
        raise HTTPException(status_code=404, detail="Human review has not been recorded.")
    return REVIEW_STORE[inspection_id]


@app.get("/api/rules")
async def list_versioned_rules():
    return {"rules": list(RULE_STORE.values()), "decision_mode": "deterministic"}


@app.post("/api/rules", status_code=201)
async def create_versioned_rule(payload: RuleRecord):
    key = f"{payload.id}:v{payload.version}"
    if key in RULE_STORE:
        raise HTTPException(status_code=409, detail="This immutable rule version already exists.")
    record = payload.model_dump()
    RULE_STORE[key] = record
    return {"created": True, "rule": record}


@app.put("/api/rules/{rule_key:path}")
async def update_rule_status(rule_key: str, payload: RuleRecord):
    """Administrative metadata/status update; legal text versions remain separately addressable."""
    if rule_key not in RULE_STORE:
        raise HTTPException(status_code=404, detail="Rule version not found.")
    record = payload.model_dump()
    RULE_STORE[rule_key] = record
    return {"updated": True, "rule": record}


class PDFExportRequest(BaseModel):
    inspection_id: str
    commodity_name: Optional[str] = "Packaged Commodity"
    overall_status: str
    compliance_score: float
    grade: str
    report: dict


@app.post("/api/export-pdf")
async def export_inspection_certificate(payload: PDFExportRequest):
    """Generates an official Government of India Legal Metrology Compliance Inspection Certificate."""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#0B2545'),
        alignment=1
    )
    sub_title = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#475569'),
        alignment=1
    )
    section_head = ParagraphStyle(
        'SectionHead',
        parent=styles['Heading2'],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=10,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1E293B')
    )

    elements = []

    elements.append(Paragraph("<b>MINISTRY OF CONSUMER AFFAIRS, FOOD & PUBLIC DISTRIBUTION</b>", title_style))
    elements.append(Paragraph("Department of Consumer Affairs • Legal Metrology Division • Government of India", sub_title))
    elements.append(Paragraph("<b>STATUTORY COMPLIANCE INSPECTION REPORT (RULE 6 & RULE 12 AUDIT)</b>", title_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#F47C20'), spaceBefore=4, spaceAfter=8))

    status_color = colors.HexColor('#10B981') if payload.overall_status == "PASS" else colors.HexColor('#EF4444')
    if payload.overall_status == "WARNING":
        status_color = colors.HexColor('#F59E0B')

    meta_data = [
        [
            Paragraph(f"<b>Inspection Reference:</b> {payload.inspection_id}", body_style),
            Paragraph(f"<b>Date & Time:</b> {datetime.now().strftime('%d-%b-%Y %H:%M:%S IST')}", body_style)
        ],
        [
            Paragraph(f"<b>Statutory Standard:</b> Legal Metrology Rules, 2011", body_style),
            Paragraph(f"<b>Commodity Evaluated:</b> {payload.commodity_name}", body_style)
        ],
        [
            Paragraph(f"<b>Compliance Score:</b> <b>{payload.compliance_score}%</b> ({payload.grade})", body_style),
            Paragraph(f"<b>Overall Statutory Verdict:</b> <font color='{status_color}'><b>{payload.overall_status}</b></font>", body_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[260, 270])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Statutory Declarations Verification Matrix:</b>", section_head))

    table_data = [
        [
            Paragraph("<b>Rule / Clause</b>", body_style),
            Paragraph("<b>Mandatory Declaration</b>", body_style),
            Paragraph("<b>Detected Value</b>", body_style),
            Paragraph("<b>Status</b>", body_style),
            Paragraph("<b>Audit Details</b>", body_style)
        ]
    ]

    for _, r_data in payload.report.items():
        st = r_data.get("status", "FAIL")
        st_color = '#10B981' if st == "COMPLIANT" else ('#F59E0B' if st == "WARNING" else '#EF4444')

        table_data.append([
            Paragraph(f"<b>{r_data.get('rule', 'Rule')}</b>", body_style),
            Paragraph(r_data.get('title', ''), body_style),
            Paragraph(r_data.get('detected_value') or "<i>Not Detected</i>", body_style),
            Paragraph(f"<font color='{st_color}'><b>{st}</b></font>", body_style),
            Paragraph(r_data.get('details', '')[:140], body_style)
        ])

    rule_table = Table(table_data, colWidths=[75, 100, 95, 75, 185])
    rule_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#94A3B8')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(rule_table)
    elements.append(Spacer(1, 15))

    elements.append(Paragraph("<b>Statutory Enforcement Advisory:</b>", section_head))
    notice_text = (
        "This automated inspection certificate is issued pursuant to the provisions of the Legal Metrology "
        "Act, 2009 and the Legal Metrology (Packaged Commodities) Rules, 2011. Any non-compliance (such as missing "
        "tax declarations, prohibited metric abbreviations under Rule 12, or mismatched Unit Sale Price under Rule 6) "
        "constitutes an offence punishable under Section 36 of the Legal Metrology Act, 2009."
    )
    elements.append(Paragraph(notice_text, body_style))
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("<i>Digitally verified by Legal Metrology Inspection Portal (SIH26034 Engine)</i>", sub_title))

    doc.build(elements)
    pdf_buffer.seek(0)

    headers = {
        'Content-Disposition': f'attachment; filename="Legal_Metrology_Inspection_{payload.inspection_id}.pdf"'
    }
    return Response(content=pdf_buffer.getvalue(), media_type="application/pdf", headers=headers)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Legal Metrology Inspection Dashboard Initializing...</h1>")
