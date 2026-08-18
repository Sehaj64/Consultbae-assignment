"""Task 2 bridge: let n8n read/write the same SQLite database from Task 1."""

from flask import Flask, jsonify, request
import sqlite3
from pathlib import Path

app = Flask(__name__)
DB_FILE = Path(__file__).resolve().parent / "consultbae.db"


def connect():
    return sqlite3.connect(DB_FILE)


@app.get("/")
def home():
    return jsonify({"status": "ok", "message": "ConsultBae Task 2 API"})


@app.get("/candidates")
def get_candidates():
    """Return candidates that still need an LLM skill tag."""
    with connect() as conn:
        rows = conn.execute("""
            SELECT candidate_id, full_name, skills
            FROM candidates
            WHERE skills IS NOT NULL
              AND (skill_category IS NULL OR TRIM(skill_category) = '')
        """).fetchall()

    candidates = [
        {"candidate_id": row[0], "full_name": row[1], "skills": row[2]}
        for row in rows
    ]
    return jsonify({"candidates": candidates})


@app.post("/category")
def save_category():
    """Save n8n's LLM category back to the same Task 1 database."""
    data = request.get_json()
    candidate_id = data.get("candidate_id")
    skill_category = data.get("skill_category")

    if not candidate_id or not skill_category:
        return jsonify({"error": "candidate_id and skill_category are required"}), 400

    with connect() as conn:
        conn.execute(
            "UPDATE candidates SET skill_category = ? WHERE candidate_id = ?",
            (skill_category, candidate_id),
        )
        conn.commit()

    return jsonify({
        "status": "updated",
        "candidate_id": candidate_id,
        "skill_category": skill_category,
    })


if __name__ == "__main__":
    app.run(debug=True)
