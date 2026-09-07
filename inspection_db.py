from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional


DB_PATH = os.getenv("SMARTMETROLOGY_DB", "smartmetrology.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS inspections (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                product_name TEXT,
                category TEXT,
                manufacturer TEXT,
                language TEXT,
                compliance_score REAL,
                verdict TEXT,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manufacturer TEXT NOT NULL,
                product_name TEXT,
                complaint_type TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS offline_sync_queue (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                synced_at TEXT
            );
            """
        )


def save_inspection(record: Dict[str, Any]):
    initialize_database()
    inspection_id = record.get("inspection_id") or record.get("id")
    if not inspection_id:
        raise ValueError("inspection_id is required")
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO inspections
            (id, created_at, product_name, category, manufacturer, language, compliance_score, verdict, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                inspection_id,
                record.get("created_at") or datetime.utcnow().isoformat(),
                record.get("product_name"),
                record.get("category"),
                record.get("manufacturer"),
                record.get("language"),
                record.get("compliance_score"),
                record.get("verdict"),
                json.dumps(record, ensure_ascii=False),
            ),
        )


def list_inspections(limit: int = 50) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM inspections ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    return [dict(row) for row in rows]


def manufacturer_risk(manufacturer: str) -> Dict[str, Any]:
    initialize_database()
    with _connect() as conn:
        inspections = conn.execute(
            "SELECT compliance_score, verdict FROM inspections WHERE lower(manufacturer)=lower(?)", (manufacturer,)
        ).fetchall()
        complaint_count = conn.execute(
            "SELECT COUNT(*) AS c FROM complaints WHERE lower(manufacturer)=lower(?)", (manufacturer,)
        ).fetchone()["c"]
    total = len(inspections)
    fail_count = sum(1 for row in inspections if str(row["verdict"]).upper() not in {"COMPLIANT", "PASS"})
    avg_score = round(sum(float(row["compliance_score"] or 0) for row in inspections) / total, 1) if total else None
    risk_points = min(100, fail_count * 18 + complaint_count * 10 + (0 if avg_score is None else max(0, 80 - avg_score)))
    level = "HIGH" if risk_points >= 60 else ("MEDIUM" if risk_points >= 30 else "LOW")
    return {
        "manufacturer": manufacturer,
        "inspection_count": total,
        "previous_violations": fail_count,
        "complaint_count": complaint_count,
        "average_compliance_score": avg_score,
        "risk_score": round(risk_points, 1),
        "risk_level": level,
        "basis": "historical inspections + complaint count; prototype risk signal, not an enforcement decision",
    }


def add_complaint(manufacturer: str, product_name: Optional[str], complaint_type: str, details: str):
    initialize_database()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO complaints (manufacturer, product_name, complaint_type, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (manufacturer, product_name, complaint_type, details, datetime.utcnow().isoformat()),
        )


def enqueue_offline(record_id: str, payload: Dict[str, Any]):
    initialize_database()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO offline_sync_queue (id, payload_json, created_at, synced_at) VALUES (?, ?, ?, NULL)",
            (record_id, json.dumps(payload, ensure_ascii=False), datetime.utcnow().isoformat()),
        )


def pending_sync() -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM offline_sync_queue WHERE synced_at IS NULL ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]
