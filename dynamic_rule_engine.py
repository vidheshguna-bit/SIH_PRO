from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
import re


@dataclass
class RuleDefinition:
    id: str
    category: str
    field: str
    title: str
    severity: str = "major"
    required: bool = True
    pattern: Optional[str] = None
    explanation: str = ""
    source_note: str = "Prototype rule profile. Verify against the currently applicable statutory text before enforcement use."
    version: int = 1
    active: bool = True


DEFAULT_RULES: List[RuleDefinition] = [
    RuleDefinition("GEN-MRP-001", "general", "mrp", "MRP declaration", pattern=r"(?:₹|rs\.?|inr)?\s*\d+(?:\.\d{1,2})?", explanation="Maximum retail price should be present and machine-readable."),
    RuleDefinition("GEN-NET-002", "general", "net_quantity", "Net quantity declaration", pattern=r"\d+(?:\.\d+)?\s*(?:kg|g|gm|ml|l|litre|liter|pcs?|pieces?)\b", explanation="Net quantity should include a numeric value and recognized unit."),
    RuleDefinition("GEN-MFG-003", "general", "manufacturer", "Manufacturer / packer identity", explanation="Manufacturer or packer identity should be declared."),
    RuleDefinition("GEN-ADDR-004", "general", "manufacturer_address", "Manufacturer / packer address", explanation="A usable manufacturer or packer address should be visible."),
    RuleDefinition("GEN-CONS-005", "general", "consumer_care", "Consumer grievance contact", explanation="Consumer care contact details should be visible where applicable."),
    RuleDefinition("GEN-DATE-006", "general", "manufactured_date", "Manufacture / packing date", explanation="Manufacture or packing date should be present where applicable."),
    RuleDefinition("FOOD-BATCH-101", "food", "batch_number", "Batch / lot identification", explanation="Food-package profile expects a batch or lot identifier."),
    RuleDefinition("FOOD-EXP-102", "food", "expiry_date", "Best-before / expiry information", explanation="Food-package profile expects shelf-life or expiry information where applicable."),
    RuleDefinition("COS-BATCH-201", "cosmetic", "batch_number", "Cosmetic batch identification", explanation="Cosmetic profile expects traceable batch identification."),
    RuleDefinition("COS-MFG-202", "cosmetic", "manufacturer", "Cosmetic manufacturer identity", explanation="Cosmetic profile expects manufacturer identity."),
    RuleDefinition("ELEC-MODEL-301", "electronics", "model_number", "Model identification", explanation="Electronics profile expects a model or product identifier."),
    RuleDefinition("ELEC-MFG-302", "electronics", "manufacturer", "Manufacturer identity", explanation="Electronics profile expects manufacturer identity."),
]


class DynamicRuleEngine:
    def __init__(self, rules: Optional[List[RuleDefinition]] = None):
        self._rules: Dict[str, RuleDefinition] = {r.id: r for r in (rules or DEFAULT_RULES)}

    def list_rules(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        values = [r for r in self._rules.values() if r.active]
        if category:
            values = [r for r in values if r.category in {"general", category}]
        return [asdict(r) for r in values]

    def upsert(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        rule = RuleDefinition(**payload)
        self._rules[rule.id] = rule
        return asdict(rule)

    def evaluate(self, fields: Dict[str, Any], category: str = "general") -> Dict[str, Any]:
        applicable = [r for r in self._rules.values() if r.active and r.category in {"general", category}]
        results = []
        weighted_total = 0.0
        weighted_pass = 0.0
        severity_weight = {"critical": 3.0, "major": 2.0, "minor": 1.0}

        for rule in applicable:
            value = fields.get(rule.field)
            if isinstance(value, dict):
                value = value.get("value") or value.get("detected_value") or value.get("text")
            value_text = str(value).strip() if value is not None else ""
            present = bool(value_text)
            format_ok = True
            if present and rule.pattern:
                format_ok = bool(re.search(rule.pattern, value_text, re.IGNORECASE))
            passed = (present and format_ok) if rule.required else (not present or format_ok)
            weight = severity_weight.get(rule.severity, 1.0)
            weighted_total += weight
            if passed:
                weighted_pass += weight
            status = "PASS" if passed else "FAIL"
            reason = "Requirement satisfied." if passed else ("Declaration missing." if not present else "Declaration detected but format requires review.")
            results.append({
                "rule_id": rule.id,
                "title": rule.title,
                "field": rule.field,
                "category": rule.category,
                "status": status,
                "severity": rule.severity,
                "detected_value": value_text or None,
                "reason": reason,
                "explanation": rule.explanation,
                "source_note": rule.source_note,
                "version": rule.version,
            })

        score = round((weighted_pass / weighted_total * 100.0), 1) if weighted_total else 100.0
        failures = [r for r in results if r["status"] == "FAIL"]
        verdict = "COMPLIANT" if not failures else ("REVIEW" if score >= 80 else "NON_COMPLIANT")
        return {
            "category": category,
            "score": score,
            "verdict": verdict,
            "passed": len(results) - len(failures),
            "failed": len(failures),
            "results": results,
            "failed_reasons": [f"{r['title']}: {r['reason']}" for r in failures],
            "decision_source": "dynamic deterministic rule engine",
        }
