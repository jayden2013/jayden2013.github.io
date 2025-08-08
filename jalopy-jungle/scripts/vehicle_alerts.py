import os
import glob
from datetime import date, timedelta
import pandas as pd
from github import Github
import requests

# ——— Configuration ———
INVENTORY_DIR  = "jalopy-jungle/inventory-csvs"
GITHUB_REPO    = "jayden2013/jayden2013.github.io"
KEY_COLUMNS    = ['year', 'make', 'model', 'row']
YARD_NAMES     = ['caldwell', 'nampa', 'boise', 'twin_falls', 'garden_city']
MONITOR_EMAIL  = "user@example.com"           # ← replace with the real recipient
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")    # ← set in your Action secrets
RESEND_API_KEY = os.getenv("RESEND_API_KEY")  # ← ditto


def get_csv_paths_by_date(directory, yard_name):
    """
    Returns (yesterday_csv, today_csv) for a given yard.
    It looks for any file named
      inventory_{yard_name}_{YYYY-MM-DD}_*.csv
    for yesterday’s date and for today’s date, and picks the
    first match it finds (or None if no match).
    """
    today_str     = date.today().isoformat()                  # "2025-08-08"
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    pat_today     = os.path.join(directory, f"inventory_{yard_name}_{today_str}_*.csv")
    pat_yesterday = os.path.join(directory, f"inventory_{yard_name}_{yesterday_str}_*.csv")

    today_files     = glob.glob(pat_today)
    yesterday_files = glob.glob(pat_yesterday)

    today_csv     = today_files[0]     if today_files     else None
    yesterday_csv = yesterday_files[0] if yesterday_files else None

    return yesterday_csv, today_csv


def load_csv(path):
    """Reads a CSV into a pandas DataFrame."""
    return pd.read_csv(path)


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
    # 1) Fetch all open issues once
    issues = fetch_open_issues(GITHUB_REPO, GITHUB_TOKEN)

    # 2) For each yard, compare yesterday vs. today
    for yard in YARD_NAMES:
        old_csv, new_csv = get_csv_paths_by_date(INVENTORY_DIR, yard)
        if not old_csv or not new_csv:
            print(f"[{yard}] missing CSV for yesterday or today, skipping.")
            continue

        df_old = load_csv(old_csv)
        df_new = load_csv(new_csv)
        added, removed, changed = diff_dataframes(df_old, df_new, KEY_COLUMNS)

        # Base email setup
        subject = f"🔔 [{yard}] Inventory Alert"
        html    = f"<h2>Inventory report for <strong>{yard}</strong> yard</h2>"

        # 3) Case A: no changes
        if added.empty and removed.empty and changed.empty:
            subject += " – No changes"
            html    += "<p>No inventory changes since yesterday.</p>"
            send_email(RESEND_API_KEY, MONITOR_EMAIL, subject, html)
            print(f"[{yard}] emailed: no changes.")
            continue

        # 4) List out any diffs
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

        # 5) Find issues that mention this yard or any new row numbers
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

        # 6a) Case B: diffs but no matches
        if not matched:
            subject += " – Changes (no matches)"
            html    += "<p><em>No open GitHub issues matched these changes.</em></p>"
            send_email(RESEND_API_KEY, MONITOR_EMAIL, subject, html)
            print(f"[{yard}] emailed: changes/no matches.")
            continue

        # 6b) Case C: diffs + matches
        subject += f" – {len(matched)} match(es) found"
        html    += "<h3>Matching GitHub Issues:</h3><ul>"
        for issue in matched:
            html += f"<li><a href='{issue.html_url}'>#{issue.number} {issue.title}</a></li>"
        html += "</ul>"

        send_email(RESEND_API_KEY, MONITOR_EMAIL, subject, html)
        print(f"[{yard}] emailed: {len(matched)} match(es).")
