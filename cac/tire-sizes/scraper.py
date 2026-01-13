import argparse
import csv
import json
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests

BASE_URL = "https://www.toyotires.com/tirefinder/SearchByVehicleOptions"

YEARS = [
    2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015, 2014, 2013, 2012,
    2011, 2010, 2009, 2008, 2007, 2006, 2005, 2004, 2003, 2002, 2001, 2000, 1999, 1998, 1997,
    1996, 1995, 1994, 1993, 1992, 1991, 1990, 1989, 1988, 1987, 1986, 1985, 1984, 1983, 1982,
    1981, 1980
]

# Politeness / stability
SLEEP_SEC = 0.25
TIMEOUT_SEC = 30
MAX_RETRIES = 3

OUT_CSV = "toyo_vehicle_fitments.csv"
EXPECTED_CACHE = "toyo_expected_combos.jsonl"  # cache of discovered combos

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CarsAndCollectiblesBot/1.0; +https://www.carsandcollectibles.com/)",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.toyotires.com/tire-finder/vehicle/",
}

session = requests.Session()
session.headers.update(HEADERS)

FIELDNAMES = [
    "year", "make", "model", "trim", "vehicleId", "tireSize",
    "section_width", "aspect_ratio", "rim_size",
    "loadIndex", "speedRating", "stdOrOpt", "tirePosition"
]


def fetch(year: int, make: Optional[str] = None, model: Optional[str] = None) -> Any:
    params: Dict[str, Any] = {"year": year}
    if make is not None:
        params["make"] = make
    if model is not None:
        params["model"] = model

    last_err: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(BASE_URL, params=params, timeout=TIMEOUT_SEC)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(SLEEP_SEC * attempt)
    raise last_err or RuntimeError("Unknown fetch error")


def dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for s in items:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def as_string_list(data: Any) -> List[str]:
    """
    Normalize makes/models responses that may be:
      - ["Ford", "Honda", ...]
      - {"Ford":"Ford", ...}
      - wrappers
    """
    if data is None:
        return []

    if isinstance(data, list):
        out: List[str] = []
        for x in data:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
            elif isinstance(x, dict):
                for k in ("make", "model", "name", "text", "value", "label"):
                    v = x.get(k)
                    if isinstance(v, str) and v.strip():
                        out.append(v.strip())
                        break
        return dedupe_preserve_order(out)

    if isinstance(data, dict):
        # Common for makes/models: {"Ford":"Ford", ...}
        if data and all(isinstance(k, str) for k in data.keys()) and all(isinstance(v, str) for v in data.values()):
            out = [k.strip() for k in data.keys() if k and k.strip()]
            return dedupe_preserve_order(out)

        for k in ("items", "makes", "models", "data", "results", "options"):
            if k in data:
                return as_string_list(data[k])

    return []


def flatten_options(year: int, make: str, model: str, options: Any) -> List[Dict[str, Any]]:
    """
    Expected options shape like:
      { "LX":[{...}], "SE":[{...}] }
    """
    if not isinstance(options, dict):
        return []

    rows: List[Dict[str, Any]] = []
    for trim, items in options.items():
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append({
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "vehicleId": it.get("vehicleId"),
                "tireSize": it.get("tireSize"),
                "section_width": it.get("section_width"),
                "aspect_ratio": it.get("aspect_ratio"),
                "rim_size": it.get("rim_size"),
                "loadIndex": it.get("loadIndex"),
                "speedRating": it.get("speedRating"),
                "stdOrOpt": it.get("stdOrOpt"),
                "tirePosition": it.get("tirePosition"),
            })
    return rows


