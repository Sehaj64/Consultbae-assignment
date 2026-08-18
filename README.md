# ConsultBae Assignment

Task 1 merges three messy CSV sources into one clean SQLite database.

## Run

```bash
pip install -r requirements.txt
python pipeline.py
```

The pipeline reads the three source CSVs, cleans and normalizes fields, matches the same person primarily by email or phone with a guarded exact name + city fallback, and writes the final records to `consultbae.db` in the `candidates` table. It also writes `merged_candidates.csv` as a readable preview.

Current Task 1 result: **103 valid source rows -> 56 unique candidates**.

Task 2 and later parts will be added next.
