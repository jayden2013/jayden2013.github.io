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

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
LOC_KEY             = "nampa"
SEARCH_TERMS        = [
    "dash vents", "headlights", "tail lights", "throttle body",
    "intake manifold", "ecu ecm", "gauge cluster", "valve covers"
]
# eBay fee calculation toggle happens in dashboard, not here

DELAY_SECONDS       = 1
MAX_ITEMS_PER_QUERY = 5

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

# ─── PATHS ─────────────────────────────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
INV_DIR     = os.path.join(script_dir, "..", "inventory-csvs")
SALES_DIR   = os.path.join(script_dir, "..", "ebay-sales")
os.makedirs(SALES_DIR, exist_ok=True)

# ─── HELPERS ───────────────────────────────────────────────────────────────────
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
        print(f"[{LOC_KEY}] No previous inventory found, will scrape all vehicles")
    return current, previous

# ─── SCRAPING ─────────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

def scrape_sold(vehicles):
    """Fetch sold data for each (Year,Make,Model) in vehicles DataFrame."""
    results = []
    total = len(vehicles)
    print(f"[{LOC_KEY}] Beginning scrape of {total} vehicles")
    for idx, row in enumerate(vehicles.itertuples(index=False), start=1):
        y, m, mo = row.Year.strip(), row.Make.strip(), row.Model.strip()
        print(f"[{LOC_KEY}] Vehicle {idx}/{total}: {y} {m} {mo}")
        for term in SEARCH_TERMS:
            query = f"{y} {m} {mo} {term}"
            url_kw = requests.utils.quote(query)
            url    = (
                "https://www.watchcount.com/"
                f"sold/{url_kw}/-/all"
                "?condition=used&site=EBAY_US&sortBy=bestmatch"
            )
            try:
                resp = session.get(url, timeout=15)
                resp.raise_for_status()
            except Exception as e:
                print(f"   → term '{term}' error: {e}")
                time.sleep(DELAY_SECONDS + random.random())
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            boxes = soup.select(".selling-info-box")[:MAX_ITEMS_PER_QUERY]
            print(f"   → term '{term}' found {len(boxes)} items")
            for box in boxes:
                total_sold = time_to_sell = last_price = date_sold = title = ""
                for sp in box.find_all("span"):
                    txt = sp.get_text(strip=True).lower()
                    if "total sold" in txt:
                        total_sold = sp.get_text(strip=True)
                    elif "to sell" in txt:
                        time_to_sell = sp.get_text(strip=True)
                ed = box.select_one(".text-lg-end")
                if ed:
                    txt = ed.get_text(" ", strip=True)
                    if "Last sold for" in txt:
                        parts = txt.split(" on ")
                        last_price = parts[0].replace("Last sold for","").replace("or Best Offer","").strip()
                        if len(parts)>1:
                            date_sold = parts[1].strip()
                gi = box.find_previous("div", class_="general-info-container")
                if gi and gi.select_one("div.row > div.col > span"):
                    title = gi.select_one("div.row > div.col > span").get_text(strip=True)
                results.append([y, m, mo, term, total_sold, time_to_sell, last_price, date_sold, title])
            time.sleep(DELAY_SECONDS + random.uniform(0.5,1.5))
    print(f"[{LOC_KEY}] Scraping complete, raw rows: {len(results)}")
    return results

# ─── MAIN LOGIC ───────────────────────────────────────────────────────────────
def main():
    print(f"[{LOC_KEY}] Starting scraper at {NOW_TS}")
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
        print(f"[{LOC_KEY}] No previous run → scraping all {len(new_df)} vehicles")

    # scheduled vehicles this weekday
    weekday = datetime.now().weekday()
    prefixes = REFRESH_MAP.get(weekday, [])
    sched_df = df_curr[df_curr["Make"].str.upper().str[0].isin(prefixes)][["Year","Make","Model"]]
    print(f"[{LOC_KEY}] {len(sched_df)} scheduled vehicles (prefix {prefixes})")

    # combine
    to_scrape = pd.concat([new_df, sched_df], ignore_index=True).drop_duplicates().reset_index(drop=True)
    print(f"[{LOC_KEY}] Total vehicles to scrape: {len(to_scrape)}")

    # scrape
    raw = scrape_sold(to_scrape)

    # dedupe
    seen = set(); uniq = []
    for r in raw:
        key = tuple(r[:3])
        if key not in seen:
            seen.add(key); uniq.append(r)
    print(f"[{LOC_KEY}] Deduplicated to {len(uniq)} rows")

    # combine with previous combined
    combined = []
    header = ["Year","Make","Model","Search Term","Total Sold","Time to Sell",
              "Last Sold Price","Date Sold","Listing Title","Scraped Date"]
    pat = re.compile(rf"^inventory_{re.escape(LOC_KEY)}_.+_ebay_sales_\d{{4}}-\d{{2}}-\d{{2}}\.csv$")
    old_files = sorted(f for f in os.listdir(SALES_DIR) if pat.match(f))
    if old_files:
        last = old_files[-1]
        print(f"[{LOC_KEY}] Loading existing combined: {last}")
        with open(os.path.join(SALES_DIR,last), newline='',encoding='utf-8') as fp:
            rdr = csv.reader(fp); next(rdr)
            skip_keys = set((row.Year,row.Make,row.Model) for row in to_scrape.itertuples(index=False))
            for row in rdr:
                if (row[0],row[1],row[2]) not in skip_keys:
                    combined.append(row)
    else:
        print(f"[{LOC_KEY}] No existing combined CSV")

    # append new
    for r in uniq:
        combined.append(r + [TODAY_DATE])

    # write out
    out_name = f"inventory_{LOC_KEY}_{NOW_TS}_ebay_sales_{TODAY_DATE}.csv"
    print(f"[{LOC_KEY}] Writing {len(combined)} rows to {out_name}")
    with open(os.path.join(SALES_DIR,out_name),"w",newline="",encoding='utf-8') as fp:
        w=csv.writer(fp); w.writerow(header); w.writerows(combined)

    print(f"[{LOC_KEY}] Done.")

if __name__=="__main__":
    main()