def discover_expected_combos(force_refresh: bool = False) -> Set[Tuple[int, str, str]]:
    """
    Builds the full set of (year, make, model) combos by walking year->makes->models.
    Caches to jsonl to avoid re-discovering every time.
    """
    if os.path.exists(EXPECTED_CACHE) and not force_refresh:
        combos: Set[Tuple[int, str, str]] = set()
        with open(EXPECTED_CACHE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                combos.add((int(rec["year"]), rec["make"], rec["model"]))
        return combos

    combos = set()
    with open(EXPECTED_CACHE, "w", encoding="utf-8") as fcache:
        for year in YEARS:
            try:
                makes = as_string_list(fetch(year))
            except Exception as e:
                print(f"[WARN] discover makes failed for {year}: {e}")
                continue

            for make in makes:
                time.sleep(SLEEP_SEC)
                try:
                    models = as_string_list(fetch(year, make=make))
                except Exception as e:
                    print(f"[WARN] discover models failed for {year} {make}: {e}")
                    continue

                for model in models:
                    combos.add((year, make, model))
                    fcache.write(json.dumps({"year": year, "make": make, "model": model}, ensure_ascii=False) + "\n")

    return combos


def load_scraped_combos_from_csv(path: str) -> Set[Tuple[int, str, str]]:
    combos: Set[Tuple[int, str, str]] = set()
    if not os.path.exists(path):
        return combos

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            y = row.get("year")
            mk = row.get("make")
            mdl = row.get("model")
            if not y or not mk or not mdl:
                continue
            combos.add((int(y), mk, mdl))
    return combos


def append_rows_to_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    file_exists = os.path.exists(path)
    with open(path, "a" if file_exists else "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def scrape_all() -> None:
    # Basic full scrape (no auditing) – still writes incrementally
    file_exists = os.path.exists(OUT_CSV)
    if not file_exists:
        append_rows_to_csv(OUT_CSV, [])  # creates file + header

    combos_processed = 0
    rows_written = 0

    for year in YEARS:
        try:
            makes = as_string_list(fetch(year))
        except Exception as e:
            print(f"[WARN] {year}: makes failed: {e}")
            continue

        for make in makes:
            time.sleep(SLEEP_SEC)
            try:
                models = as_string_list(fetch(year, make=make))
            except Exception as e:
                print(f"[WARN] {year} {make}: models failed: {e}")
                continue

            for model in models:
                time.sleep(SLEEP_SEC)
                try:
                    options = fetch(year, make=make, model=model)
                except Exception as e:
                    print(f"[WARN] {year} {make} {model}: options failed: {e}")
                    continue

                rows = flatten_options(year, make, model, options)
                if rows:
                    append_rows_to_csv(OUT_CSV, rows)
                    rows_written += len(rows)
                combos_processed += 1

                if combos_processed % 200 == 0:
                    print(f"[PROGRESS] combos={combos_processed:,} rows={rows_written:,}")

    print(f"[DONE] combos={combos_processed:,} rows={rows_written:,} -> {OUT_CSV}")


def audit_and_backfill(force_refresh_expected: bool, do_backfill: bool) -> None:
    expected = discover_expected_combos(force_refresh=force_refresh_expected)
    scraped = load_scraped_combos_from_csv(OUT_CSV)

    missing = expected - scraped
    extra = scraped - expected  # usually empty; can happen if expected cache was built at different time

    print(f"[AUDIT] expected combos: {len(expected):,}")
    print(f"[AUDIT] scraped combos:  {len(scraped):,}")
    print(f"[AUDIT] missing combos:  {len(missing):,}")
    if extra:
        print(f"[AUDIT] extra combos in CSV not in expected cache: {len(extra):,} (likely cache staleness)")

    # Show a few missing examples
    for i, (y, mk, mdl) in enumerate(sorted(missing)[:20], start=1):
        print(f"  missing {i:02d}: {y} | {mk} | {mdl}")

    if not do_backfill or not missing:
        return

    rows_written = 0
    combos_filled = 0

    for (year, make, model) in sorted(missing):
        time.sleep(SLEEP_SEC)
        try:
            options = fetch(year, make=make, model=model)
        except Exception as e:
            print(f"[WARN] backfill failed {year} {make} {model}: {e}")
            continue

        rows = flatten_options(year, make, model, options)
        if rows:
            append_rows_to_csv(OUT_CSV, rows)
            rows_written += len(rows)

        combos_filled += 1
        if combos_filled % 200 == 0:
            print(f"[BACKFILL] filled combos={combos_filled:,}/{len(missing):,} rows_written={rows_written:,}")

    print(f"[BACKFILL DONE] filled combos={combos_filled:,} rows_written={rows_written:,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["scrape", "audit", "backfill"], default="audit",
                    help="scrape=full run, audit=report missing, backfill=fill missing")
    ap.add_argument("--refresh-expected", action="store_true",
                    help="rebuild expected combo cache by rediscovering makes/models (slower)")
    args = ap.parse_args()

    if args.mode == "scrape":
        scrape_all()
    elif args.mode == "audit":
        audit_and_backfill(force_refresh_expected=args.refresh_expected, do_backfill=False)
    else:  # backfill
        audit_and_backfill(force_refresh_expected=args.refresh_expected, do_backfill=True)


if __name__ == "__main__":
    main()
