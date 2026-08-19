# ConsultBae — AI Automation Take-Home Assignment

I built this as one small system rather than three disconnected tasks:

- clean and merge the three messy candidate CSVs into one SQLite database;
- use n8n + Gemini to classify candidate skills and write the result back to that same database;
- collect audio submissions, calculate the required audio properties, and store the metadata in the same database.

The main goal was to keep the data flow simple enough that I can explain how each part works.

## Submission links

- **GitHub repository:** https://github.com/Sehaj64/Consultbae-assignment
- **Video walkthrough (Loom):** https://www.loom.com/share/d1af898f9a384168bc6af14370df08dd
- **Candidate skill results:** https://skkr.pythonanywhere.com/results
- **Pending candidates API used by n8n:** https://skkr.pythonanywhere.com/candidates
- **Audio submission form:** https://skkr.pythonanywhere.com/audio
- **Audio submissions + playback:** https://skkr.pythonanywhere.com/audio/submissions
- **Exported n8n workflow:** [`n8n_skill_tagging.json`](./n8n_skill_tagging.json)

The `/results` page shows all merged candidates and their `skill_category`, which makes it easy to inspect the labels written back by the n8n workflow. The `/candidates` endpoint only returns candidates that still have skill data waiting to be classified.

## Quick reviewer path

1. Run `python pipeline.py` to rebuild the merged candidate dataset and SQLite database.
2. Open `merged_candidates.csv` to inspect the 56 merged candidate records.
3. Import `n8n_skill_tagging.json` into n8n, add a Gemini credential, and run the workflow to classify candidates and write categories back through the Flask API.
4. Use the deployed audio form to record/upload a WAV file, then open the submissions page to see playback and extracted audio properties.

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

`pipeline.py` loads all three CSV files, maps them into one common structure, cleans the fields, matches records that belong to the same person, and writes the final result into the SQLite `candidates` table.

Current result: **103 valid source rows → 56 unique candidates**.

### Matching logic

I kept the matching careful:

1. normalized email or phone first;
2. exact name + city only when there was no conflicting identifier;
3. never merge only because the names look the same.

This matters because there are ambiguous records such as multiple `Arjun Mehta` entries. If the identifiers conflict, I keep them separate instead of forcing a merge.

## Task 2 — n8n + Gemini skill tagging

The exported n8n workflow is included as `n8n_skill_tagging.json`.

```text
Manual Trigger
→ GET /candidates
→ Split Out
→ Limit
→ Gemini
→ POST /category
→ SQLite
```

I kept SQLite as the main database. Since n8n Cloud cannot directly open the SQLite file on my machine/server, I added a small Flask API in `task2_api.py`:

- `GET /candidates` returns candidates whose `skill_category` is empty;
- `POST /category` accepts `candidate_id` + the Gemini category and updates that row in SQLite.

Gemini returns one of:

- `automation-heavy`
- `web dev`
- `data`
- `other`

One of the 56 merged candidates has no skills in the source data. The API skips records with no skills instead of asking the model to guess a skill category, so the workflow tagged the 55 candidates that had skill data.

For the demo, the Flask app is hosted on PythonAnywhere.

> This is not an automatic file-change trigger. If the CSV files change, I rerun Task 1 first so SQLite contains the latest cleaned data, then run the n8n workflow against that latest database state.

## Task 3 — Audio collection app

The audio app is in `task3_audio.py` with simple HTML templates.

A user can:

- enter name and phone number;
- record audio in the browser or upload a WAV file;
- submit the recording;
- open a second page that lists saved submissions with an audio player.

The audio file is stored in `audio_uploads/`. The metadata goes into the `audio_submissions` table inside the same `consultbae.db` used by Task 1.

For each 16-bit PCM WAV submission I store:

- duration (seconds)
- sample rate (kHz)
- bitrate (kbps)
- RMS loudness (dBFS)

I used RMS dBFS as a simple loudness estimate; it is not a full LUFS measurement.

Routes:

- `/audio` — record/upload form
- `/audio/submissions` — saved submissions + playback

Demo deployment at submission time:

- `https://skkr.pythonanywhere.com/audio`
- `https://skkr.pythonanywhere.com/audio/submissions`

## Setup

```bash
pip install -r requirements.txt
python pipeline.py
python task2_api.py
```

This creates `consultbae.db`, writes `merged_candidates.csv`, and starts the Flask app.

For Task 2, import `n8n_skill_tagging.json` into n8n and configure your own Gemini credential. No Gemini API key is stored in the repository.

> Rerunning `pipeline.py` rebuilds the `candidates` table, so the `skill_category` values are reset. After rebuilding Task 1, rerun the n8n workflow to populate them again.

## Task 4 — Data issues found and what I did

These are the issues I found while working through the three source files:

