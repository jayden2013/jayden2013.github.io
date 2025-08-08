import csv
import re
import requests
from datetime import datetime
from collections import defaultdict
from github import Github
import os
import sys

# Force stdout flush for GitHub Actions logs
sys.stdout.reconfigure(line_buffering=True)

# Load Resend API key and GitHub token
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
GITHUB_TOKEN = os.getenv("GH_ALERT_TOKEN")
REPO_NAME = "jayden2013/jayden2013.github.io"
ALERT_LABEL = "alert"

# Resolve the CSV directory relative to this script file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "inventory-csvs"))

# 1. Get the two most recent CSVs per yard
def list_inventory_files():
    print("Listing inventory files...")
    files = os.listdir(CSV_DIR)
    yard_files = defaultdict(list)
    for file in files:
        match = re.match(r"inventory_(.+?)_(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})\.csv", file)
        if match:
            yard = match.group(1)
            timestamp = datetime.strptime(match.group(2), "%Y-%m-%d-%H-%M-%S")
            yard_files[yard].append((timestamp, file))
    for yard in yard_files:
        yard_files[yard] = sorted(yard_files[yard], reverse=True)[:2]
    print(f"Yard files found: {dict(yard_files)}")
    return yard_files

# 2. Load CSV rows
def load_csv(filepath):
    print(f"Loading CSV: {filepath}")
    with open(os.path.join(CSV_DIR, filepath), newline="") as f:
        data = list(csv.DictReader(f))
        print(f"Loaded {len(data)} rows from {filepath}")
        return data

# 3. Compare latest vs previous
def get_new_vehicles(old, new):
    print("Comparing CSVs for new vehicles...")
    old_set = {tuple(row.items()) for row in old}
    new_rows = [row for row in new if tuple(row.items()) not in old_set]
    print(f"New vehicles found: {new_rows}")
    return new_rows

# 4. Get open alerts from GitHub Issues
def get_alerts():
    print("Fetching alerts from GitHub Issues...")
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    alerts = []
    for issue in repo.get_issues(state="open", labels=[ALERT_LABEL]):
        body = issue.body or ""
        email = re.search(r"### Email to notify\n(.*?)\n", body)
        makes = re.search(r"### Make\(s\)\n(.*?)\n", body)
        models = re.search(r"### Model\(s\)\n(.*?)\n", body)
        years = re.search(r"### Year range\n(.*?)\n", body)
        if email and makes and models and years:
            alert = {
                "email": email.group(1).strip(),
                "makes": [m.strip().lower() for m in makes.group(1).split(",")],
                "models": [m.strip().lower() for m in models.group(1).split(",")],
                "years": [int(y) for y in re.findall(r"\d{4}", years.group(1))],
            }
            print(f"Loaded alert: {alert}")
            alerts.append(alert)
        else:
            print(f"Skipping malformed alert: {body}")
    print(f"Loaded {len(alerts)} alerts from GitHub")
    return alerts

# 5. Match and email alerts
def matches_alert(vehicle, alert):
    try:
        year = int(vehicle["year"].strip())
        make = vehicle["make"].strip().lower()
        model = vehicle["model"].strip().lower()
        result = (
            year in alert["years"] and
            make in alert["makes"] and
            model in alert["models"]
        )
        print(f"    Match result: {result} for year={year}, make={make}, model={model}")
        return result
    except Exception as e:
        print(f"Matching error: {e}")
        return False

def send_email(to, vehicle):
    print(f"Sending match email to {to} for {vehicle}")
    requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from": "alerts@carsandcollectibles.com",
            "to": to,
            "subject": f"New {vehicle['year']} {vehicle['make']} {vehicle['model']} found!",
            "text": f"A matching vehicle was found at row {vehicle['row']} in Jalopy Jungle."
        }
    )

def send_no_matches_email(to):
    print(f"Sending no-match email to {to}")
    requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from": "alerts@carsandcollectibles.com",
            "to": to,
            "subject": "No matching vehicles found today",
            "text": "We didn’t find any new vehicles that match your alert criteria today. We’ll keep checking each day!"
        }
    )

# Main execution
def main():
    yard_files = list_inventory_files()
    alerts = get_alerts()
    matched_alerts = set()

    for yard, files in yard_files.items():
        if len(files) < 2:
            print(f"Skipping yard {yard}: not enough files")
            continue
        _, latest = files[0]
        _, previous = files[1]
        print(f"Comparing files for {yard}:")
        print(f"  New: {latest}")
        print(f"  Old: {previous}")
        latest_data = load_csv(latest)
        previous_data = load_csv(previous)

        # Dump CSV content for debugging
        print("Latest CSV content:")
        for row in latest_data:
            print(row)
        print("Previous CSV content:")
        for row in previous_data:
            print(row)

        new_vehicles = get_new_vehicles(previous_data, latest_data)
        print(f"Found {len(new_vehicles)} new vehicles in {yard}")

        for vehicle in new_vehicles:
            print(f"Checking new vehicle: {vehicle}")
            for alert in alerts:
                print(f"  Against alert: {alert}")
                if matches_alert(vehicle, alert):
                    send_email(alert["email"], vehicle)
                    matched_alerts.add(alert["email"])

    for alert in alerts:
        if alert["email"] not in matched_alerts:
            send_no_matches_email(alert["email"])

if __name__ == "__main__":
    main()
