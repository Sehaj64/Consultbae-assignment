"""Task 2 bridge plus Task 3 audio routes."""

from flask import Flask, jsonify, request
import sqlite3
from pathlib import Path
from html import escape

from task3_audio import audio_bp

app = Flask(__name__)
app.register_blueprint(audio_bp)
DB_FILE = Path(__file__).resolve().parent / "consultbae.db"


def connect():
    return sqlite3.connect(DB_FILE)


@app.get("/")
def home():
    return jsonify({"status": "ok", "message": "ConsultBae API"})


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


@app.get("/results")
def results():
    """Human-readable view of all candidates and their current skill category."""
    with connect() as conn:
        rows = conn.execute("""
            SELECT candidate_id, full_name, skills, skill_category
            FROM candidates
            ORDER BY candidate_id
        """).fetchall()

    table_rows = ""
    for candidate_id, full_name, skills, skill_category in rows:
        table_rows += f"""
        <tr>
            <td>{escape(str(candidate_id or ''))}</td>
            <td>{escape(str(full_name or ''))}</td>
            <td>{escape(str(skills or ''))}</td>
            <td><b>{escape(str(skill_category or 'Not tagged'))}</b></td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ConsultBae Candidate Results</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 30px; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
            th {{ background: #eee; position: sticky; top: 0; }}
        </style>
    </head>
    <body>
        <h2>ConsultBae Candidate Skill Results</h2>
        <p>All merged candidates from SQLite</p>
        <table>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Skills</th>
                <th>Skill Category</th>
            </tr>
            {table_rows}
        </table>
    </body>
    </html>
    """


if __name__ == "__main__":
    app.run(debug=True)
