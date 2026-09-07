"""
SIH26034 - Legal Metrology Compliance System
FastAPI Backend Application serving OCR, Deterministic Statutory Rule Engine, and PDF Reports
"""

import os
import io
import base64
import uuid
from datetime import datetime
from typing import List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ocr_engine import OCREngine
from rule_engine import LegalMetrologyRuleEngine

# Initialize Engines
app = FastAPI(
    title="Legal Metrology Compliance Audit System (SIH26034)",
    description="Automated Inspection System for Packaged Commodities Rules, 2011",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(SAMPLES_DIR, exist_ok=True)

ocr_pipeline = OCREngine()
rule_evaluator = LegalMetrologyRuleEngine()


def _read_image_bytes(file_bytes: bytes) -> np.ndarray:
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image from provided bytes.")
    return img


@app.post("/api/audit")
async def audit_product_labels(files: List[UploadFile] = File(...)):
    """
    Multi-panel and single-panel label audit endpoint.
    Accepts 1 or more label images (front, back, nutritional side panels).
    """
    if not files:
        raise HTTPException(status_code=400, detail="No image files provided.")

    panels_data = []
    combined_tokens = []
    combined_lines = []
    combined_texts = []

    for index, file in enumerate(files):
        content = await file.read()
        try:
            cv_img = _read_image_bytes(content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image file {file.filename}: {str(e)}")

        # Run OCR extraction on panel
        ocr_result = ocr_pipeline.process(cv_img)
        
        # Convert image to base64 for immediate frontend rendering
        _, buffer = cv2.imencode('.png', cv_img)
        img_b64 = base64.b64encode(buffer).decode('utf-8')

        panel_info = {
            "panel_index": index,
            "filename": file.filename,
            "image_b64": f"data:image/png;base64,{img_b64}",
            "dimensions": ocr_result["image_dimensions"],
            "token_count": ocr_result["token_count"],
            "line_count": ocr_result["line_count"],
            "raw_tokens": ocr_result["raw_tokens"]
        }
        panels_data.append(panel_info)

        # Merge tokens across panels with panel indexing
        for token in ocr_result["raw_tokens"]:
            t_copy = dict(token)
            t_copy["panel_index"] = index
            combined_tokens.append(t_copy)

        for line in ocr_result["assembled_lines"]:
            l_copy = dict(line)
            l_copy["panel_index"] = index
            combined_lines.append(l_copy)

        combined_texts.append(ocr_result["full_extracted_text"])

    # Aggregate OCR data
    aggregated_ocr = {
        "raw_tokens": combined_tokens,
        "assembled_lines": combined_lines,
        "full_extracted_text": "\n\n".join(combined_texts)
    }

    # Run deterministic statutory verification
    audit_verdict = rule_evaluator.evaluate(aggregated_ocr)
    audit_verdict["inspection_id"] = f"LM-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    audit_verdict["timestamp"] = datetime.now().isoformat()
    audit_verdict["panels"] = panels_data

    return JSONResponse(content=audit_verdict)


@app.get("/api/sample/{sample_name}")
async def audit_sample(sample_name: str):
    """
    1-Click test runner for pre-loaded benchmark samples.
    """
    valid_samples = {
        "compliant": "sample_compliant.png",
        "illegal_units": "sample_illegal_units.png",
        "mismatched_usp": "sample_mismatched_usp.png",
        "missing_grievance": "sample_missing_grievance.png"
    }

    if sample_name not in valid_samples:
        raise HTTPException(
            status_code=404,
            detail=f"Sample '{sample_name}' not found. Available: {list(valid_samples.keys())}"
        )

    file_path = os.path.join(SAMPLES_DIR, valid_samples[sample_name])
    if not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="Sample image missing on disk.")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    cv_img = _read_image_bytes(file_bytes)
    ocr_result = ocr_pipeline.process(cv_img)
    
    _, buffer = cv2.imencode('.png', cv_img)
    img_b64 = base64.b64encode(buffer).decode('utf-8')

    audit_verdict = rule_evaluator.evaluate(ocr_result)
    audit_verdict["inspection_id"] = f"LM-SMPL-{uuid.uuid4().hex[:6].upper()}"
    audit_verdict["timestamp"] = datetime.now().isoformat()
    audit_verdict["panels"] = [{
        "panel_index": 0,
        "filename": valid_samples[sample_name],
        "image_b64": f"data:image/png;base64,{img_b64}",
        "dimensions": ocr_result["image_dimensions"],
        "token_count": ocr_result["token_count"],
        "line_count": ocr_result["line_count"],
        "raw_tokens": ocr_result["raw_tokens"]
    }]

    return JSONResponse(content=audit_verdict)


class PDFExportRequest(BaseModel):
    inspection_id: str
    commodity_name: Optional[str] = "Packaged Commodity"
    overall_status: str
    compliance_score: float
    grade: str
    report: dict


@app.post("/api/export-pdf")
async def export_inspection_certificate(payload: PDFExportRequest):
    """
    Generates an official Government of India Legal Metrology Compliance Inspection Certificate.
    """
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

    # Ministry Header
    elements.append(Paragraph("<b>MINISTRY OF CONSUMER AFFAIRS, FOOD & PUBLIC DISTRIBUTION</b>", title_style))
    elements.append(Paragraph("Department of Consumer Affairs • Legal Metrology Division • Government of India", sub_title))
    elements.append(Paragraph("<b>STATUTORY COMPLIANCE INSPECTION REPORT (RULE 6 & RULE 12 AUDIT)</b>", title_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#F47C20'), spaceBefore=4, spaceAfter=8))

    # Meta Table
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
            Paragraph(f"<b>Evaluator:</b> SIH26034 Automated Inspector", body_style)
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

    # Detailed Statutory Rules Table
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

    # Statutory Enforcement Notice
    elements.append(Paragraph("<b>Statutory Enforcement Advisory:</b>", section_head))
    notice_text = (
        "This automated inspection certificate is issued pursuant to the provisions of the Legal Metrology "
        "Act, 2009 and the Legal Metrology (Packaged Commodities) Rules, 2011. Any non-compliance (such as missing "
        "tax declarations, prohibited metric abbreviations under Rule 12, or mismatched Unit Sale Price under Rule 6) "
        "constitutes an offence punishable under Section 36 of the Legal Metrology Act, 2009 with fines up to "
        "₹25,000 for the first offence and imprisonment for subsequent offences."
    )
    elements.append(Paragraph(notice_text, body_style))
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("<i>Digitally signed by Legal Metrology Inspection Portal (SIH26034 Engine)</i>", sub_title))

    doc.build(elements)
    pdf_buffer.seek(0)

    headers = {
        'Content-Disposition': f'attachment; filename="Legal_Metrology_Inspection_{payload.inspection_id}.pdf"'
    }
    return Response(content=pdf_buffer.getvalue(), media_type="application/pdf", headers=headers)


# Mount static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Legal Metrology Inspection Dashboard Initializing...</h1>")
