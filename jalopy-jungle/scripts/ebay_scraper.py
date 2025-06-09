import os
import glob
import csv
import time
import random
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# ───── SETTINGS ───────────────────────────────────────────────────────────────

SEARCH_TERMS        = [
    "dash vents", "headlights", "tail lights", "throttle body",
    "intake manifold", "ecu ecm", "gauge cluster", "valve covers"
]
DELAY_SECONDS       = 1             # base delay after each successful request
MAX_ITEMS_PER_QUERY = 5             # cap per term
WORKERS             = 5             # reduced threads to avoid rate-limit
MAX_RETRIES         = 3             # how many times to retry on 429
BACKOFF_FACTOR      = 2             # exponential backoff multiplier

# ───── PATHS & SESSION ────────────────────────────────────────────────────────

script_dir = os.path.dirname(os.path.abspath(__file__))
csv_dir    = os.path.join(script_dir, "..", "inventory-csvs")
out_dir    = os.path.join(script_dir, "..", "ebay-sales")
today_str  = datetime.now().strftime("%Y-%m-%d")

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

os.makedirs(out_dir, exist_ok=True)

# ───── SCRAPER FUNCTION ───────────────────────────────────────────────────────

def scrape_vehicle_term(year, make, model, term, idx, total):
    query = f"{year} {make} {model} {term}"
    url_kw = requests.utils.quote(query)
    url    = (
        "https://www.watchcount.com/"
        f"sold/{url_kw}/-/all"
        "?condition=used&site=EBAY_US&sortBy=bestmatch"
    )

    # Retry loop for status 429 or transient failures
    for attempt in range(1, MAX_RETRIES+1):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 429:
                wait = BACKOFF_FACTOR ** (attempt - 1) + random.random()
                print(f"[{idx}/{total}] {query} → 429, backing off {wait:.1f}s (attempt {attempt})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                print(f"[{idx}/{total}] {query} → failed after {MAX_RETRIES} tries: {e}")
                return []
            # exponential backoff on other errors too
            wait = BACKOFF_FACTOR ** (attempt - 1) + random.random()
            print(f"[{idx}/{total}] {query} → error: {e}. retrying in {wait:.1f}s")
            time.sleep(wait)
    else:
        # never got a successful response
        return []

    soup  = BeautifulSoup(resp.text, "html.parser")
    boxes = soup.select("div.col-auto.normal-text.selling-info-box")[:MAX_ITEMS_PER_QUERY]

    print(f"[{idx}/{total}] {query} → found {len(boxes)} boxes")
    out = []
    for box in boxes:
        total_sold = time_to_sell = last_sold_price = date_sold = title_text = ""

        # parse the spans
        for span in box.find_all("span"):
            txt = span.get_text(strip=True).lower()
            if "total sold" in txt:
                total_sold = span.get_text(strip=True).replace("total sold", "").strip()
            elif "to sell" in txt:
                time_to_sell = span.get_text(strip=True).replace("to sell one", "").strip()

        # last sold price & date
        end_div = box.select_one("div.col.text-lg-end")
        if end_div:
            txt = end_div.get_text(" ", strip=True)
            if "Last sold for" in txt:
                parts = txt.split(" on ")
                last_sold_price = parts[0].replace("Last sold for", "").replace("or Best Offer", "").strip()
                if len(parts) > 1:
                    date_sold = parts[1].strip()

        # listing title
        gin = box.find_previous("div", class_="general-info-container")
        if gin:
            span = gin.select_one("div.row > div.col > span")
            if span:
                title_text = span.get_text(strip=True)

        out.append([
            year, make, model, term,
            total_sold, time_to_sell,
            last_sold_price, date_sold,
            title_text
        ])

    time.sleep(DELAY_SECONDS + random.random())
    return out

# ───── CSV PROCESSOR ──────────────────────────────────────────────────────────

def scrape_csv(csv_path, csv_index, csv_total):
    name = os.path.splitext(os.path.basename(csv_path))[0]
    print(f"\n=== ({csv_index}/{csv_total}) Processing '{name}' ===")

    df   = pd.read_csv(csv_path, dtype=str)
    uniq = df.drop_duplicates(subset=["Year","Make","Model"])
    total_tasks = len(uniq) * len(SEARCH_TERMS)
    print(f"→ {len(uniq)} vehicles, {total_tasks} total queries")

    tasks   = []
    results = []

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        counter = 0
        for _, row in uniq.iterrows():
            y, m, mo = row["Year"].strip(), row["Make"].strip(), row["Model"].strip()
            if not (y and m and mo):
                continue
            for term in SEARCH_TERMS:
                counter += 1
                tasks.append(ex.submit(
                    scrape_vehicle_term, y, m, mo, term, counter, total_tasks
                ))

        completed = 0
        for fut in as_completed(tasks):
            results.extend(fut.result())
            completed += 1
            print(f"Progress: {completed}/{total_tasks}", end="\r")
    print()  # newline

    # dedupe & write out
    seen, uniq_rows = set(), []
    for row in results:
        key = tuple(row)
        if key not in seen:
            seen.add(key)
            uniq_rows.append(row)

    out_file = os.path.join(out_dir, f"{name}_ebay_sales_{today_str}.csv")
    with open(out_file, "w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "Year","Make","Model","Search Term",
            "Total Sold","Time to Sell",
            "Last Sold Price","Date Sold","Listing Title"
        ])
        writer.writerows(uniq_rows)

    print(f"→ Saved {len(uniq_rows)} rows to {out_file}")

# ───── MAIN ────────────────────────────────────────────────────────────────────

def main():
    csvs = [
        f for f in glob.glob(os.path.join(csv_dir, "*.csv"))
        if today_str in os.path.basename(f)
    ]
    if not csvs:
        print("No CSVs for", today_str)
        return

    for idx, path in enumerate(csvs, 1):
        scrape_csv(path, idx, len(csvs))

    print("\nAll done!")

if __name__ == "__main__":
    main()
