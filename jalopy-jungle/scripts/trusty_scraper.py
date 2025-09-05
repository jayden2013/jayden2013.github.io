import http.client
import uuid
import csv
import time
from html.parser import HTMLParser
from datetime import datetime

HOST = "inventory.trustypickapart.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest"
}

# ========= Timestamp for filename =========
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
CSV_FILENAME = f"inventory_trusty_{timestamp}.csv"


# ---------------------------
# Parsers for <select> & rows
# ---------------------------
class SelectOptionsParser(HTMLParser):
    """
    Generic parser to pull <option> text out of a given <select name="...">.
    Designed for both VehicleMake and VehicleModel.
    """
    def __init__(self, select_name):
        super().__init__()
        self.select_name = select_name
        self.in_target_select = False
        self.in_option = False
        self.options = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "select":
            name = dict(attrs).get("name") or dict(attrs).get("id") or ""
            if name == self.select_name:
                self.in_target_select = True
        elif tag.lower() == "option" and self.in_target_select:
            self.in_option = True

    def handle_endtag(self, tag):
        if tag.lower() == "option" and self.in_option:
            self.in_option = False
        elif tag.lower() == "select" and self.in_target_select:
            self.in_target_select = False

    def handle_data(self, data):
        if self.in_option and self.in_target_select:
            text = data.strip()
            if text:
                self.options.append(text)


class InventoryRowsParser(HTMLParser):
    """
    Parses search results table rows. We assume rows with exactly 4 TDs:
    Year, Make, Model, Row (same as the Jalopy CSV format you use).
    """
    def __init__(self):
        super().__init__()
        self.in_tr = False
        self.in_td = False
        self.curr = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "tr":
            self.in_tr = True
            self.curr = []
        elif tag.lower() == "td" and self.in_tr:
            self.in_td = True

    def handle_endtag(self, tag):
        if tag.lower() == "td":
            self.in_td = False
        elif tag.lower() == "tr":
            if len(self.curr) == 4:
                self.rows.append(tuple(self.curr))
            self.in_tr = False

    def handle_data(self, data):
        if self.in_td and self.in_tr:
            text = data.strip()
            if text:
                self.curr.append(text)


# ---------------------------
# HTTP helpers
# ---------------------------
def https_get(path="/"):
    conn = http.client.HTTPSConnection(HOST, timeout=30)
    conn.request("GET", path, headers=HEADERS)
    res = conn.getresponse()
    html = res.read().decode("utf-8", errors="replace")
    conn.close()
    return html


def post_inventory(make="", model=""):
    """
    Replays the same multipart/form-data structure the site sends:
      name="VehicleMake"
      name="VehicleModel"
    """
    boundary = f"----geckoformboundary{uuid.uuid4().hex}"
    delimiter = f"--{boundary}"
    closing = f"--{boundary}--"

    parts = [
        delimiter,
        'Content-Disposition: form-data; name="VehicleMake"\r\n',
        make,
        delimiter,
        'Content-Disposition: form-data; name="VehicleModel"\r\n',
        model,
        closing,
        ''
    ]
    body = "\r\n".join(parts).encode("utf-8")

    headers = HEADERS.copy()
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    headers["Content-Length"] = str(len(body))

    conn = http.client.HTTPSConnection(HOST, timeout=60)
    conn.request("POST", "/", body, headers)
    res = conn.getresponse()
    html = res.read().decode("utf-8", errors="replace")
    conn.close()
    return html


# ---------------------------
# Scrape flow
# ---------------------------
def parse_makes_from_homepage():
    html = https_get("/")  # homepage has the form with selects
    p = SelectOptionsParser("VehicleMake")
    p.feed(html)

    # Filter out placeholders like "Make", "All", etc.
    makes = [m for m in (p.options or []) if m and m.lower() not in {"make", "select make", "all"}]
    # De-dup & stable order
    seen = set()
    ordered = []
    for m in makes:
        if m not in seen:
            ordered.append(m)
            seen.add(m)
    return ordered


def parse_models_from_html(html):
    p = SelectOptionsParser("VehicleModel")
    p.feed(html)
    models = [m for m in (p.options or []) if m and m.lower() not in {"model", "select model", "all"}]
    # unique preserve order
    seen = set()
    out = []
    for m in models:
        if m not in seen:
            out.append(m)
            seen.add(m)
    return out


def extract_rows(html):
    p = InventoryRowsParser()
    p.feed(html)
    return p.rows


def main():
    print("Processing Trusty Pick-A-Part inventory...")

    # 1) Pull makes from homepage select
    try:
        makes = parse_makes_from_homepage()
        if not makes:
            print("No makes found on homepage — the form may have changed.")
    except Exception as e:
        print(f"Error loading homepage/makes: {e}")
        makes = []

    total_rows = 0

    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Year", "Make", "Model", "Row"])

        # 2) For each make, do a POST with only the make first (model empty)
        #    Some sites return results for all models; if not, we then discover models
        for make in makes:
            try:
                print(f"{make}")
                html = post_inventory(make=make, model="")
                rows = extract_rows(html)
                if rows:
                    for r in rows:
                        writer.writerow(list(r))
                    total_rows += len(rows)

                # 3) Try to parse models from the returned HTML (often the Model select is populated after choosing a make)
                models = parse_models_from_html(html)

                # If nothing came back above and we found models, iterate models:
                if models:
                    for model in models:
                        try:
                            # skip model if blank-ish
                            if not model.strip():
                                continue
                            html2 = post_inventory(make=make, model=model)
                            rows2 = extract_rows(html2)
                            if rows2:
                                for r in rows2:
                                    writer.writerow(list(r))
                                total_rows += len(rows2)
                            time.sleep(0.2)
                        except Exception as sub_e:
                            print(f"  Error getting {make} {model}: {sub_e}")
                            time.sleep(0.2)
                else:
                    # If there were no models parsed, we already captured whatever the site returns for just the make.
                    pass

                time.sleep(0.25)

            except Exception as e:
                print(f"Error fetching for make {make}: {e}")
                time.sleep(0.25)

    print(f"Saved to {CSV_FILENAME} with {total_rows} rows.\nDone! Inventory saved.")


if __name__ == "__main__":
    main()
