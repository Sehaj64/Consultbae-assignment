"""ConsultBae Task 1: merge three messy CSVs into one SQLite database."""

import re
import sqlite3
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd

BASE = Path(__file__).resolve().parent
DB_FILE = BASE / "consultbae.db"
OUTPUT_CSV = BASE / "merged_candidates.csv"

COLUMNS = [
    "source", "name", "email", "phone", "city", "skills",
    "experience_years", "current_ctc_inr", "applied_date",
    "gig_rate", "gig_status", "verified", "projects_completed",
]


# ---------- CLEANING ----------

def clean_text(value):
    if pd.isna(value) or str(value).strip() == "":
        return None
    return str(value).strip()


def clean_phone(value):
    value = clean_text(value)
    if not value:
        return None
    digits = re.sub(r"\D", "", value)[-10:]
    return digits if len(digits) == 10 else None


def clean_city(value):
    value = clean_text(value)
    if not value:
        return None
    aliases = {
        "gurgaon": "Gurugram", "gurugram": "Gurugram",
        "bangalore": "Bengaluru", "bengaluru": "Bengaluru",
        "new delhi": "Delhi", "delhi ncr": "Delhi", "delhi": "Delhi",
    }
    return aliases.get(value.lower(), value.title())


def clean_date(value):
    value = clean_text(value)
    if not value:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        result = pd.to_datetime(value, format="%Y-%m-%d", errors="coerce")
    elif "/" in value:
        result = pd.to_datetime(value, format="%m/%d/%Y", errors="coerce")
    elif re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", value):
        result = pd.to_datetime(value, format="%d-%m-%Y", errors="coerce")
    else:
        result = pd.to_datetime(value, dayfirst=True, errors="coerce")
    return result.strftime("%Y-%m-%d") if pd.notna(result) else None


def clean_ctc(value):
    value = clean_text(value)
    if not value:
        return None
    try:
        number = float(value)
        return int(round(number * 100000 if number <= 100 else number))
    except ValueError:
        return None


def standardize(df, source):
    """Give all three source files the same columns and clean matching fields."""
    for column in COLUMNS:
        if column not in df:
            df[column] = None

    df["source"] = source
    df["name"] = df["name"].apply(lambda x: (ct := clean_text(x)) and ct.title() or None)
    df["email"] = df["email"].apply(lambda x: (ct := clean_text(x)) and ct.lower() or None)
    df["phone"] = df["phone"].apply(clean_phone)
    df["city"] = df["city"].apply(clean_city)
    df["skills"] = df["skills"].apply(
        lambda x: (lambda ct: ", ".join(s.strip().lower() for s in ct.split(",") if s.strip()) if ct else None)(clean_text(x))
    )
    return df[COLUMNS].astype(object)


# ---------- LOAD THE THREE SOURCES ----------

def load_sources():
    # Naukri
    naukri = pd.read_csv(BASE / "source1_naukri_applicants.csv", dtype=str).rename(columns={
        "Full Name": "name", "Email": "email", "Phone": "phone",
        "City": "city", "Skills": "skills",
        "Experience (Years)": "experience_years",
        "Current CTC": "current_ctc_inr", "Applied Date": "applied_date",
    })
    naukri["experience_years"] = pd.to_numeric(naukri["experience_years"], errors="coerce")
    naukri["current_ctc_inr"] = naukri["current_ctc_inr"].apply(clean_ctc)
    naukri["applied_date"] = naukri["applied_date"].apply(clean_date)
    naukri = standardize(naukri, "naukri")

    # Gig workers: drop blank rows and repair the one shifted row.
    gigs = pd.read_csv(BASE / "source2_gig_workers.csv", dtype=str).dropna(how="all")
    email_has_at = gigs["email_id"].astype(str).apply(lambda x: "@" in x)
    worker_has_at = gigs["worker_name"].astype(str).apply(lambda x: "@" in x)
    shifted = (~email_has_at) & worker_has_at
    for i in gigs[shifted].index:
        old = gigs.loc[i].copy()
        gigs.loc[i, ["email_id", "worker_name", "rate", "location", "status", "skill_tags"]] = [
            old["worker_name"], old["rate"], old["location"],
            old["status"], old["skill_tags"], old["email_id"],
        ]
    gigs = gigs.rename(columns={
        "worker_name": "name", "email_id": "email", "location": "city",
        "skill_tags": "skills", "rate": "gig_rate", "status": "gig_status",
    })
    gigs["gig_status"] = gigs["gig_status"].apply(
        lambda x: (ct := clean_text(x)) and ct.title() or None
    )
    gigs = standardize(gigs, "gigs")

    # CBNexus: remove the repeated header and normalize yes/no values.
    cbnexus = pd.read_csv(BASE / "source3_cbnexus_contacts.csv", dtype=str)
    cbnexus = cbnexus[cbnexus["Name"].str.strip().str.lower() != "name"].rename(columns={
        "Name": "name", "Phone Number": "phone", "City": "city",
        "Verified": "verified", "Projects Completed": "projects_completed",
    })
    cbnexus["verified"] = cbnexus["verified"].apply(
        lambda x: 1 if str(x).strip().lower() in {"y", "yes", "true", "1"} else 0
    )
    cbnexus["projects_completed"] = pd.to_numeric(cbnexus["projects_completed"], errors="coerce")
    cbnexus = standardize(cbnexus, "cbnexus")

    return pd.concat([naukri, gigs, cbnexus], ignore_index=True)


