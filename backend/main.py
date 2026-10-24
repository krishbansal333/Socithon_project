from __future__ import annotations

import base64
import io
import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "naaravali.db")))
CATEGORIES = {"recyclable", "organic", "hazardous", "residual"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

app = FastAPI(
    title="Naaravali EcoLoop AI API",
    description="Hackathon MVP for campus waste segregation, collection and recycling workflows.",
    version="1.0.0",
)
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS bins (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, location TEXT NOT NULL,
                waste_type TEXT NOT NULL, fill_level INTEGER NOT NULL,
                latitude REAL NOT NULL, longitude REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active', updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pickups (
                id TEXT PRIMARY KEY, bin_id TEXT, location TEXT NOT NULL,
                waste_type TEXT NOT NULL, priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY, category TEXT NOT NULL, confidence REAL NOT NULL,
                mode TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, detail TEXT NOT NULL,
                kind TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recycler_requests (
                id TEXT PRIMARY KEY, recycler_id TEXT NOT NULL, recycler_name TEXT NOT NULL,
                material TEXT NOT NULL, contact TEXT NOT NULL, location TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Requested', created_at TEXT NOT NULL
            );
            """
        )
        if db.execute("SELECT COUNT(*) FROM bins").fetchone()[0] == 0:
            bins = [
                ("BIN-01", "Govind Bhawan Gate", "Govind Bhawan", "Mixed recyclables", 88, 29.8669, 77.8950, "Active", now_iso()),
                ("BIN-02", "LBS Canteen", "LBS Canteen", "Organic", 72, 29.8661, 77.8943, "Active", now_iso()),
                ("BIN-03", "MAC Entry", "MAC Auditorium", "Residual", 43, 29.8682, 77.8933, "Active", now_iso()),
                ("BIN-04", "Thomso Ground", "Thomso Ground", "Mixed recyclables", 96, 29.8648, 77.8966, "Active", now_iso()),
                ("BIN-05", "Library Lawn", "Central Library", "Paper & cardboard", 28, 29.8671, 77.8918, "Active", now_iso()),
                ("BIN-06", "Hostel Cluster C", "Hostel Cluster C", "Organic", 61, 29.8658, 77.8990, "Active", now_iso()),
            ]
            db.executemany("INSERT INTO bins VALUES (?,?,?,?,?,?,?,?,?)", bins)
        if db.execute("SELECT COUNT(*) FROM pickups").fetchone()[0] == 0:
            pickups = [
                ("PU-101", "BIN-04", "Thomso Ground", "Mixed recyclables", "High", "Pending", now_iso(), None),
                ("PU-102", "BIN-01", "Govind Bhawan", "Mixed recyclables", "High", "Pending", now_iso(), None),
                ("PU-103", "BIN-02", "LBS Canteen", "Organic", "Medium", "Pending", now_iso(), None),
                ("PU-104", "BIN-06", "Hostel Cluster C", "Organic", "Low", "Scheduled", now_iso(), None),
            ]
            db.executemany("INSERT INTO pickups VALUES (?,?,?,?,?,?,?,?)", pickups)
        if db.execute("SELECT COUNT(*) FROM activity").fetchone()[0] == 0:
            activities = [
                (str(uuid.uuid4()), "Overflow risk detected", "Thomso Ground bin is at 96% capacity", "alert", now_iso()),
                (str(uuid.uuid4()), "Collection scheduled", "Organic waste pickup at LBS Canteen", "truck", now_iso()),
                (str(uuid.uuid4()), "Recycling goal updated", "Weekly target: divert more materials from landfill", "leaf", now_iso()),
            ]
            db.executemany("INSERT INTO activity VALUES (?,?,?,?,?)", activities)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


class ReportRequest(BaseModel):
    note: str = Field(default="Overflow reported by user", max_length=300)


class RecyclerRequest(BaseModel):
    material: str = Field(min_length=2, max_length=80)
    contact: str = Field(min_length=2, max_length=120)
    location: str = Field(min_length=2, max_length=180)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "Naaravali EcoLoop AI", "time": now_iso()}


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    with connect() as db:
        bin_rows = db.execute("SELECT * FROM bins ORDER BY fill_level DESC").fetchall()
        pending = db.execute("SELECT COUNT(*) FROM pickups WHERE status != 'Completed'").fetchone()[0]
        completed = db.execute("SELECT COUNT(*) FROM pickups WHERE status = 'Completed'").fetchone()[0]
        scan_count = db.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        reports = db.execute("SELECT COUNT(*) FROM activity WHERE kind='alert'").fetchone()[0]
        recent = db.execute("SELECT * FROM activity ORDER BY created_at DESC LIMIT 5").fetchall()
    avg_fill = round(sum(b["fill_level"] for b in bin_rows) / max(len(bin_rows), 1))
    at_risk = sum(1 for b in bin_rows if b["fill_level"] >= 80)
    # Clearly illustrative until real campus weights and collection records are connected.
    return {
        "stats": [
            {"label": "Waste sorted this week", "value": "128 kg", "change": "Illustrative demo data", "icon": "scale"},
            {"label": "Recycling rate", "value": "68%", "change": "Illustrative demo data", "icon": "recycle"},
            {"label": "Collections pending", "value": str(pending), "change": f"{completed} completed in this demo", "icon": "truck"},
            {"label": "Bins needing attention", "value": str(at_risk), "change": f"Average fill: {avg_fill}%", "icon": "alert"},
        ],
        "bins": [dict(x) for x in bin_rows],
        "recent_activity": [dict(x) for x in recent],
        "scan_count": scan_count,
        "report_count": reports,
        "notice": "Dashboard totals are seeded demonstration values, not measured IIT Roorkee data.",
    }


@app.get("/api/bins")
def get_bins() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("SELECT * FROM bins ORDER BY fill_level DESC").fetchall()
    return [dict(x) for x in rows]


@app.post("/api/bins/{bin_id}/report")
def report_bin(bin_id: str, payload: ReportRequest) -> dict[str, Any]:
    with connect() as db:
        bin_row = db.execute("SELECT * FROM bins WHERE id = ?", (bin_id,)).fetchone()
        if not bin_row:
            raise HTTPException(status_code=404, detail="Bin not found")
        pickup_id = "PU-" + uuid.uuid4().hex[:6].upper()
        db.execute(
            "INSERT INTO pickups (id, bin_id, location, waste_type, priority, status, created_at) VALUES (?,?,?,?,?,?,?)",
            (pickup_id, bin_id, bin_row["location"], bin_row["waste_type"], "High", "Pending", now_iso()),
        )
        db.execute("UPDATE bins SET fill_level = MAX(fill_level, 90), updated_at=? WHERE id=?", (now_iso(), bin_id))
        db.execute(
            "INSERT INTO activity VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), "Overflow reported", f"{bin_row['name']}: {payload.note}", "alert", now_iso()),
        )
    return {"ok": True, "pickup_id": pickup_id, "message": f"Collection request created for {bin_row['name']}"}


@app.get("/api/pickups")
def get_pickups() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("SELECT * FROM pickups ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, created_at DESC").fetchall()
    return [dict(x) for x in rows]


@app.post("/api/pickups/{pickup_id}/complete")
def complete_pickup(pickup_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute("SELECT * FROM pickups WHERE id=?", (pickup_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pickup not found")
        db.execute("UPDATE pickups SET status='Completed', completed_at=? WHERE id=?", (now_iso(), pickup_id))
        if row["bin_id"]:
            db.execute("UPDATE bins SET fill_level=15, updated_at=? WHERE id=?", (now_iso(), row["bin_id"]))
        db.execute("INSERT INTO activity VALUES (?,?,?,?,?)", (str(uuid.uuid4()), "Pickup completed", f"Collected {row['waste_type']} from {row['location']}", "truck", now_iso()))
    return {"ok": True, "message": f"Pickup {pickup_id} marked complete"}


def distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    # Euclidean distance on latitude/longitude degrees. Not road distance.
    return math.sqrt((a["latitude"] - b["latitude"]) ** 2 + (a["longitude"] - b["longitude"]) ** 2)


@app.post("/api/collection/optimize")
def optimize_collection() -> dict[str, Any]:
    with connect() as db:
        rows = db.execute("SELECT * FROM bins WHERE fill_level >= 70 ORDER BY fill_level DESC").fetchall()
    pending = [dict(x) for x in rows]
    if not pending:
        return {"route": [], "total_distance_km_approx": 0, "note": "No bins currently meet the 70% threshold."}
    route = [pending.pop(0)]
    total = 0.0
    while pending:
        current = route[-1]
        nxt = min(pending, key=lambda x: distance(current, x))
        total += distance(current, nxt) * 111  # approximate conversion, demo only
        route.append(nxt)
        pending.remove(nxt)
    return {
        "route": [{"order": i + 1, "id": b["id"], "name": b["name"], "location": b["location"], "fill_level": b["fill_level"], "waste_type": b["waste_type"]} for i, b in enumerate(route)],
        "total_distance_km_approx": round(total, 2),
        "note": "Demo route uses straight-line coordinate distances, not road-network routing or live traffic.",
    }


WASTE_OPTIONS = [
    {"label": "plastic bottle", "category": "recyclable"},
    {"label": "paper and cardboard", "category": "recyclable"},
    {"label": "glass bottle", "category": "recyclable"},
    {"label": "metal can", "category": "recyclable"},
    {"label": "food scraps", "category": "organic"},
    {"label": "fruit peel", "category": "organic"},
    {"label": "leaves", "category": "organic"},
    {"label": "battery", "category": "hazardous"},
    {"label": "e-waste", "category": "hazardous"},
    {"label": "light bulb", "category": "hazardous"},
    {"label": "used tissue", "category": "residual"},
    {"label": "sanitary waste", "category": "residual"},
]
DISPOSAL = {
    "recyclable": {"bin": "Blue / dry recyclable bin", "tip": "Keep the item dry, empty, and as clean as practical. Follow your campus recycler's accepted-material list."},
    "organic": {"bin": "Green / wet organic bin", "tip": "Keep food and garden waste separate from plastic and other dry recyclables. Compost where a supported facility exists."},
    "hazardous": {"bin": "Dedicated e-waste / hazardous collection point", "tip": "Do not place batteries, bulbs, or electronics in ordinary bins. Ask campus facilities for the approved take-back point."},
    "residual": {"bin": "Grey / residual waste bin", "tip": "Use this for items that are not accepted in local recycling or composting streams. Check local campus rules."},
}


def categorize_text(text: str) -> str:
    s = text.lower()
    if any(k in s for k in ("battery", "cell", "electronic", "e-waste", "bulb", "charger", "circuit", "chemical", "medicine")):
        return "hazardous"
    if any(k in s for k in ("food", "peel", "banana", "apple", "vegetable", "leaves", "leaf", "compost", "organic")):
        return "organic"
    if any(k in s for k in ("plastic", "bottle", "paper", "cardboard", "can", "metal", "glass", "carton", "newspaper")):
        return "recyclable"
    return "residual"


def classify_with_provider(image_bytes: bytes) -> dict[str, Any] | None:
    endpoint = os.getenv("HF_INFERENCE_URL", "").strip()
    token = os.getenv("HF_TOKEN", "").strip()
    if not endpoint or not token:
        return None
    payload = {
        "inputs": base64.b64encode(image_bytes).decode("ascii"),
        "parameters": {"candidate_labels": [x["label"] for x in WASTE_OPTIONS]},
    }
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=18,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data and isinstance(data[0], dict) and "label" in data[0]:
            best = max(data, key=lambda x: float(x.get("score", 0)))
            category = categorize_text(str(best["label"]))
            return {"category": category, "confidence": round(float(best.get("score", 0.0)), 3), "mode": "provider"}
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return None
    return None


def demo_classify(image: Image.Image, filename: str) -> tuple[str, float, str]:
    """Clearly labelled fallback heuristic; not an ML classifier."""
    from_name = categorize_text(filename)
    if from_name != "residual":
        return from_name, 0.58, "demo"
    rgb = image.convert("RGB").resize((32, 32))
    pixels = list(rgb.getdata())
    r = sum(p[0] for p in pixels) / len(pixels)
    g = sum(p[1] for p in pixels) / len(pixels)
    b = sum(p[2] for p in pixels) / len(pixels)
    # Only a visual heuristic to keep the demo interactive. It cannot reliably recognise objects.
    if g > r * 1.12 and g > b * 1.08:
        return "organic", 0.42, "demo"
    if b > r * 1.08 and b > g * 1.04:
        return "recyclable", 0.40, "demo"
    if r > 145 and g < 115 and b < 115:
        return "hazardous", 0.35, "demo"
    return "residual", 0.34, "demo"


@app.post("/api/scan")
async def scan_waste(file: UploadFile = File(...)) -> dict[str, Any]:
    if file.content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise HTTPException(status_code=400, detail="Upload a JPG, PNG, WEBP, or GIF image.")
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 8 MB or smaller.")
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.verify()
        image = Image.open(io.BytesIO(image_bytes))
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="This file could not be read as an image.")
    result = classify_with_provider(image_bytes)
    if result is None:
        category, confidence, mode = demo_classify(image, file.filename or "upload")
        result = {"category": category, "confidence": confidence, "mode": mode}
    category = result["category"] if result["category"] in CATEGORIES else "residual"
    scan_id = str(uuid.uuid4())
    with connect() as db:
        db.execute("INSERT INTO scans VALUES (?,?,?,?,?)", (scan_id, category, result["confidence"], result["mode"], now_iso()))
        db.execute("INSERT INTO activity VALUES (?,?,?,?,?)", (str(uuid.uuid4()), "Waste image scanned", f"Classified as {category} ({result['mode']} mode)", "scan", now_iso()))
    return {
        "id": scan_id,
        "category": category,
        "confidence": result["confidence"],
        "mode": result["mode"],
        "label": "Demo prediction" if result["mode"] == "demo" else "Model prediction",
        "filename": file.filename or "uploaded-image",
        "disposal": DISPOSAL[category],
        "disclaimer": "Demo mode is a filename/color heuristic, not validated AI. Verify before disposal." if result["mode"] == "demo" else "Model confidence is not a guarantee. Verify local disposal rules.",
    }


RECYCLERS = [
    {"id": "REC-01", "name": "Campus Dry-Waste Partner", "materials": ["Paper", "Cardboard", "Plastic bottles"], "type": "Dry recyclables", "description": "Demo listing for sorted dry recyclables collected in bulk.", "schedule": "Weekly collection (illustrative)"},
    {"id": "REC-02", "name": "Community Compost Point", "materials": ["Food scraps", "Garden waste"], "type": "Organic waste", "description": "Demo listing for segregated organic waste where composting capacity is available.", "schedule": "Confirm capacity before delivery"},
    {"id": "REC-03", "name": "Authorised E-Waste Take-Back", "materials": ["Batteries", "Small electronics", "Cables"], "type": "E-waste", "description": "Use only an authorised handler; this placeholder is not a verified vendor endorsement.", "schedule": "Contact facilities team first"},
    {"id": "REC-04", "name": "Metal Recovery Collection", "materials": ["Aluminium cans", "Scrap metal"], "type": "Metal", "description": "Demo listing to model connecting recovered material with a downstream recycler.", "schedule": "Minimum quantity may apply"},
]


@app.get("/api/recyclers")
def get_recyclers() -> list[dict[str, Any]]:
    return RECYCLERS


@app.post("/api/recyclers/{recycler_id}/request")
def create_recycler_request(recycler_id: str, payload: RecyclerRequest) -> dict[str, Any]:
    recycler = next((r for r in RECYCLERS if r["id"] == recycler_id), None)
    if not recycler:
        raise HTTPException(status_code=404, detail="Recycler listing not found")
    req_id = "RR-" + uuid.uuid4().hex[:6].upper()
    with connect() as db:
        db.execute(
            "INSERT INTO recycler_requests VALUES (?,?,?,?,?,?,?,?)",
            (req_id, recycler_id, recycler["name"], payload.material, payload.contact, payload.location, "Requested", now_iso()),
        )
        db.execute("INSERT INTO activity VALUES (?,?,?,?,?)", (str(uuid.uuid4()), "Recycler pickup requested", f"{payload.material} → {recycler['name']}", "recycle", now_iso()))
    return {"ok": True, "request_id": req_id, "message": "Demo request saved. A real deployment needs an operations team to confirm pickup."}


@app.get("/api/impact")
def get_impact() -> dict[str, Any]:
    with connect() as db:
        scan_count = db.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        completed = db.execute("SELECT COUNT(*) FROM pickups WHERE status='Completed'").fetchone()[0]
        total = db.execute("SELECT COUNT(*) FROM pickups").fetchone()[0]
        bins = db.execute("SELECT fill_level FROM bins").fetchall()
    avg_fill = round(sum(x["fill_level"] for x in bins) / max(1, len(bins)))
    return {
        "is_demo_data": True,
        "indicators": [
            {"label": "Waste diverted", "value": "42 kg", "description": "Illustrative pilot target; not measured data."},
            {"label": "Segregation scans", "value": str(scan_count), "description": "Scan interactions recorded by this demo."},
            {"label": "Pickup completion", "value": f"{round(100 * completed / max(total, 1))}%", "description": "Based on demo pickup queue records."},
            {"label": "Average bin fill", "value": f"{avg_fill}%", "description": "Average across seeded bin statuses."},
        ],
        "recommended_metrics": ["kg by waste category", "contamination rate", "recycling recovery rate", "collection distance and time", "overflow incidents per week", "cost per kg recovered"],
    }


@app.get("/api/activity")
def get_activity() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("SELECT * FROM activity ORDER BY created_at DESC LIMIT 30").fetchall()
    return [dict(x) for x in rows]
