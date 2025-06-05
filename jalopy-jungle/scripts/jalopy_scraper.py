import http.client
import uuid
import json
import csv
import time
from html.parser import HTMLParser

# ========= VEHICLE INTEREST LIST =========
# Format: ("MAKE", "MODEL", START_YEAR, END_YEAR or None)
VEHICLES_OF_INTEREST = [
    ("FORD", "THUNDERBIRD", 1989, 1997),
    ("FORD", "MUSTANG", 1996, None),
]

# ========= YARD DEFINITIONS =========
YARDS = {
    "1020": "Boise",
    "1021": "Caldwell",
    "1119": "Garden City",
    "1022": "Nampa",
    "1099": "Twin Falls",
}

HOST = "inventory.pickapartjalopyjungle.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest"
}

def is_vehicle_of_interest(year_str, make, model):
    try:
        year = int(year_str)
    except ValueError:
        return "N"
    make = make.upper()
    model = model.upper()

    for interest_make, interest_model, start_year, end_year in VEHICLES_OF_INTEREST:
        if make == interest_make and model == interest_model:
            if end_year is None:
                if year >= start_year:
                    return "Y"
            elif start_year <= year <= end_year:
                return "Y"
    return "N"

class InventoryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_row = False
        self.in_td = False
        self.current_data = []
        self.entries = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.current_data = []
            self.in_row = True
        elif tag == "td" and self.in_row:
            self.in_td = True

    def handle_endtag(self, tag):
        if tag == "td":
            self.in_td = False
        elif tag == "tr":
            if len(self.current_data) == 4:
                self.entries.append(tuple(self.current_data))
            self.in_row = False

    def handle_data(self, data):
        if self.in_td:
            text = data.strip()
            if text:
                self.current_data.append(text)

def post_json(path, payload):
    body = "&".join(f"{k}={v}" for k, v in payload.items())
    headers = HEADERS.copy()
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn = http.client.HTTPSConnection(HOST)
    conn.request("POST", path, body, headers)
    res = conn.getresponse()
    content = res.read().decode("utf-8")
    conn.close()
    return json.loads(content)

def post_inventory(yard_id, make, model):
    boundary = f"----geckoformboundary{uuid.uuid4().hex}"
    delimiter = f"--{boundary}"
    closing = f"--{boundary}--"
    headers = HEADERS.copy()
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    parts = [
        delimiter,
        'Content-Disposition: form-data; name="YardId"\r\n',
        yard_id,
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
    headers["Content-Length"] = str(len(body))

    conn = http.client.HTTPSConnection(HOST)
    conn.request("POST", "/", body, headers)
    res = conn.getresponse()
    html = res.read().decode("utf-8")
    conn.close()
    return html

def main():
    with open("vehicles_of_interest.csv", "w", newline="", encoding="utf-8") as summary_file:
        summary_writer = csv.writer(summary_file)
        summary_writer.writerow(["Location", "Year", "Make", "Model", "Row"])

        for yard_id, location_name in YARDS.items():
            filename = f"inventory_{location_name.lower().replace(' ', '_')}.csv"
            print(f"Processing inventory for {location_name}...")

            try:
                makes = post_json("/Home/GetMakes", {"yardId": yard_id})
                print(f"Found {len(makes)} makes.")

                with open(filename, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Year", "Make", "Model", "Row", "Vehicle of Interest"])

                    for make_obj in makes:
                        make = make_obj["makeName"]
                        print(f"{make}")

                        models = post_json("/Home/GetModels", {"yardId": yard_id, "makeName": make})
                        for model_obj in models:
                            model = model_obj["model"]
                            print(f"  {model}")
                            try:
                                html = post_inventory(yard_id, make, model)
                                parser = InventoryParser()
                                parser.feed(html)

                                for row in parser.entries:
                                    interest = is_vehicle_of_interest(row[0], row[1], row[2])
                                    writer.writerow(list(row) + [interest])

                                    if interest == "Y":
                                        summary_writer.writerow([location_name] + list(row))

                            except Exception as e:
                                print(f"  Error getting {make} {model}: {e}")
                            time.sleep(0.3)

                print(f"Saved to {filename}\n")

            except Exception as e:
                print(f"Error fetching from {location_name}: {e}")

    print("Done! Inventory and summary of vehicles of interest saved.")

# Run the script
if __name__ == "__main__":
    main()
