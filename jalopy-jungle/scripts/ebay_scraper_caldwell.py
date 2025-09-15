#!/usr/bin/env python3
import os
import glob
import csv
import time
import random
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import quote_plus

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
LOC_KEY             = "caldwell"
SEARCH_TERMS        = [
    "dash vents", "headlights", "tail lights", "throttle body",
    "intake manifold", "ecu ecm", "gauge cluster", "valve covers"
]

# Polite pacing (tune if needed)
MIN_GAP_PER_HOST    = 12.0  # minimum seconds between any two requests to the same host
DELAY_BETWEEN_TERMS = (6.0, 10.0)  # random sleep range after each term
DELAY_BETWEEN_VEHS  = (10.0, 18.0) # random sleep range after each vehicle
MAX_ITEMS_PER_QUERY = 5
MAX_RETRIES         = 5       # per URL
BACKOFF_START       = 15.0    # seconds
BACKOFF_CAP         = 600.0   # seconds

# Monday=0: A,B,C; Tuesday=1: D,E,F; Wednesday=2: G,H,I,J
# Thursday=3: K,L,M,N; Friday=4: O,P,Q,R; Saturday=5: S,T,U,V; Sunday=6: W,X,Y,Z
REFRESH_MAP = {
    0: list("ABC"),
    1: list("DEF"),
    2: list("GHIJ"),
    3: list("KLMN"),
    4: list("OPQR"),
    5: list("STUV"),
    6: list("WXYZ"),
}

TODAY_DATE = datetime.now().strftime("%Y-%m-%d")
NOW_TS     = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# ─── PATHS ────────────────────────────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
INV_DIR     = os.path.join(script_dir, "..", "inventory-csvs")
SALES_DIR   = os.path.join(script_dir, "..", "ebay-sales")
os.makedirs(SALES_DIR, exist_ok=True)

