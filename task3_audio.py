"""Task 3: record/upload WAV audio, calculate metrics, and save metadata to SQLite."""

from array import array
from pathlib import Path
import math
import sqlite3
import sys
import uuid
import wave

from flask import Blueprint, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename


audio_bp = Blueprint("audio", __name__)
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "consultbae.db"
UPLOAD_DIR = BASE_DIR / "audio_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def connect():
    return sqlite3.connect(DB_FILE)


def init_audio_table():
    """Create the Task 3 table inside the same database used by Task 1."""
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audio_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                audio_filename TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                sample_rate_khz REAL NOT NULL,
                bitrate_kbps REAL NOT NULL,
                loudness_db REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def analyze_wav(path):
    """Return duration, sample rate, bitrate, and RMS loudness for a 16-bit PCM WAV file."""
    with wave.open(str(path), "rb") as audio:
        channels = audio.getnchannels()
        sample_width = audio.getsampwidth()
        sample_rate = audio.getframerate()
        frame_count = audio.getnframes()
        compression = audio.getcomptype()
        raw_audio = audio.readframes(frame_count)

    if compression != "NONE" or sample_width != 2:
        raise ValueError("Please use a 16-bit PCM WAV file.")

    duration_seconds = frame_count / sample_rate if sample_rate else 0
    sample_rate_khz = sample_rate / 1000
    bitrate_kbps = sample_rate * channels * sample_width * 8 / 1000

    samples = array("h")
    samples.frombytes(raw_audio)
    if sys.byteorder == "big":
        samples.byteswap()

    if samples:
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        loudness_db = 20 * math.log10(max(rms, 1) / 32768)
    else:
        loudness_db = -96.0

    return {
        "duration_seconds": round(duration_seconds, 2),
        "sample_rate_khz": round(sample_rate_khz, 2),
        "bitrate_kbps": round(bitrate_kbps, 2),
        "loudness_db": round(loudness_db, 2),
    }


@audio_bp.route("/audio", methods=["GET", "POST"])
def audio_form():
    if request.method == "GET":
        return render_template("audio_form.html", error=None)

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    audio_file = request.files.get("audio")

    if not name or not phone or not audio_file or not audio_file.filename:
        return render_template(
            "audio_form.html",
            error="Name, phone, and a recorded/uploaded WAV file are required.",
        ), 400

    if Path(audio_file.filename).suffix.lower() != ".wav":
        return render_template("audio_form.html", error="Please use a WAV file."), 400

    safe_name = secure_filename(audio_file.filename) or "recording.wav"
    filename = f"{uuid.uuid4().hex}_{safe_name}"
    saved_path = UPLOAD_DIR / filename
    audio_file.save(saved_path)

    try:
        metrics = analyze_wav(saved_path)
    except (wave.Error, ValueError) as exc:
        saved_path.unlink(missing_ok=True)
        return render_template("audio_form.html", error=str(exc)), 400

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO audio_submissions (
                name, phone, audio_filename,
                duration_seconds, sample_rate_khz, bitrate_kbps, loudness_db
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                phone,
                filename,
                metrics["duration_seconds"],
                metrics["sample_rate_khz"],
                metrics["bitrate_kbps"],
                metrics["loudness_db"],
            ),
        )
        conn.commit()

    return redirect(url_for("audio.audio_submissions"))


@audio_bp.get("/audio/submissions")
def audio_submissions():
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audio_submissions ORDER BY id DESC"
        ).fetchall()
    return render_template("audio_submissions.html", submissions=rows)


@audio_bp.get("/audio/file/<path:filename>")
def audio_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


init_audio_table()
