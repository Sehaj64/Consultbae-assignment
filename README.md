# ConsultBae — AI Automation Take-Home Assignment

This project merges three messy candidate datasets into one clean database, adds an n8n + Gemini classification workflow on top of that data, and provides a small audio collection app that stores audio metadata in the same database.

## Architecture

```text
3 CSV files
    ↓
Python + Pandas cleaning / matching
    ↓
SQLite: consultbae.db
    ├── candidates
    │      ↓
    │   Flask API ↔ n8n ↔ Gemini
    │      ↓
    │   skill_category written back
    │
    └── audio_submissions
           ↑
      Flask audio app
```

## Task 1 — Merge and deduplicate

`pipeline.py` reads all three CSVs, standardizes their fields, resolves data-quality issues, matches records that represent the same person, and writes the final result to SQLite table `candidates`.

Current result: **103 valid source rows → 56 unique candidates**.

Matching strategy:

1. Match primarily on normalized email or phone because they are stronger identifiers.
2. Use exact name + city only as a guarded fallback when there is no conflicting identifier.
3. Do not merge records just because the names are the same.

This conservative approach was chosen to avoid false merges, especially for ambiguous records such as multiple `Arjun Mehta` entries with conflicting identifiers.

## Task 2 — n8n + Gemini skill tagging

The exported workflow is in `n8n_skill_tagging.json`.

Flow:

```text
Manual Trigger
→ GET /candidates
→ Split Out
→ Limit
→ Gemini
→ POST /category
→ SQLite
```

SQLite is the source of truth. Because n8n Cloud cannot directly open a local SQLite file, `task2_api.py` exposes a small Flask API:

- `GET /candidates` returns candidates whose `skill_category` is still empty.
- `POST /category` receives `candidate_id` and the Gemini-generated category and updates the same SQLite database.

The Gemini step classifies skills into one of:

- `automation-heavy`
- `web dev`
- `data`
- `other`

The Flask app is deployed on PythonAnywhere for the demo.

## Task 3 — Audio collection app

The audio app is implemented in `task3_audio.py` with simple HTML templates.

A user can:

- enter name and phone number;
- record audio in the browser or upload a WAV file;
- submit the recording;
- view all submissions on a second page with an audio player.

The actual audio file is stored in `audio_uploads/`, while metadata is stored in the `audio_submissions` table inside the same `consultbae.db` used by Task 1.

For every 16-bit PCM WAV submission, the backend extracts:

- duration in seconds;
- sample rate in kHz;
- bitrate in kbps;
- RMS loudness in dBFS.

Routes:

- `/audio` — record/upload form
- `/audio/submissions` — saved submissions and playback

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Build the Task 1 database

```bash
python pipeline.py
```

This creates `consultbae.db` and `merged_candidates.csv`.

### 3. Run the Flask app locally

```bash
python task2_api.py
```

The same Flask application serves both the Task 2 API and Task 3 audio routes.

### 4. Import the n8n workflow

Import `n8n_skill_tagging.json` into n8n and configure your own Google Gemini credential. The submitted workflow does not include a Gemini API key.

> Note: rerunning `pipeline.py` rebuilds the `candidates` table and resets the derived `skill_category` values. After a fresh Task 1 rebuild, rerun the n8n workflow to repopulate the categories.

## Task 4 — Data issues found and how I handled them

I treated the supplied files as intentionally messy rather than assuming every row or value was trustworthy.

1. **Different schemas across all three files** — mapped source-specific columns into one common candidate schema before merging.
2. **Phone numbers in inconsistent formats** — removed non-numeric characters and normalized valid numbers to the last 10 digits.
3. **Email casing and whitespace differences** — trimmed whitespace and converted emails to lowercase before matching.
4. **City aliases and casing** — standardized values such as `Gurgaon`/`Gurugram`, `Bangalore`/`Bengaluru`, and Delhi variants.
5. **Multiple date formats** — parsed the different formats and stored dates consistently as `YYYY-MM-DD`.
6. **Mixed CTC scales** — values such as `4.2` represented LPA while other rows contained full INR amounts. Small numeric values were converted to annual INR.
7. **Blank Gig Worker row** — removed completely empty rows.
8. **Shifted Gig Worker row** — detected a row where the email appeared in the worker-name column and repaired the shifted values before standardization.
9. **Repeated CBNexus header inside the data** — detected and removed the repeated header row.
10. **Inconsistent boolean values** — normalized values such as `Y`, `yes`, `Yes`, `N`, and `No` into consistent database values.
11. **Inconsistent status/skill casing and whitespace** — normalized text before comparing or combining it.
12. **Same person represented differently across sources** — for example, name variations such as `R. Verma` / `Rohit Verma` could still be connected when a stronger identifier matched.
13. **Different emails for the same person** — for example, records such as Nikhil Chopra could have different emails but the same phone number, so the phone was used as the stronger link.
14. **Ambiguous same-name records** — multiple `Arjun Mehta` records had conflicting identifiers. I deliberately kept them separate rather than performing a risky name-only merge.
15. **Missing fields** — some records did not contain email, phone, skills, or other attributes. I kept missing values as null instead of inventing data.
16. **Gig rates expressed in different units** — values could be hourly or monthly. I preserved the original rate text rather than making an unsupported conversion assumption.

