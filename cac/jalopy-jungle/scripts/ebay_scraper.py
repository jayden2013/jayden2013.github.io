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

# ───── SETTINGS ───────────────────────────────────────────────────────────────
SEARCH_TERMS        = [
    "dash vents", "headlights", "tail lights", "throttle body",
    "intake manifold", "ecu ecm", "gauge cluster", "valve covers"
]
DELAY_SECONDS       = 1
MAX_ITEMS_PER_QUERY = 5

# Which makes to refresh each weekday
REFRESH_MAP = {
    0: list("ABC"),    # Monday
    1: list("DEF"),    # Tuesday
    2: list("GHIJ"),   # Wednesday
    3: list("KLMN"),   # Thursday
    4: list("OPQR"),   # Friday
    5: list("STUV"),   # Saturday
    6: list("WXYZ"),   # Sunday
}

# ───── PATHS & TIMESTAMPS ─────────────────────────────────────────────────────
script_dir    = os.path.dirname(os.path.abspath(__file__))
inventory_dir = os.path.join(script_dir, "..", "inventory-csvs")
output_dir    = os.path.join(script_dir, "..", "ebay-sales")
os.makedirs(output_dir, exist_ok=True)

TODAY_DATE = datetime.now().strftime("%Y-%m-%d")
NOW_TS     = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# ───── DISCOVER & GROUP INVENTORY FILES ───────────────────────────────────────
inv_pattern = re.compile(
    r"inventory_(.+?)_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.csv$"
)
inventory_map = {}
for path in glob.glob(os.path.join(inventory_dir, "inventory_*.csv")):
    fn = os.path.basename(path)
    m = inv_pattern.match(fn)
    if not m:
        continue
    locKey, dt = m.group(1), m.group(2)
    inventory_map.setdefault(locKey, []).append((dt, path))
for loc in inventory_map:
    inventory_map[loc].sort(key=lambda x: x[0])

