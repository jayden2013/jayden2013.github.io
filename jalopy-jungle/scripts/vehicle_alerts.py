import os
import glob
from datetime import date, timedelta
import pandas as pd
from github import Github
import requests

# ——— Configuration ———
INVENTORY_DIR  = "jalopy-jungle/inventory-csvs"
GITHUB_REPO    = "jayden2013/jayden2013.github.io"
# keys we diff on; will lowercase to match normalized columns
KEY_COLUMNS    = ['year', 'make', 'model', 'row']
YARD_NAMES     = ['caldwell', 'nampa', 'boise', 'twin_falls', 'garden_city']
MONITOR_EMAIL  = "user@example.com"           # ← replace with the real recipient
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")    # ← set in your Action secrets
RESEND_API_KEY = os.getenv("RESEND_API_KEY")  # ← set in your Action secrets

def get_csv_paths_by_date(directory, yard_name):
    """
    Returns (yesterday_csv, today_csv) for a given yard.
    Matches inventory_{yard_name}_{YYYY-MM-DD}_*.csv for yesterday and today,
    picking the first file found for each.
    """
    today_str     = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    pat_today     = os.path.join(directory, f"inventory_{yard_name}_{today_str}_*.csv")
    pat_yesterday = os.path.join(directory, f"inventory_{yard_name}_{yesterday_str}_*.csv")

    today_files     = glob.glob(pat_today)
    yesterday_files = glob.glob(pat_yesterday)

    today_csv     = today_files[0]     if today_files     else None
    yesterday_csv = yesterday_files[0] if yesterday_files else None

    return yesterday_csv, today_csv

def load_csv(path):
    """Reads a CSV into a pandas DataFrame and normalizes its column names."""
    df = pd.read_csv(path)
    # strip whitespace & lowercase column names
    df.columns = df.columns.str.strip().str.lower()
    return df

def diff_dataframes(df_old, df_new, key_cols):
    """
    Returns three DataFrames:
      - added:   rows in df_new not in df_old
      - removed: rows in df_old not in df_new
      - changed: rows present in both where any non-key column differs
    """
    merged = df_old.merge(df_new, on=key_cols, how='outer',
                          indicator=True, suffixes=('_old','_new'))
    added   = merged[merged['_merge']=='right_only']
    removed = merged[merged['_merge']=='left_only']

    idx_old = df_old.set_index(key_cols)
    idx_new = df_new.set_index(key_cols)
    changed = idx_old.compare(idx_new).reset_index()

    return added, removed, changed

def fetch_open_issues(repo_name, github_token):
    """Returns a list of all open issues in the given GitHub repo."""
    gh   = Github(github_token)
    repo = gh.get_repo(repo_name)
    return list(repo.get_issues(state='open'))

def find_matching_issues(diffs, issues, match_fn):
    """
    Returns all issues for which match_fn(diffs, issue) is True.
    diffs is the tuple (added, removed, changed).
    """
    matched = []
    for issue in issues:
        if match_fn(diffs, issue):
            matched.append(issue)
    return matched

def send_email(resend_api_key, to_email, subject, html_body):
    """Sends an HTML email via the Resend API."""
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {resend_api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "from":    "alerts@yourdomain.com",
        "to":      [to_email],
        "subject": subject,
        "html":    html_body,
    }
    resp = requests.post(url, json=data, headers=headers)
    resp.raise_for_status()

if __name__ == "__main__":
    # lowercase the key columns to match normalized DataFrame columns
    key_cols = [c.lower() for c in KEY_COLUMNS]

    # 1) fetch all open GitHub issues
    issues = fetch_open_issues(GITHUB_REPO, GITHUB_TOKEN)

    # 2) loop through each yard
    for yard in YARD_NAMES:
        old_csv, new_csv = get_csv_paths_by_date(INVENTORY_DIR, yard)
        if not old_csv or not new_csv:
            print(f"[{yard}] missing CSV for yesterday or today, skipping.")
            continue

        # debug: show which files we're comparing
        print(f"[{yard}] Comparing:\n  yesterday → {old_csv}\n  today     → {new_csv}")

        df_old = load_csv(old_csv)
        df_new = load_csv(new_csv)

        # debug: verify column names
        print(f"[{yard}] old columns: {df_old.columns.tolist()}")
        print(f"[{yard}] new columns: {df_new.columns.tolist()}")

        # 3) diff the two DataFrames
        added, removed, changed = diff_dataframes(df_old, df_new, key_cols)

        # base email
        subject = f"🔔 [{yard}] Inventory Alert"
        html    = f"<h2>Inventory report for <strong>{yard}</strong> yard</h2>"

        # Case A: no changes
        if added.empty and removed.empty and changed.empty:
            subject += " – No changes"
            html    += "<p>No inventory changes since yesterday.</p>"
            send_email(RESEND_API_KEY, MONITOR_EMAIL, subject, html)
            print(f"[{yard}] emailed: no changes.")
            continue

        # list diffs
        if not added.empty:
            html += "<h3>Added:</h3><ul>"
            for _, r in added.iterrows():
                html += f"<li>Row {r['row']}: {r['year']} {r['make']} {r['model']}</li>"
            html += "</ul>"
        if not removed.empty:
            html += "<h3>Removed:</h3><ul>"
            for _, r in removed.iterrows():
                html += f"<li>Row {r['row']}: {r['year']} {r['make']} {r['model']}</li>"
            html += "</ul>"
        if not changed.empty:
            html += "<h3>Changed:</h3><ul>"
            for _, r in changed.iterrows():
                html += f"<li>Row {r['row']}: values changed</li>"
            html += "</ul>"

        # define matching logic
        def match_fn(diffs, issue):
            added, _, _ = diffs
            text = (issue.title or "") + "\n" + (issue.body or "")
            if yard in text.lower():
                return True
            for _, row in added.iterrows():
                if str(row['row']) in text:
                    return True
            return False

        matched = find_matching_issues((added, removed, changed), issues, match_fn)

        # Case B: diffs but no matches
        if not matched:
            subject += " – Changes (no matches)"
            html    += "<p><em>No open GitHub issues matched these changes.</em></p>"
            send_email(RESEND_API_KEY, MONITOR_EMAIL, subject, html)
            print(f"[{yard}] emailed: changes/no matches.")
            continue

        # Case C: diffs + matches
        subject += f" – {len(matched)} match(es) found"
        html    += "<h3>Matching GitHub Issues:</h3><ul>"
        for issue in matched:
            html += f"<li><a href='{issue.html_url}'>#{issue.number} {issue.title}</a></li>"
        html += "</ul>"

        send_email(RESEND_API_KEY, MONITOR_EMAIL, subject, html)
        print(f"[{yard}] emailed: {len(matched)} match(es).")
