import os
import glob
import csv
import time
import random
from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

SEARCH_TERMS = [
    "dash vents", "headlights", "tail lights", "throttle body",
    "intake manifold", "ecu ecm", "gauge cluster", "valve covers"
]
DELAY_SECONDS = 3

script_dir = os.path.dirname(os.path.abspath(__file__))
base_path = os.path.join(script_dir, "..", "ebay-sales")
latest_csv = None

# Match both inventory and vehicles_of_interest CSVs
csv_source_path = os.path.join(script_dir, "..", "inventory-csvs")
csv_files = sorted(
    glob.glob(os.path.join(csv_source_path, "inventory_*.csv")) +
    glob.glob(os.path.join(csv_source_path, "vehicles_of_interest_*.csv")),
    key=os.path.getmtime,
    reverse=True
)

if csv_files:
    latest_csv = csv_files[0]
else:
    print("No inventory CSV files found.")
    exit()

print(f"Using CSV: {latest_csv}")
vehicles_df = pd.read_csv(latest_csv)
output_data = []

# Deduplicate year/make/model combinations
unique_vehicles = vehicles_df.drop_duplicates(subset=["Year", "Make", "Model"])

# Setup Selenium WebDriver with local chromedriver
chrome_path = os.path.join(script_dir, "chromedriver.exe")
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
service = Service(executable_path=chrome_path)
driver = webdriver.Chrome(service=service, options=options)

for _, row in unique_vehicles.iterrows():
    year = str(row.get("Year", "")).strip()
    make = str(row.get("Make", "")).strip()
    model = str(row.get("Model", "")).strip()

    if not (year and make and model):
        continue

    for term in SEARCH_TERMS:
        query = f"{year} {make} {model} {term}"
        url_query = query.replace(" ", "+")
        url = f"https://www.watchcount.com/sold/{url_query}/-/all?condition=used&site=EBAY_US&sortBy=bestmatch"
        print(f"Fetching: {query}")
        print(f"URL: {url}")

        try:
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "selling-info-box"))
            )
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            boxes = soup.select("div.col-auto.normal-text.selling-info-box")
            print(f"Found {len(boxes)} 'selling-info-box' containers")

            for i, box in enumerate(boxes):
                if i >= 5:
                    break

                total_sold = ""
                time_to_sell = ""
                last_sold_price = ""
                date_sold = ""
                title_text = ""

                spans = box.find_all("span")
                for span in spans:
                    text = span.get_text(strip=True)
                    print(f"  Span text: {text}")
                    if "total sold" in text:
                        total_sold = text.replace("total sold", "").strip()
                    elif "to sell" in text:
                        time_to_sell = text.replace("to sell one", "").strip()

                end_text_div = box.select_one("div.col.text-lg-end")
                if end_text_div:
                    last_text = end_text_div.get_text(strip=True)
                    print(f"  End div text: {last_text}")
                    if "Last sold for" in last_text:
                        if " on " in last_text:
                            price_part, date_part = last_text.split(" on ", 1)
                            last_sold_price = price_part.replace("Last sold for ", "").replace("or Best Offer", "").strip()
                            date_sold = date_part.strip()
                        else:
                            last_sold_price = last_text.replace("Last sold for ", "").replace("or Best Offer", "").strip()

                title_container = box.find_previous("div", class_="general-info-container")
                if title_container:
                    span = title_container.select_one("div.row > div.col > span")
                    if span:
                        title_text = span.get_text(strip=True)

                if total_sold or time_to_sell or last_sold_price or date_sold:
                    print(f"  Parsed: {total_sold}, {time_to_sell}, {last_sold_price}, {date_sold}, {title_text}")
                    output_data.append([
                        year, make, model, term,
                        total_sold, time_to_sell, last_sold_price, date_sold, title_text
                    ])
        except Exception as e:
            print(f"Error fetching {query}: {e}")

        time.sleep(DELAY_SECONDS + random.uniform(0.5, 1.5))

# Deduplicate output rows
unique_rows = []
seen = set()
for row in output_data:
    row_key = tuple(row)
    if row_key not in seen:
        seen.add(row_key)
        unique_rows.append(row)

# Save results to CSV
output_filename = f"ebay_sales_{datetime.now().strftime('%Y-%m-%d')}.csv"
output_path = os.path.join(base_path, output_filename)

os.makedirs(base_path, exist_ok=True)
with open(output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Year", "Make", "Model", "Search Term", "Total Sold", "Time to Sell", "Last Sold Price", "Date Sold", "Listing Title"])
    writer.writerows(unique_rows)

print(f"Done! Saved to {output_path}")

# Clean up
driver.quit()
