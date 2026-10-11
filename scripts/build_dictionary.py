"""Download the public ECDICT CSV once, then build an indexed offline dictionary."""
import csv
import hashlib
from pathlib import Path
import sqlite3
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
REVISION = "bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b"
CSV_SHA256 = "1a6947e04785db63613a92e14903cdae7954f7e84860b10e68e5c7cbb3f9c3cf"
sys.path.insert(0, str(ROOT))
from translator.dictionary import search_terms


def main():
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    for name in ("ecdict.csv", "LICENSE"):
        target = data / ("ECDICT-LICENSE.txt" if name == "LICENSE" else name)
        if not target.exists():
            download = target.with_suffix(".download")
            urllib.request.urlretrieve(f"https://raw.githubusercontent.com/skywind3000/ECDICT/{REVISION}/{name}", download)
            download.replace(target)
    if hashlib.sha256((data / "ecdict.csv").read_bytes()).hexdigest() != CSV_SHA256:
        raise ValueError("ECDICT CSV checksum mismatch; remove data/ecdict.csv and retry.")
    target = data / "dictionary.sqlite3"
    staging = target.with_suffix(".tmp")
    if staging.exists():
        staging.unlink()
    db = sqlite3.connect(staging)
    db.executescript("""
        PRAGMA journal_mode=OFF;
        CREATE TABLE entries (id INTEGER PRIMARY KEY, word TEXT COLLATE NOCASE, phonetic TEXT, translation TEXT, rank INTEGER);
        CREATE VIRTUAL TABLE search USING fts5(terms, content='');
    """)
    count = 0
    with (data / "ecdict.csv").open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if not row["word"] or not row["translation"]:
                continue
            count += 1
            rank = min([int(row[k]) for k in ("frq", "bnc") if row.get(k, "").isdigit() and int(row[k]) > 0] or [999999])
            db.execute("INSERT INTO entries VALUES (?, ?, ?, ?, ?)",
                       (count, row["word"], row["phonetic"], row["translation"], rank))
            db.execute("INSERT INTO search(rowid, terms) VALUES (?, ?)", (count, search_terms(row["translation"])))
    db.execute("CREATE INDEX words ON entries(word)")
    db.execute("INSERT INTO search(search) VALUES ('optimize')")
    db.commit()
    db.close()
    staging.replace(target)
    print(f"Built {count:,} entries: {target} ({target.stat().st_size // 1048576} MiB)")


if __name__ == "__main__":
    main()