# ───── HTTP SESSION ───────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# ───── SCRAPER & COMBINER ─────────────────────────────────────────────────────
def scrape_for_location(locKey, current_path, prev_path=None):
    print(f"\n>> Processing location '{locKey}'")

    # Load and dedupe current inventory
    curr_df = (
        pd.read_csv(current_path, dtype=str)
          .dropna(subset=["Year","Make","Model"])
          .drop_duplicates(subset=["Year","Make","Model"])
    )

    # 1) New vehicles since last run
    if prev_path:
        prev_df = (
            pd.read_csv(prev_path, dtype=str)
              .dropna(subset=["Year","Make","Model"])
              .drop_duplicates(subset=["Year","Make","Model"])
        )
        merged = curr_df.merge(prev_df, on=["Year","Make","Model"],
                               how="left", indicator=True)
        new_df = merged[merged["_merge"] == "left_only"][["Year","Make","Model"]]
        print(f"   {len(curr_df)} total, {len(new_df)} new since last run")
    else:
        new_df = curr_df[["Year","Make","Model"]]
        print(f"   No previous – scraping all {len(new_df)} vehicles")

    # 2) Scheduled refresh by make initial
    weekday = datetime.now().weekday()
    prefixes = REFRESH_MAP.get(weekday, [])
    sched_df = curr_df[
        curr_df["Make"].str.upper().str[0].isin(prefixes)
    ][["Year","Make","Model"]]
    print(f"   {len(sched_df)} scheduled ({','.join(prefixes)}) vehicles to refresh")

    # 3) Combine & dedupe both sets
    to_scrape = pd.concat([new_df, sched_df]).drop_duplicates().reset_index(drop=True)
    total = len(to_scrape)
    print(f"   Total to scrape this run: {total}")

    # 4) Scrape sold data
    scraped = []
    for i, (_, row) in enumerate(to_scrape.iterrows(), start=1):
        year, make, model = row["Year"].strip(), row["Make"].strip(), row["Model"].strip()
        print(f"    Vehicle {i}/{total} ({total - i} left): {year} {make} {model}")
        for term in SEARCH_TERMS:
            query = f"{year} {make} {model} {term}"
            url_kw = requests.utils.quote(query)
            url = (
                "https://www.watchcount.com/"
                f"sold/{url_kw}/-/all"
                "?condition=used&site=EBAY_US&sortBy=bestmatch"
            )
            try:
                resp = session.get(url, timeout=15)
                resp.raise_for_status()
            except Exception as e:
                print(f"      → Request error: {e}")
                time.sleep(DELAY_SECONDS + random.random())
                continue

            soup  = BeautifulSoup(resp.text, "html.parser")
            boxes = soup.select("div.col-auto.normal-text.selling-info-box")[:MAX_ITEMS_PER_QUERY]
            for box in boxes:
                total_sold = time_to_sell = last_price = date_sold = title = ""
                for span in box.find_all("span"):
                    txt = span.get_text(strip=True).lower()
                    if "total sold" in txt:
                        total_sold = span.get_text(strip=True).replace("total sold","").strip()
                    elif "to sell" in txt:
                        time_to_sell = span.get_text(strip=True).replace("to sell one","").strip()
                end_div = box.select_one("div.col.text-lg-end")
                if end_div:
                    txt = end_div.get_text(" ", strip=True)
                    if "Last sold for" in txt:
                        parts = txt.split(" on ")
                        last_price = parts[0].replace("Last sold for","").replace("or Best Offer","").strip()
                        if len(parts) > 1:
                            date_sold = parts[1].strip()
                gin = box.find_previous("div", class_="general-info-container")
                if gin:
                    sp = gin.select_one("div.row > div.col > span")
                    if sp:
                        title = sp.get_text(strip=True)
                scraped.append([
                    year, make, model, term,
                    total_sold, time_to_sell,
                    last_price, date_sold,
                    title
                ])
            time.sleep(DELAY_SECONDS + random.uniform(0.5, 1.5))

    # Deduplicate scraped rows
    seen = set()
    uniq_scraped = []
    for r in scraped:
        key = tuple(r)
        if key not in seen:
            seen.add(key)
            uniq_scraped.append(r)

    # ── COMBINE with previous combined CSV, replacing scraped vehicles ──────────
    combined = []
    header = [
        "Year","Make","Model","Search Term",
        "Total Sold","Time to Sell","Last Sold Price",
        "Date Sold","Listing Title","Scraped Date"
    ]
    replace_keys = {
        (row.Year, row.Make, row.Model)
        for _, row in to_scrape.iterrows()
    }

    combined_pattern = re.compile(
        rf"^inventory_{re.escape(locKey)}_.+_ebay_sales_\d{{4}}-\d{{2}}-\d{{2}}\.csv$"
    )
    all_combined = [
        f for f in os.listdir(output_dir)
        if combined_pattern.match(f)
    ]
    if all_combined:
        all_combined.sort()
        prev_combined = all_combined[-1]
        print(f"   Loading previous combined: {prev_combined}")
        with open(os.path.join(output_dir, prev_combined), newline='', encoding='utf-8') as fp:
            reader = csv.reader(fp)
            next(reader, None)
            for row in reader:
                key = (row[0], row[1], row[2])
                if key not in replace_keys:
                    combined.append(row)

    # Append today’s newly scraped rows
    for row in uniq_scraped:
        combined.append(row + [TODAY_DATE])

    # Write out one combined CSV with timestamp
    out_name = f"inventory_{locKey}_{NOW_TS}_ebay_sales_{TODAY_DATE}.csv"
    out_path = os.path.join(output_dir, out_name)
    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(header)
        writer.writerows(combined)

    print(f"  → Saved {len(combined)} total rows to {out_name}")


# ───── MAIN ───────────────────────────────────────────────────────────────────
def main():
    for locKey, arr in inventory_map.items():
        if not arr:
            continue
        current_fp = arr[-1][1]
        prev_fp    = arr[-2][1] if len(arr) >= 2 else None
        scrape_for_location(locKey, current_fp, prev_fp)
    print("\nAll done!")

if __name__ == "__main__":
    main()