## Stuck log

### 1. Matching people without one common ID

The first hard part was deciding when two rows should become one person. A name-only match looked simple, but I realized it would create false positives when two different people had the same name.

I asked AI to help compare matching strategies when there is no common ID across sources. I considered fuzzy/name-based matching, but rejected using it as the primary rule because I could not safely prove that similar names were the same person. I instead used normalized email and phone as the strongest identifiers, with exact name + city only as a guarded fallback.

The ambiguous `Arjun Mehta` records were useful here: instead of forcing them together, I kept records with conflicting identifiers separate. That made the pipeline more conservative but safer.

### 2. Connecting SQLite to n8n Cloud

My first idea for Task 2 was to feed a processed/static copy of the data into n8n. That would work for a one-time demo, but it would create another copy of the data and could become stale after Task 1 was rerun.

I asked AI how n8n Cloud could work with the SQLite database created by Task 1 and compared using a separate n8n Data Table with exposing my existing database through an API. I rejected the separate Data Table approach because it would create a second source of truth.

The solution was a small Flask API hosted on PythonAnywhere. n8n reads current unclassified candidates through `GET /candidates`, sends their skills to Gemini, and writes the result back through `POST /category`. SQLite therefore remains the source of truth.

This is not a file-change trigger: if the source CSVs change, Task 1 is rerun first to rebuild SQLite, and then the n8n workflow reads that latest database state.

### 3. Audio recording and audio metrics

I had not previously built browser audio capture or calculated audio properties such as sample rate, bitrate, and loudness. I asked AI how to keep this implementation small enough to understand and defend under the assignment deadline.

I considered supporting many audio formats, but rejected that because it would require extra conversion tooling such as ffmpeg and add failure cases that were not needed for the core requirement. I standardized the implementation around 16-bit PCM WAV. The browser records audio and produces a WAV file, while Python's `wave` module reads the file metadata and samples.

Duration is calculated from frame count / sample rate, bitrate from sample rate × channels × bits per sample, and loudness is an RMS-based dBFS estimate. I kept this implementation deliberately small and explainable instead of adding an audio library I did not need.

## Task 5 — Optional scaling notes

The current SQLite + local-file design is appropriate for a take-home prototype, but I would change it before a weekend launch to 5,000 workers:

- Store audio in object storage such as S3/R2 instead of on the web server filesystem.
- Let clients upload directly using signed upload URLs so large files do not pass through the Flask process.
- Move metadata from SQLite to managed PostgreSQL for concurrent writes and safer production operation.
- Put audio analysis behind a queue so uploads return quickly and failed processing can be retried.
- Use an idempotency/submission key to prevent duplicate records when users retry after network failures.
- Add file-size/type/duration validation, rate limits, monitoring, and retry/error states.
- Add a storage-retention policy because audio volume will be the main ongoing cost.

## Files

- `pipeline.py` — Task 1 cleaning, matching and SQLite load
- `source1_naukri_applicants.csv` — source data
- `source2_gig_workers.csv` — source data
- `source3_cbnexus_contacts.csv` — source data
- `merged_candidates.csv` — readable merged output
- `task2_api.py` — Flask bridge between SQLite and n8n + app entry point
- `n8n_skill_tagging.json` — exported Task 2 n8n workflow
- `task3_audio.py` — Task 3 audio backend and analysis
- `templates/` — Task 3 HTML views
- `requirements.txt` — Python dependencies

## AI use

AI tools were used during development for debugging, comparing implementation options, and understanding unfamiliar areas such as n8n/SQLite integration and browser audio processing. I kept the final implementation intentionally small and reviewed the flow and calculations so that I can explain and extend the submitted solution.