1. **Different schemas across the three CSVs** — mapped source-specific columns into one common candidate schema.
2. **Phone numbers in different formats** — removed non-numeric characters and normalized valid values to the last 10 digits.
3. **Email casing / whitespace differences** — trimmed and converted emails to lowercase before matching.
4. **City aliases** — normalized values such as `Gurgaon`/`Gurugram`, `Bangalore`/`Bengaluru`, and Delhi variants.
5. **Multiple date formats** — parsed them and stored dates as `YYYY-MM-DD`.
6. **Mixed CTC scales** — values such as `4.2` were treated as LPA while full INR values were preserved as annual INR.
7. **Blank Gig Worker row** — dropped the completely empty row.
8. **Shifted Gig Worker row** — detected the row where values had moved into the wrong columns and realigned it instead of dropping it.
9. **Repeated CBNexus header inside the data** — removed the repeated header row.
10. **Inconsistent boolean values** — normalized values such as `Y`, `yes`, `Yes`, `N`, and `No`.
11. **Status / skills casing and whitespace** — normalized text before comparison and merging.
12. **Same person with different name representation** — e.g. `R. Verma` / `Rohit Verma`; stronger identifiers were used to connect them.
13. **Different emails for the same person** — e.g. Nikhil Chopra could still be linked through the same phone number.
14. **Ambiguous same-name records** — multiple `Arjun Mehta` records had conflicting identifiers, so I kept them separate.
15. **Missing values** — kept them as null rather than guessing or inventing data.
16. **Gig rates in different units** — kept the original rate text instead of making an unsupported hourly/monthly conversion.

## Stuck log — what actually happened

I was not blocked for hours on every task, but there were a few places where I had to stop, rethink the approach, and simplify it before moving on. Most of my debugging came from searching through the actual CSV/output rows, checking n8n node output and errors, and checking the PythonAnywhere setup rather than doing broad web searches.

### 1. The first merge solution became harder to explain than it needed to be

My first concern with Task 1 was not only "does it run?" but "can I explain why every merge happened?" The earlier approach was becoming more complicated than I wanted for this dataset.

I searched the source and merged output for repeated emails, repeated phones, and same-name cases to see where a simple rule could fail. I asked AI to help me simplify the pipeline without changing the core result. I considered more aggressive fuzzy/name-based matching, but rejected it because a false merge is worse than leaving an uncertain person separate.

I ended up with a simpler rule that I can explain: **email/phone first, then exact name + city only when identifiers do not conflict**. The ambiguous `Arjun Mehta` rows were a useful test of this rule because I deliberately did not force them into one person.

### 2. I first thought a simple processed output into n8n would be enough

This was the main decision in Task 2.

At first I thought I could just feed the processed data into n8n and run the Gemini step. Then I asked myself: **if the Task 1 data changes, how will this workflow use the updated data?** A copied/static dataset inside n8n would work for one demo, but it could become stale.

I checked the n8n options for how the cloud workflow could reach my data and asked AI how n8n Cloud could read and write the SQLite database created by Task 1. I looked at using a separate n8n Data Table, but rejected that because it would give me another copy of the data to keep in sync.

The solution was to keep SQLite as the main database and expose only two small API endpoints through Flask. n8n reads current candidates through `GET /candidates` and writes the Gemini result back through `POST /category`.

That is also why I hosted the Flask app on PythonAnywhere: n8n Cloud needed an internet-accessible endpoint instead of a local SQLite file.

### 3. Getting the Gemini output all the way back into SQLite

Once the n8n flow was connected, I still had to get the Gemini node configured and map its response correctly into the final POST request.

I hit a **model-required** setup error first, and later a temporary **service unavailable / high demand** response from Gemini. I used the n8n error/output panel to see what was failing, checked the Gemini node settings, selected the text/model configuration, enabled retry, and tested with one candidate before processing the rest.

The next thing I had to understand was the response shape. Gemini did not return a flat value; the category was inside `content.parts[0].text`, and the returned text also had quote characters around it. I inspected the n8n output and mapped that field into the final HTTP request, removing the extra quotes before writing it back.

I kept the candidate ID with the same item so the category was written to the correct person. After the final run, `GET /candidates` returned:

```json
{"candidates":[]}
```

which was my check that all candidates returned by the tagging endpoint had been processed.

## Task 5 — Optional scaling notes

If this had to handle around 5,000 workers over one weekend, the first two changes I would make are:

1. **Move audio storage away from the web server** — I would use AWS S3 or another object-storage service instead of keeping recordings inside `audio_uploads/` on the Flask server. This would give the app much more storage space and keep large audio files separate from the application server.
2. **Move the database from SQLite to PostgreSQL** — SQLite is fine for this assignment, but PostgreSQL would handle many users writing data at the same time more reliably.

After that, I would add a queue for audio processing so uploads do not have to wait for analysis, prevent duplicate submissions with a unique submission ID, add upload limits and clear error handling, and decide how long old audio recordings should be kept so storage costs do not keep growing.

## Files

- `pipeline.py` — Task 1 cleaning, matching and SQLite load
- `source1_naukri_applicants.csv` — source data
- `source2_gig_workers.csv` — source data
- `source3_cbnexus_contacts.csv` — source data
- `merged_candidates.csv` — readable merged output
- `task2_api.py` — Flask API bridge + app entry point
- `n8n_skill_tagging.json` — exported Task 2 workflow
- `task3_audio.py` — Task 3 audio backend and analysis
- `templates/` — Task 3 HTML pages
- `requirements.txt` — dependencies

## AI use

When something was new or confusing, I used ChatGPT to understand it or fix an issue. I then checked the final flow myself so I knew what each part was doing.
