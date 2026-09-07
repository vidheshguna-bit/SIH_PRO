"""
SIH26034 - Sample Data Generator
Generates realistic packaged commodity test labels for Legal Metrology compliance auditing.
"""

import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "samples")
os.makedirs(SAMPLE_DIR, exist_ok=True)

def create_label(
    filename: str,
    title: str,
    commodity: str,
    net_qty_text: str,
    mrp_text: str,
    usp_text: str,
    date_text: str,
    grievance_text: str,
    mfg_text: str,
    bg_color=(248, 249, 250),
    border_color=(200, 205, 215)
):
    # Dimensions for product label
    width, height = 750, 520
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rectangle([(10, 10), (width - 10, height - 10)], outline=border_color, width=3)
    draw.rectangle([(16, 16), (width - 16, height - 16)], outline=(220, 225, 235), width=1)

    # Header banner
    draw.rectangle([(20, 20), (width - 20, 80)], fill=(26, 54, 93))
    
    # Try default font or basic PIL font
    try:
        font_large = ImageFont.truetype("arial.ttf", 26)
        font_med = ImageFont.truetype("arial.ttf", 18)
        font_bold = ImageFont.truetype("arialbd.ttf", 19)
        font_small = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font_large = ImageFont.load_default()
        font_med = font_large
        font_bold = font_large
        font_small = font_large

    # Brand Title
    draw.text((35, 32), title.upper(), fill=(255, 255, 255), font=font_large)

    # Commodity Name
    draw.text((35, 95), f"Commodity: {commodity}", fill=(30, 41, 59), font=font_bold)
    draw.line([(35, 125), (width - 35, 125)], fill=(203, 213, 225), width=1)

    # Mandatory Declarations Block
    y = 140
    line_spacing = 38

    # Net Qty
    draw.text((35, y), "Net Quantity:", fill=(71, 85, 105), font=font_med)
    draw.text((220, y), net_qty_text, fill=(15, 23, 42), font=font_bold)
    y += line_spacing

    # MRP
    draw.text((35, y), "Maximum Retail Price:", fill=(71, 85, 105), font=font_med)
    draw.text((220, y), mrp_text, fill=(15, 23, 42), font=font_bold)
    y += line_spacing

    # USP
    if usp_text:
        draw.text((35, y), "Unit Sale Price (USP):", fill=(71, 85, 105), font=font_med)
        draw.text((220, y), usp_text, fill=(15, 23, 42), font=font_bold)
        y += line_spacing

    # Mfg Date
    if date_text:
        draw.text((35, y), "Date of Packing / Mfg:", fill=(71, 85, 105), font=font_med)
        draw.text((220, y), date_text, fill=(15, 23, 42), font=font_bold)
        y += line_spacing

    # Separator
    draw.line([(35, y + 5), (width - 35, y + 5)], fill=(226, 232, 240), width=1)
    y += 18

    # Manufacturer Details
    draw.text((35, y), mfg_text, fill=(51, 65, 85), font=font_small)
    y += 40

    # Grievance / Customer Care
    if grievance_text:
        draw.text((35, y), grievance_text, fill=(30, 58, 138), font=font_small)

    out_path = os.path.join(SAMPLE_DIR, filename)
    img.save(out_path, quality=95)
    print(f"Generated sample label: {out_path}")
    return out_path

def generate_all_samples():
    # 1. 100% Compliant Sample (All rules pass)
    create_label(
        filename="sample_compliant.png",
        title="ROYAL DELIGHT COOKIES",
        commodity="Biscuits",
        net_qty_text="200 g",
        mrp_text="MRP Rs. 40.00 (incl. of all taxes)",
        usp_text="Rs. 0.20 / g",
        date_text="MFD: 08/2026",
        grievance_text="Customer Care: 1800-202-3344 | Email: support@royaldelight.in | New Delhi 110001",
        mfg_text="Mfd by: Royal Delights Confectionery Ltd, Plot 42, Industrial Area, New Delhi - 110001"
    )

    # 2. Non-Compliant Sample: Illegal Metric Unit ('gms') & Missing Tax Statement
    create_label(
        filename="sample_illegal_units.png",
        title="CRUNCHY CHIPS MASALA",
        commodity="Potato Chips",
        net_qty_text="150 gms",  # VIOLATION: Rule 12(1) prohibition of 'gms'
        mrp_text="MRP Rs. 60.00",  # VIOLATION: Rule 6(1)(e) missing 'incl. of all taxes'
        usp_text="Rs. 0.40 / g",
        date_text="PKD: 07/2026",
        grievance_text="Contact: 1800-444-5566 | Email: care@crunchychips.com",
        mfg_text="Manufactured by: Crisp Snack Foods Pvt Ltd, Pune, Maharashtra 411001"
    )

    # 3. Non-Compliant Sample: Arithmetic Mismatch in Unit Sale Price (USP)
    # Net Qty = 250 g, MRP = Rs. 100.00 => Expected USP = 100 / 250 = Rs. 0.40 / g
    # Declared USP = Rs. 0.25 / g (Mismatch!)
    create_label(
        filename="sample_mismatched_usp.png",
        title="HIMALAYAN PURE GHEE",
        commodity="Ghee",
        net_qty_text="250 g",
        mrp_text="MRP Rs. 100.00 (inclusive of all taxes)",
        usp_text="USP: Rs. 0.25 / g", # VIOLATION: Rule 6(1)(11) math mismatch
        date_text="Date of Mfg: 09/2026",
        grievance_text="Grievance Helpline: 1800-999-8877 | support@himalayanghee.org",
        mfg_text="Mfd by: Himalayan Dairy Cooperative Ltd, Shimla, Himachal Pradesh 171001"
    )

    # 4. Non-Compliant Sample: Missing Grievance Redressal Mechanism & Missing Mfg Date
    create_label(
        filename="sample_missing_grievance.png",
        title="FRESH FARM ATTA",
        commodity="Atta",
        net_qty_text="5 kg",
        mrp_text="MRP Rs. 240.00 (incl. of all taxes)",
        usp_text="Rs. 48.00 / kg",
        date_text="", # VIOLATION: Missing Mfg Date
        grievance_text="", # VIOLATION: Missing Customer Care / Email
        mfg_text="Packed by: Golden Harvest Mills, Kanpur, Uttar Pradesh 208001"
    )

if __name__ == "__main__":
    generate_all_samples()
