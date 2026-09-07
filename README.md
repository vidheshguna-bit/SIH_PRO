# Legal Metrology Compliance Auditor (SIH26034)
**Software System to check compliance of Packaged Commodities under Legal Metrology (Packaged Commodities) Rules, 2011 by scanning products, images and labels.**

*Ministry of Consumer Affairs, Food & Public Distribution • Smart India Hackathon 2026*

---

## 📌 Executive Summary
Under the **Legal Metrology (Packaged Commodities) Rules, 2011** (and subsequent 2021/2022 amendments), every pre-packaged commodity manufactured, packed, or imported in India must strictly bear specific mandatory declarations. Retail violations—such as omitted tax statements, non-standard metric symbols (e.g. `gms` instead of `g`), or misleading Unit Sale Prices (USP)—harm consumer rights and farmers' market transparency.

This project delivers a **production-ready, zero-hallucination compliance audit system** featuring:
1. **Computer Vision & Preprocessing Pipeline**: High-contrast CLAHE enhancement, bilateral edge filtering, and skew correction.
2. **High-Speed OCR Engine**: RapidOCR (PaddleOCR models powered by ONNX Runtime) with spatial coordinate mapping `[x, y, w, h]` and horizontal line assembly.
3. **Deterministic Statutory Rule Engine**: Zero-LLM, legally sound regex patterns and arithmetic verification ensuring 100% explainability and auditability.
4. **FastAPI Backend**: Endpoints for single/multi-panel scans, sample benchmarks, and downloadable official PDF Inspection Certificates.
5. **Government-Grade Frontend Dashboard**: Split-screen canvas overlay with bounding boxes, violation cards, and 1-click sample benchmarks.

---

## ⚖️ Statutory Clauses Enforced

| Statutory Clause | Mandatory Declaration | Verification Mechanism | Penalty / Impact |
| :--- | :--- | :--- | :--- |
| **Rule 6(1)(e)** | Maximum Retail Price (MRP) & Tax Declaration | Regex extracts MRP and strictly checks for mandatory phrase `'inclusive of all taxes'` or `'incl. of all taxes'`. | **Non-compliant** if tax phrase missing. Punishable under Sec. 36 of LM Act. |
| **Rule 6(1)(c) & Rule 12(1)** | Net Quantity & Standard SI Metric Symbol | Enforces SI symbols (`g`, `kg`, `ml`, `l`, `m`, `cm`, `N`). Strictly flags illegal symbols (`gm`, `gms`, `grms`, `ltr`, `ltrs`, `kilo`). | **Warning/Defect** under Rule 12(1) prohibition of pluralized/non-standard metric units. |
| **Rule 6(1)(11)** | Unit Sale Price (USP) & Mathematical Consistency | Extracts declared USP and verifies with computed value: $\text{USP} = \frac{\text{MRP}}{\text{Net Qty in Base Units}}$. | **Statutory Violation** if math mismatch exceeds tolerance or if USP omitted. |
| **Rule 6(1)(d)** | Month & Year of Manufacture / Packing | Detects `MM/YYYY`, `MM-YYYY`, `MMM YYYY` (e.g. `08/2026`, `AUG 2026`). | **Defect** if manufacturing timeline is missing. |
| **Rule 6(1)(da)** | Consumer Grievance Contact Details | Checks for Customer Care Helpline/Phone AND Email Address. | **Violation** if contact channels are omitted; **Warning** if only one is present. |
| **Rule 6(1)(a)** | Manufacturer / Packer Identity | Extracts name, address, and Indian PIN code. | **Warning** if manufacturer identity lacks PIN or clear keyword. |
| **Rule 6(1)(b)** | Common Generic Commodity Name | Matches commodity against official gazette dictionary. | Verified front panel declaration. |

---

## 🚀 Quickstart Guide

### Prerequisites
- Python 3.10+ (Tested and verified on Python 3.14.3)
- Windows / Linux / macOS

### 1. Installation
Navigate to the project directory:
```bash
cd C:\Users\vidhe\.gemini\antigravity\scratch\legal-metrology-inspector
```

Install the dependencies:
```bash
pip install -r requirements.txt
```

### 2. Generate Benchmark Sample Datasets
Generate pre-configured compliant and non-compliant test labels:
```bash
python generate_sample_data.py
```

### 3. Run Automated Statutory Test Suite
Verify that all legal clauses pass deterministic verification:
```bash
python test_system.py
```

### 4. Launch Inspection Server
Start the FastAPI server:
```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and visit:
👉 **`http://127.0.0.1:8000`**

---

## 🎯 1-Click Judge & Evaluator Demonstration

In the web dashboard, click any of the **Benchmark Test Vectors** in the top bar:

1. **🟢 100% Compliant (Royal Delight Cookies)**:
   - Evaluates a perfectly compliant biscuit pack.
   - Result: `PASS` (100% score, Grade A+). All bounding boxes green.
2. **🔴 Illegal 'gms' Unit & No Tax (Crunchy Chips)**:
   - Uses prohibited `150 gms` instead of standard `150 g` (Rule 12).
   - MRP printed without `inclusive of all taxes` (Rule 6(1)(e)).
   - Result: `FAIL` / `WARNING` with exact statutory citations highlighted.
3. **🔴 USP Math Mismatch (Himalayan Ghee)**:
   - Net Qty = 250 g, MRP = ₹ 100.00.
   - Stated USP = `₹ 0.25 / g` (Expected: $\frac{100}{250} = \text{₹ } 0.40 \text{ / g}$).
   - Result: `FAIL` with math mismatch breakdown!
4. **🔴 Missing Grievance & Mfg Date (Fresh Farm Atta)**:
   - Missing customer care helpline and email, missing packaging date.
   - Result: `FAIL` with red warning cards.

---

## 📡 API Endpoints

- `POST /api/audit`: Multipart upload accepting 1 or more images (front, back, nutritional side panels). Returns full audit JSON with bounding boxes.
- `GET /api/sample/{sample_id}`: Benchmark runner (`compliant`, `illegal_units`, `mismatched_usp`, `missing_grievance`).
- `POST /api/export-pdf`: Generates an official, print-ready Government of India Inspection Certificate with statutory notices under Section 36 of the Legal Metrology Act, 2009.