# ---------- MATCH THE SAME PERSON ----------

def add_record(group, record):
    group["records"].append(record)
    if record["email"]:
        group["emails"].add(record["email"])
    if record["phone"]:
        group["phones"].add(record["phone"])


def match_people(records):
    """First match by email/phone, then use safe exact name+city as fallback."""
    groups = []

    for record in records:
        matches = [i for i, g in enumerate(groups)
                   if (record["email"] and record["email"] in g["emails"])
                   or (record["phone"] and record["phone"] in g["phones"])]

        if not matches:
            group = {"records": [], "emails": set(), "phones": set()}
            add_record(group, record)
            groups.append(group)
            continue

        main = groups[matches[0]]
        add_record(main, record)
        for i in reversed(matches[1:]):
            other = groups.pop(i)
            main["records"] += other["records"]
            main["emails"] |= other["emails"]
            main["phones"] |= other["phones"]

    # Guarded fallback: exact name + city, only when there is one possible pair.
    def best(group, field):
        values = [r[field] for r in group["records"] if r[field]]
        return (max(values, key=len) if field == "name" else Counter(values).most_common(1)[0][0]) if values else None

    same_name_city = defaultdict(list)
    for group in groups:
        name = best(group, "name")
        city = best(group, "city")
        if name and city:
            same_name_city[(name.lower(), city.lower())].append(group)

    remove = set()
    for pair in same_name_city.values():
        if len(pair) != 2:
            continue
        first, second = pair
        if (first["emails"] and second["emails"]) or (first["phones"] and second["phones"]):
            continue
        first["records"] += second["records"]
        first["emails"] |= second["emails"]
        first["phones"] |= second["phones"]
        remove.add(id(second))

    return [g for g in groups if id(g) not in remove], best


# ---------- CREATE FINAL CANDIDATES ----------

def build_candidates(groups, best):
    def first(records, field):
        for record in records:
            value = record[field]
            if value is not None and not pd.isna(value):
                return value
        return None

    rows = []
    for number, group in enumerate(groups, 1):
        records = group["records"]
        skill_set = {s.strip() for r in records if r["skills"] for s in r["skills"].split(",")}
        emails = sorted(group["emails"], key=lambda x: (x.startswith("alt."), len(x), x))

        rows.append({
            "candidate_id": f"C{number:03d}", "full_name": best(group, "name"),
            "email": emails[0] if emails else None,
            "phone": sorted(group["phones"])[0] if group["phones"] else None,
            "city": best(group, "city"), "skills": ", ".join(sorted(skill_set)) if skill_set else None,
            "skill_category": None,  # Task 2 writes the LLM tag here.
            "experience_years": first(records, "experience_years"),
            "current_ctc_inr": first(records, "current_ctc_inr"),
            "applied_date": first(records, "applied_date"),
            "gig_rate": first(records, "gig_rate"), "gig_status": first(records, "gig_status"),
            "verified": first(records, "verified"),
            "projects_completed": first(records, "projects_completed"),
            "sources": ", ".join(sorted({r["source"] for r in records})),
        })
    return pd.DataFrame(rows)


# ---------- RUN ----------

def main():
    all_rows = load_sources().where(lambda df: pd.notna(df), None)
    records = all_rows.to_dict("records")
    groups, best = match_people(records)
    final = build_candidates(groups, best)

    for column in ["current_ctc_inr", "verified", "projects_completed"]:
        final[column] = final[column].astype("Int64")

    with sqlite3.connect(DB_FILE) as connection:
        final.to_sql("candidates", connection, if_exists="replace", index=False)
    final.to_csv(OUTPUT_CSV, index=False)

    print("TASK 1 COMPLETE")
    print(f"Valid source rows: {len(records)}")
    print(f"Final unique candidates: {len(final)}")
    print(f"Database: {DB_FILE} -> candidates")


if __name__ == "__main__":
    main()
