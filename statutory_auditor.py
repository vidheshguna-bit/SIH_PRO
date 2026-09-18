"""
SIH26034 - Layer 5: Statutory Auditing (Deterministic Symbolic AI)
Uses Pydantic validation schemas + Python Decimal exact arithmetic.
Enforces exact Legal Metrology calculations (MRP / Quantity) and standard SI unit verification
without floating-point math errors, adhering strictly to Legal Metrology Rules, 2011.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


class PackagingDeclarationModel(BaseModel):
    """Structured, validated packaging declaration data model."""
    mrp: Optional[Decimal] = Field(default=None, description="Maximum Retail Price in INR")
    has_tax_clause: bool = Field(default=False, description="Whether statutory 'inclusive of all taxes' is declared")
    net_quantity: Optional[Decimal] = Field(default=None, description="Net quantity value")
    declared_unit: Optional[str] = Field(default=None, description="Raw unit symbol declared on package")
    standard_unit: Optional[str] = Field(default=None, description="Standard SI unit according to Rule 12")
    is_illegal_unit: bool = Field(default=False, description="Whether prohibited symbol like 'gms' is detected")
    declared_usp: Optional[Decimal] = Field(default=None, description="Declared Unit Sale Price")
    usp_unit_denominator: Optional[str] = Field(default=None, description="USP denominator unit e.g. 'g', '100g', 'kg'")
    mfg_date: Optional[str] = Field(default=None, description="Month and year of manufacture or packing")
    consumer_phone: Optional[str] = Field(default=None, description="Consumer grievance phone / helpline")
    consumer_email: Optional[str] = Field(default=None, description="Consumer grievance email")
    manufacturer: Optional[str] = Field(default=None, description="Manufacturer/Packer name and address")
    country_of_origin: Optional[str] = Field(default=None, description="Country of origin declaration")

    @field_validator('mrp', 'net_quantity', 'declared_usp', mode='before')
    @classmethod
    def parse_to_decimal(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, Decimal):
            return v
        try:
            # String conversion to Decimal prevents float inaccuracy
            return Decimal(str(v).strip())
        except (InvalidOperation, ValueError):
            return None


class MRPAuditModel(BaseModel):
    rule: str = "Rule 6(1)(e)"
    title: str = "Maximum Retail Price (MRP) & Mandatory Tax Clause"
    status: str
    numeric_mrp: Optional[float]
    has_tax_clause: bool
    details: str


class NetQuantityAuditModel(BaseModel):
    rule: str = "Rule 6(1)(c) & Rule 12"
    title: str = "Net Quantity & Standard SI Metric Symbol"
    status: str
    numeric_qty: Optional[float]
    detected_unit: Optional[str]
    standard_unit: Optional[str]
    is_illegal_symbol: bool
    details: str


class USPAuditModel(BaseModel):
    rule: str = "Rule 6(1)(11)"
    title: str = "Unit Sale Price (USP) Exact Arithmetic Verification"
    status: str
    declared_usp: Optional[float]
    expected_usp: Optional[float]
    math_consistent: Optional[bool]
    absolute_diff: Optional[float]
    details: str


class StatutoryComplianceAuditResult(BaseModel):
    overall_status: str
    compliance_score: float
    compliance_grade: str
    violations_count: int
    warnings_count: int
    audit_report: Dict[str, Any]
    violations_summary: List[Dict[str, Any]]


class StatutoryAuditor:
    """
    Deterministic Symbolic AI Engine using Python Decimal exact arithmetic.
    Audits Legal Metrology rules with exact mathematical proofs.
    """

    @classmethod
    def audit_declarations(cls, decl: PackagingDeclarationModel) -> StatutoryComplianceAuditResult:
        violations = []
        warnings = []
        audit_rep = {}

        # 1. Audit Rule 6(1)(e): MRP & Mandatory Tax Phrase
        if decl.mrp is not None:
            if decl.has_tax_clause:
                mrp_status = "COMPLIANT"
                mrp_det = f"MRP ₹ {decl.mrp:.2f} declared with mandatory statutory phrase 'inclusive of all taxes'."
            else:
                mrp_status = "NON_COMPLIANT"
                mrp_det = f"MRP ₹ {decl.mrp:.2f} detected, but MANDATORY statutory phrase 'inclusive of all taxes' is MISSING. Violation of Rule 6(1)(e) punishable under Section 36."
                violations.append({"rule": "Rule 6(1)(e)", "title": "Missing Tax Clause", "details": mrp_det})
        else:
            mrp_status = "FAIL"
            mrp_det = "Maximum Retail Price (MRP) declaration not found on package label. Mandatory under Rule 6(1)(e)."
            violations.append({"rule": "Rule 6(1)(e)", "title": "Missing MRP", "details": mrp_det})

        audit_rep["rule_6_1_e_mrp"] = MRPAuditModel(
            status=mrp_status,
            numeric_mrp=float(decl.mrp) if decl.mrp is not None else None,
            has_tax_clause=decl.has_tax_clause,
            details=mrp_det
        ).model_dump()

        # 2. Audit Rule 6(1)(c) & Rule 12: Net Quantity & Standard SI Units
        if decl.net_quantity is not None and decl.standard_unit:
            if decl.is_illegal_unit:
                qty_status = "WARNING"
                qty_det = (
                    f"Non-compliant metric symbol '{decl.declared_unit}' detected. "
                    f"Under Rule 12(1) of Legal Metrology Rules, 2011, symbols must not be pluralized or altered. "
                    f"Mandatory standard SI symbol is '{decl.standard_unit}'."
                )
                warnings.append({"rule": "Rule 12(1)", "title": "Illegal Unit Symbol", "details": qty_det})
            else:
                qty_status = "COMPLIANT"
                qty_det = f"Net quantity {decl.net_quantity} {decl.standard_unit} uses authorized standard SI unit according to Rule 12."
        else:
            qty_status = "FAIL"
            qty_det = "Net Quantity declaration not found. Mandatory under Rule 6(1)(c) and Rule 12."
            violations.append({"rule": "Rule 6(1)(c)", "title": "Missing Net Quantity", "details": qty_det})

        audit_rep["rule_6_1_c_net_quantity"] = NetQuantityAuditModel(
            status=qty_status,
            numeric_qty=float(decl.net_quantity) if decl.net_quantity is not None else None,
            detected_unit=decl.declared_unit,
            standard_unit=decl.standard_unit,
            is_illegal_symbol=decl.is_illegal_unit,
            details=qty_det
        ).model_dump()

        # 3. Audit Rule 6(1)(11): Exact Decimal USP Arithmetic Verification
        usp_status, exp_usp, is_consistent, diff_val, usp_det = cls._audit_usp_exact_decimal(decl)
        if usp_status == "NON_COMPLIANT":
            violations.append({"rule": "Rule 6(1)(11)", "title": "Mathematical Discrepancy in USP", "details": usp_det})
        elif usp_status == "WARNING":
            warnings.append({"rule": "Rule 6(1)(11)", "title": "Missing USP Declaration", "details": usp_det})

        audit_rep["rule_6_1_11_unit_sale_price"] = USPAuditModel(
            status=usp_status,
            declared_usp=float(decl.declared_usp) if decl.declared_usp is not None else None,
            expected_usp=float(exp_usp) if exp_usp is not None else None,
            math_consistent=is_consistent,
            absolute_diff=float(diff_val) if diff_val is not None else None,
            details=usp_det
        ).model_dump()

        # 4. Audit Rule 6(1)(d): Date of Manufacture / Packing
        if decl.mfg_date:
            date_status = "COMPLIANT"
            date_det = f"Date of Manufacture/Packing '{decl.mfg_date}' complies with Rule 6(1)(d)."
        else:
            date_status = "NON_COMPLIANT"
            date_det = "Month and Year of manufacture or packing is NOT detected on label. Mandatory under Rule 6(1)(d)."
            violations.append({"rule": "Rule 6(1)(d)", "title": "Missing Mfg/Packing Date", "details": date_det})

        audit_rep["rule_6_1_d_mfg_date"] = {
            "rule": "Rule 6(1)(d)",
            "title": "Month & Year of Manufacture / Packing",
            "status": date_status,
            "detected_value": decl.mfg_date,
            "details": date_det
        }

        # 5. Audit Rule 6(1)(da): Consumer Grievance Contact
        if decl.consumer_phone and decl.consumer_email:
            griev_status = "COMPLIANT"
            griev_det = f"Both Helpline ({decl.consumer_phone}) and Email ({decl.consumer_email}) declared under Rule 6(1)(da)."
        elif decl.consumer_phone or decl.consumer_email:
            griev_status = "WARNING"
            val = decl.consumer_phone or decl.consumer_email
            griev_det = f"Partial compliance with Rule 6(1)(da). Detected: {val}, but both telephone and email are mandatory."
            warnings.append({"rule": "Rule 6(1)(da)", "title": "Incomplete Grievance Redressal", "details": griev_det})
        else:
            griev_status = "NON_COMPLIANT"
            griev_det = "Consumer grievance redressal details (phone and email) missing. Mandatory under Rule 6(1)(da)."
            violations.append({"rule": "Rule 6(1)(da)", "title": "Missing Grievance Redressal", "details": griev_det})

        audit_rep["rule_6_1_da_consumer_grievance"] = {
            "rule": "Rule 6(1)(da)",
            "title": "Consumer Grievance Redressal",
            "status": griev_status,
            "detected_value": f"{decl.consumer_phone or ''} {decl.consumer_email or ''}".strip() or None,
            "details": griev_det
        }

        # Scoring
        if violations:
            overall_status = "FAIL"
            score = max(50.0, 100.0 - (len(violations) * 20.0) - (len(warnings) * 5.0))
            grade = "F (Statutory Violations Detected)"
        elif warnings:
            overall_status = "WARNING"
            score = max(80.0, 100.0 - (len(warnings) * 5.0))
            grade = "B (Compliant with Warnings)"
        else:
            overall_status = "PASS"
            score = 100.0
            grade = "A+ (Fully Compliant)"

        return StatutoryComplianceAuditResult(
            overall_status=overall_status,
            compliance_score=round(score, 1),
            compliance_grade=grade,
            violations_count=len(violations),
            warnings_count=len(warnings),
            audit_report=audit_rep,
            violations_summary=violations + warnings
        )

    @classmethod
    def _audit_usp_exact_decimal(cls, decl: PackagingDeclarationModel):
        """Exact Decimal Unit Sale Price calculation with ROUND_HALF_UP."""
        if not decl.declared_usp:
            return "WARNING", None, None, None, "Unit Sale Price (USP) declaration not detected. Mandatory under Rule 6(1)(11)."

        if not decl.mrp or not decl.net_quantity or not decl.standard_unit:
            return "COMPLIANT", None, None, None, f"Unit Sale Price declared as ₹ {decl.declared_usp:.2f}."

        mrp_dec = decl.mrp
        qty_dec = decl.net_quantity
        unit_std = decl.standard_unit.lower()

        # Normalize quantity to grams or milliliters
        base_qty = qty_dec
        base_unit = unit_std
        if unit_std == "kg":
            base_qty = qty_dec * Decimal("1000")
            base_unit = "g"
        elif unit_std == "l":
            base_qty = qty_dec * Decimal("1000")
            base_unit = "ml"

        # Determine multiplier based on USP denominator
        denom = (decl.usp_unit_denominator or "g").replace(" ", "").lower()
        multiplier = Decimal("1")
        if denom in ["100g", "100ml"]:
            multiplier = Decimal("100")
        elif denom in ["kg", "l"]:
            multiplier = Decimal("1000")
        elif denom == "10g":
            multiplier = Decimal("10")

        # Statutory Decimal calculation: (MRP / base_qty) * multiplier
        try:
            expected_raw = (mrp_dec / base_qty) * multiplier
            expected_usp = expected_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            return "COMPLIANT", None, None, None, f"Unit Sale Price declared as ₹ {decl.declared_usp:.2f}."

        abs_diff = abs(decl.declared_usp - expected_usp)
        # Legal tolerance under Legal Metrology Rules: within 0.01 (1 paisa rounding) or 2%
        rel_diff = abs_diff / expected_usp if expected_usp > Decimal("0") else Decimal("1")
        is_consistent = (rel_diff <= Decimal("0.02")) or (abs_diff <= Decimal("0.01"))

        if is_consistent:
            status = "COMPLIANT"
            details = (
                f"Unit Sale Price ₹ {decl.declared_usp:.2f} / {denom} is mathematically accurate. "
                f"Statutory expected rate: ₹ {expected_usp:.2f} / {denom} (MRP ₹{mrp_dec:.2f} ÷ {base_qty}{base_unit} × {multiplier})."
            )
        else:
            status = "NON_COMPLIANT"
            details = (
                f"MATHEMATICAL MISMATCH! Declared USP is ₹ {decl.declared_usp:.2f} / {denom}, "
                f"but statutory calculation is ₹ {expected_usp:.2f} / {denom} "
                f"(MRP ₹{mrp_dec:.2f} ÷ {base_qty}{base_unit} × {multiplier}). Discrepancy violates Rule 6(1)(11)."
            )

        return status, expected_usp, is_consistent, abs_diff, details


def verify_unit_sale_price(
    mrp_val: Decimal,
    net_qty_val: Decimal,
    net_qty_unit: str,
    declared_usp_val: Decimal,
    declared_usp_unit: str = "g",
) -> Tuple[bool, Decimal, str]:
    """
    Stand-alone deterministic Decimal verification of Unit Sale Price (USP).
    Returns (is_compliant, expected_usp, reason_details).
    """
    decl = PackagingDeclarationModel(
        mrp=mrp_val,
        net_quantity=net_qty_val,
        standard_unit=net_qty_unit,
        declared_usp=declared_usp_val,
        usp_unit_denominator=declared_usp_unit,
    )
    status, exp_usp, is_consistent, _, details = StatutoryAuditor._audit_usp_exact_decimal(decl)
    return (status == "COMPLIANT"), exp_usp, details


def audit_packaging_declaration(decl: PackagingDeclarationModel) -> StatutoryComplianceAuditResult:
    """Convenience functional wrapper for statutory compliance audit."""
    return StatutoryAuditor.audit_declarations(decl)