# ─── USER-AGENT POOL (rotate per run) ─────────────────────────────────────────
UA_POOL = [
    # rotate once per run; do NOT rotate every request (spiky signature)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

# ─── SESSION & PER-HOST PACING ────────────────────────────────────────────────
session = requests.Session()
session.headers.update({
    "User-Agent": random.choice(UA_POOL),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "close",
})
_HOST_NEXT_ALLOWED = {}

def _host_from_url(url: str) -> str:
    # crude but fine: https://www.ebay.com/...
    try:
        return url.split("/")[2].lower()
    except Exception:
        return "unknown"

def _sleep_until_allowed(host: str, min_gap: float = MIN_GAP_PER_HOST):
    now = time.time()
    next_ok = _HOST_NEXT_ALLOWED.get(host, 0.0)
    if now < next_ok:
        time.sleep(next_ok - now)
    # set next allowed time with a little jitter (±20%)
    jitter = random.uniform(0.8, 1.2)
    _HOST_NEXT_ALLOWED[host] = time.time() + min_gap * jitter

def _polite_get(url: str, timeout: int = 30) -> requests.Response:
    host = _host_from_url(url)
    backoff = BACKOFF_START
    for attempt in range(1, MAX_RETRIES + 1):
        _sleep_until_allowed(host)
        try:
            resp = session.get(url, timeout=timeout)
        except requests.RequestException as e:
            if attempt >= MAX_RETRIES:
                raise
            wait = backoff
            print(f"      · Network error: {e} → sleeping {wait:.1f}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            backoff = min(backoff * 2, BACKOFF_CAP)
            continue

        if resp.status_code == 429 or (500 <= resp.status_code < 600):
            if attempt >= MAX_RETRIES:
                resp.raise_for_status()
            # Respect Retry-After header if present
            ra = resp.headers.get("Retry-After")
            try:
                wait = float(ra) if ra else backoff
            except Exception:
                wait = backoff
            print(f"      · HTTP {resp.status_code} → sleeping {wait:.1f}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            backoff = min(backoff * 2, BACKOFF_CAP)
            continue

        # Light post-success pause to avoid clock-like cadence
        time.sleep(random.uniform(1.2, 2.0))
        return resp

    # Should not reach here due to raises above
    return resp

# ─── INVENTORY HELPERS ────────────────────────────────────────────────────────
def pick_inventory_files():
    """Return (current_csv, previous_csv_or_None) for this location."""
    pattern = re.compile(
        rf"inventory_{re.escape(LOC_KEY)}_(\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}-\d{{2}})\.csv$"
    )
    candidates = []
    for path in glob.glob(os.path.join(INV_DIR, f"inventory_{LOC_KEY}_*.csv")):
        m = pattern.match(os.path.basename(path))
        if m:
            candidates.append((m.group(1), path))
    candidates.sort(key=lambda x: x[0])
    print(f"[{LOC_KEY}] Found inventory files (sorted): {[p for _, p in candidates]}")
    if not candidates:
        raise FileNotFoundError(f"No inventory files for {LOC_KEY}")
    current = candidates[-1][1]
    previous = candidates[-2][1] if len(candidates) > 1 else None
    print(f"[{LOC_KEY}] Using current inventory: {current}")
    if previous:
        print(f"[{LOC_KEY}] Previous inventory: {previous}")
    else:
        print(f"[{LOC_KEY}] No previous inventory found, will fetch all vehicles")
    return current, previous

# ─── EBAY SOLD SEARCH (WEB) ───────────────────────────────────────────────────
def build_ebay_sold_url(query: str) -> str:
    # Sold + Completed; rt=nc (no cache redirect); &_ipg=240 could increase items per page (risky).
    # Keep defaults (safer); exact params can change, so keep minimal.
    q = quote_plus(query)
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1&rt=nc"

PRICE_RE = re.compile(r"\$?\s*([\d{1,3}(?:,\d{3})*]+(?:\.\d{2})?)")  # fallback price parse
DATE_RE  = re.compile(r"(Sold|ENDED)\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", re.IGNORECASE)

def parse_sold_results(html: str):
    """
    Parse eBay sold search results page.
    Returns list of dicts: {"title":..., "price":..., "date":...}
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Primary layout: <li class="s-item"> blocks
    for li in soup.select("li.s-item")[:MAX_ITEMS_PER_QUERY]:
        title = ""
        price = ""
        date  = ""

        # Title
        t = li.select_one(".s-item__title")
        if t:
            tt = t.get_text(" ", strip=True)
            # some entries have "Shop on eBay" placeholders—skip those
            if "Shop on eBay" in tt or not tt:
                continue
            title = tt

        # Price (sold price often in .s-item__price)
        p = li.select_one(".s-item__price")
        if p:
            price_text = p.get_text(" ", strip=True)
            price = price_text
        else:
            # fallback: look for any element with price pattern
            txt = li.get_text(" ", strip=True)
            m = PRICE_RE.search(txt.replace(",", ""))
            if m:
                price = m.group(1)

        # Date (often in .s-item__caption: "Sold Aug 23, 2025")
        cap = li.select_one(".s-item__caption, .s-item__endedDate")
        cap_text = cap.get_text(" ", strip=True) if cap else li.get_text(" ", strip=True)
        md = DATE_RE.search(cap_text)
        if md:
            date = md.group(2)

        if title or price or date:
            items.append({"title": title, "price": price, "date": date})

    return items

def fetch_sold_for_query(query: str):
    url = build_ebay_sold_url(query)
    try:
        resp = _polite_get(url, timeout=30)
        resp.raise_for_status()
        return parse_sold_results(resp.text)
    except Exception as e:
        print(f"      · fetch error: {e}")
        return []

# ─── FETCH LOOP (REPLACES WATCHCOUNT) ─────────────────────────────────────────
def fetch_sold_data(vehicles: pd.DataFrame):
    """
    For each (Year, Make, Model) and each SEARCH_TERM, query eBay sold/completed (web).
    Returns rows shaped like your original CSV header.
    """
    results = []
    total = len(vehicles)
    print(f"[{LOC_KEY}] Beginning eBay SOLD fetch for {total} vehicles")

    for idx, row in enumerate(vehicles.itertuples(index=False), start=1):
        y, m, mo = row.Year.strip(), row.Make.strip(), row.Model.strip()
        print(f"[{LOC_KEY}] Vehicle {idx}/{total}: {y} {m} {mo}")

        for term in SEARCH_TERMS:
            query = f"{y} {m} {mo} {term}"
            items = fetch_sold_for_query(query)
            print(f"   → term '{term}' found {len(items)} items")

            for it in items[:MAX_ITEMS_PER_QUERY]:
                title = it.get("title", "")
                price = it.get("price", "")
                date  = it.get("date", "")
                # Map into your schema:
                # ["Year","Make","Model","Search Term","Total Sold","Time to Sell",
                #  "Last Sold Price","Date Sold","Listing Title","Scraped Date"]
                results.append([
                    y, m, mo, term,
                    "",      # Total Sold (unknown)
                    "",      # Time to Sell (unknown)
                    price,   # Sold price
                    date,    # Date Sold (best-effort parse)
                    title,   # Listing Title
                ])

            # gentle pause between terms
            time.sleep(random.uniform(*DELAY_BETWEEN_TERMS))

        # bigger pause between vehicles
        time.sleep(random.uniform(*DELAY_BETWEEN_VEHS))

    print(f"[{LOC_KEY}] SOLD fetch complete, raw rows: {len(results)}")
    return results

# ─── MAIN LOGIC ───────────────────────────────────────────────────────────────
def main():
    print(f"[{LOC_KEY}] Starting eBay SOLD scrape at {NOW_TS}")
    current_csv, prev_csv = pick_inventory_files()

    # load current inventory
    df_curr = (
        pd.read_csv(current_csv, dtype=str)
          .dropna(subset=["Year","Make","Model"])
          .drop_duplicates(subset=["Year","Make","Model"])
    )

    # new vehicles
    if prev_csv:
        df_prev = (
            pd.read_csv(prev_csv, dtype=str)
              .dropna(subset=["Year","Make","Model"])
              .drop_duplicates(subset=["Year","Make","Model"])
        )
        merged = df_curr.merge(df_prev,on=["Year","Make","Model"],how="left",indicator=True)
        new_df = merged[merged["_merge"]=="left_only"][["Year","Make","Model"]]
        print(f"[{LOC_KEY}] {len(new_df)} new vehicles since last run")
    else:
        new_df = df_curr[["Year","Make","Model"]]
        print(f"[{LOC_KEY}] No previous run → fetching all {len(new_df)} vehicles")

    # scheduled vehicles this weekday
    weekday = datetime.now().weekday()
    prefixes = REFRESH_MAP.get(weekday, [])
    sched_df = df_curr[df_curr["Make"].str.upper().str[0].isin(prefixes)][["Year","Make","Model"]]
    print(f"[{LOC_KEY}] {len(sched_df)} scheduled vehicles (prefix {prefixes})")

    # combine queues
    to_fetch = pd.concat([new_df, sched_df], ignore_index=True).drop_duplicates().reset_index(drop=True)
    print(f"[{LOC_KEY}] Total vehicles to fetch: {len(to_fetch)}")

    # fetch sold data
    raw = fetch_sold_data(to_fetch)

    # If nothing fetched, keep old combined CSVs (fail-safe)
    if not raw:
        print(f"[{LOC_KEY}] No data fetched; skipping CSV replacement to preserve previous data.")
        return

    # dedupe by (Year,Make,Model) like before (keeps first per vehicle)
    seen = set(); uniq = []
    for r in raw:
        key = tuple(r[:3])
        if key not in seen:
            seen.add(key); uniq.append(r)
    print(f"[{LOC_KEY}] Deduplicated to {len(uniq)} rows")

    # Load previous combined (to keep rows for vehicles not refreshed this run)
    combined = []
    header = ["Year","Make","Model","Search Term","Total Sold","Time to Sell",
              "Last Sold Price","Date Sold","Listing Title","Scraped Date"]

    pat = re.compile(rf"^inventory_{re.escape(LOC_KEY)}_.+_ebay_sales_\d{{4}}-\d{{2}}-\d{{2}}\.csv$")
    old_files = sorted(f for f in os.listdir(SALES_DIR) if pat.match(f))
    if old_files:
        last = old_files[-1]
        print(f"[{LOC_KEY}] Loading existing combined: {last}")
        with open(os.path.join(SALES_DIR, last), newline='', encoding='utf-8') as fp:
            rdr = csv.reader(fp); next(rdr, None)
            skip_keys = set((row.Year,row.Make,row.Model) for row in to_fetch.itertuples(index=False))
            for row in rdr:
                if (row[0], row[1], row[2]) not in skip_keys:
                    combined.append(row)
    else:
        print(f"[{LOC_KEY}] No existing combined CSV")

    # Append new (deduped) rows
    for r in uniq:
        combined.append(r + [TODAY_DATE])

    # Write new combined CSV
    out_name = f"inventory_{LOC_KEY}_{NOW_TS}_ebay_sales_{TODAY_DATE}.csv"
    out_path = os.path.join(SALES_DIR, out_name)
    print(f"[{LOC_KEY}] Writing {len(combined)} rows to {out_name}")
    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp); w.writerow(header); w.writerows(combined)

    # Remove old sales CSVs to avoid repo bloat (keep only the one we just wrote)
    removed = 0
    for fname in old_files:
        fpath = os.path.join(SALES_DIR, fname)
        if os.path.abspath(fpath) != os.path.abspath(out_path):
            try:
                os.remove(fpath)
                removed += 1
            except Exception as e:
                print(f"[{LOC_KEY}] Warning: failed to delete {fname}: {e}")
    print(f"[{LOC_KEY}] Cleanup complete. Removed {removed} old sales CSV(s).")

    print(f"[{LOC_KEY}] Done.")

if __name__=="__main__":
    main()
