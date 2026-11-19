"""reno-forge - local-first home renovation planner and materials takeoff workbench.

Flask app: REST API, static UI and a SQLite log of saved reviews.
No API keys, no network calls, no LLM.
"""

import io
import json
import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, request, send_from_directory

import engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.environ.get("RENO_FORGE_DB", os.path.join(BASE_DIR, "reno_forge.sqlite3"))

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS runs (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   created_at TEXT NOT NULL,
                   project_name TEXT,
                   profile TEXT,
                   score REAL,
                   verdict TEXT,
                   budget REAL,
                   estimate REAL,
                   self_rating INTEGER,
                   notes TEXT,
                   brief TEXT
               )"""
        )


@app.before_request
def _ensure_db():
    if request.path.startswith("/api/"):
        init_db()


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


# --------------------------------------------------------------------------
# api
# --------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "app": "reno-forge", "version": "1.0.0"})


@app.get("/api/profiles")
def profiles():
    return jsonify([
        {"id": key, "label": meta["label"], "weights": meta["weights"]}
        for key, meta in engine.PROFILES.items()
    ])


@app.get("/api/samples")
def samples():
    out = []
    if os.path.isdir(SAMPLES_DIR):
        for name in sorted(os.listdir(SAMPLES_DIR)):
            if not name.endswith(".txt"):
                continue
            path = os.path.join(SAMPLES_DIR, name)
            with open(path, encoding="utf-8") as fh:
                brief = fh.read()
            out.append({
                "id": name[:-4],
                "label": name[:-4].replace("_", " ").title(),
                "brief": brief,
            })
    return jsonify(out)


@app.get("/api/samples/<sample_id>")
def sample(sample_id):
    path = os.path.join(SAMPLES_DIR, sample_id + ".txt")
    if not os.path.isfile(path):
        return jsonify({"error": "sample not found"}), 404
    with open(path, encoding="utf-8") as fh:
        return jsonify({"id": sample_id, "brief": fh.read()})


@app.post("/api/analyze")
def analyze():
    data = request.get_json(silent=True) or {}
    brief = data.get("brief") or ""
    profile = data.get("profile") or "general"
    if profile not in engine.PROFILES:
        profile = "general"
    if not brief.strip():
        return jsonify({"error": "brief is required"}), 400
    result = engine.analyse(brief, profile)
    return jsonify(result)


@app.post("/api/export")
def export():
    data = request.get_json(silent=True) or {}
    brief = data.get("brief") or ""
    profile = data.get("profile") or "general"
    fmt = (data.get("format") or "md").lower()
    if profile not in engine.PROFILES:
        profile = "general"
    if not brief.strip():
        return jsonify({"error": "brief is required"}), 400
    result = engine.analyse(brief, profile)
    name = "reno-forge-report"
    if fmt == "md":
        body = engine.to_markdown(result)
        mime = "text/markdown"
    elif fmt == "csv":
        body = engine.to_csv(result)
        mime = "text/csv"
    else:
        body = json.dumps(result, indent=2, default=str)
        mime = "application/json"
    return Response(
        body,
        mimetype=mime,
        headers={"Content-Disposition": 'attachment; filename="%s.%s"' % (name, fmt)},
    )


@app.post("/api/runs")
def create_run():
    data = request.get_json(silent=True) or {}
    brief = data.get("brief") or ""
    profile = data.get("profile") or "general"
    if profile not in engine.PROFILES:
        profile = "general"
    if not brief.strip():
        return jsonify({"error": "brief is required"}), 400
    result = engine.analyse(brief, profile)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO runs (created_at, project_name, profile, score, verdict,
                                 budget, estimate, self_rating, notes, brief)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                created,
                result["project"]["name"],
                profile,
                result["score"]["overall"],
                result["score"]["verdict"],
                result["cost"]["budget"],
                result["cost"]["total"],
                data.get("self_rating"),
                data.get("notes") or "",
                brief,
            ),
        )
        run_id = cur.lastrowid
    return jsonify({"id": run_id, "created_at": created, "score": result["score"]["overall"]}), 201


@app.get("/api/runs")
def list_runs():
    limit = request.args.get("limit", default=50, type=int)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, created_at, project_name, profile, score, verdict,
                      budget, estimate, self_rating, notes
               FROM runs ORDER BY id DESC LIMIT ?""",
            (max(1, min(limit, 200)),),
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.get("/api/runs/<int:run_id>")
def get_run(run_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return jsonify({"error": "run not found"}), 404
    record = dict(row)
    record["result"] = engine.analyse(record["brief"], record["profile"])
    return jsonify(record)


@app.patch("/api/runs/<int:run_id>")
def update_run(run_id):
    data = request.get_json(silent=True) or {}
    with get_db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return jsonify({"error": "run not found"}), 404
        rating = data.get("self_rating", row["self_rating"])
        notes = data.get("notes", row["notes"])
        conn.execute(
            "UPDATE runs SET self_rating = ?, notes = ? WHERE id = ?",
            (rating, notes, run_id),
        )
    return jsonify({"id": run_id, "self_rating": rating, "notes": notes})


@app.delete("/api/runs/<int:run_id>")
def delete_run(run_id):
    with get_db() as conn:
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    return jsonify({"deleted": run_id})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8765"))
    app.run(host="127.0.0.1", port=port, debug=False)
