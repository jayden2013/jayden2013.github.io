import os
import re
import glob
from datetime import date, timedelta
import pandas as pd
from github import Github
import requests

# ——— Config ———
INVENTORY_DIR  = "jalopy-jungle/inventory-csvs"
GITHUB_REPO    = "jayden2013/jayden2013.github.io"
KEY_COLUMNS    = ['year', 'make', 'model', 'row']  # all key cols
YARD_NAMES     = ['caldwell', 'nampa', 'boise', 'twin_falls', 'garden_city']

# Email (env)
RESEND_API_KEY       = os.getenv("RESEND_API_KEY")          # secret
RESEND_FROM          = os.getenv("RESEND_FROM")             # verified sender
FAIL_ON_EMAIL_ERROR  = os.getenv("FAIL_ON_EMAIL_ERROR", "false").lower() == "true"

# GitHub (env)
GITHUB_TOKEN         = os.getenv("GITHUB_TOKEN")            # secret

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Yard name mapping for “Yards” section (supports common spellings)
YARD_CANON = {
    "caldwell": {"caldwell"},
    "nampa": {"nampa"},
    "boise": {"boise", "jalopy jungle (boise)", "jalopy jungle boise"},
    "twin_falls": {"twin_falls", "twin falls", "jalopy jungle (twin falls)", "jalopy jungle twin falls"},
    "garden_city": {"garden_city", "garden city", "jalopy jungle (garden city)", "jalopy jungle garden city"},
}

# ---------- File helpers ----------
def get_csv_paths_by_date(directory, yard_name):
    """Return (yesterday_csv, today_csv) for a yard; time-of-day ignored."""
    today_str     = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    pat_today     = os.path.join(directory, f"inventory_{yard_name}_{today_str}_*.csv")
    pat_yesterday = os.path.join(directory, f"inventory_{yard_name}_{yesterday_str}_*.csv")
    today_files     = glob.glob(pat_today)
    yesterday_files = glob.glob(pat_yesterday)
    return (yesterday_files[0] if yesterday_files else None,
            today_files[0] if today_files else None)

def load_csv(path):
    """Read CSV and normalize column names to lowercase."""
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    return df

# ---------- Diff ----------
def diff_dataframes(df_old, df_new, key_cols):
    """
    Returns three DataFrames:
      - added:   in new not in old
      - removed: in old not in new
      - changed: rows present in both but with any non-key column differing
                 (for current schema of only key cols, 'changed' will be empty)
    """
    merged = df_old.merge(
        df_new, on=key_cols, how='outer', indicator=True, suffixes=('_old','_new')
    )
    added   = merged[merged['_merge']=='right_only']
    removed = merged[merged['_merge']=='left_only']
    common  = merged[merged['_merge']=='both'].copy()

    non_key_cols = [c for c in df_old.columns if c not in key_cols]
    if non_key_cols:
        mask = pd.Series(False, index=common.index)
        for col in non_key_cols:
            mask |= common[f'{col}_old'] != common[f'{col}_new']
        changed = common[mask]
    else:
        changed = pd.DataFrame(columns=key_cols)

    return added, removed, changed

# ---------- GitHub ----------
def fetch_open_issues(repo_name, github_token):
    gh   = Github(github_token)
    repo = gh.get_repo(repo_name)
    return list(repo.get_issues(state='open'))

def _parse_sections(markdown_text: str):
    """
    Parse simple '### Heading' sections into a dict {heading_lower: text_block}.
    Grabs lines after a '### ' until the next '### '.
    """
    sections = {}
    current = None
    lines = (markdown_text or "").splitlines()
    for line in lines:
        if line.strip().startswith("### "):
            current = line.strip()[4:].strip().lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line.rstrip())
    # squish whitespace and join
    return {k: "\n".join(v).strip() for k, v in sections.items()}

def _canon_yards(raw: str):
    """
    Map 'Jalopy Jungle (Boise)' etc. to canonical keys like 'boise'.
    Supports multiple lines/commas.
    """
    if not raw:
        return set()
    out = set()
    tokens = []
    for line in raw.splitlines():
        tokens.extend([t.strip().lower() for t in line.split(",") if t.strip()])
    for tok in tokens:
        for canon, alts in YARD_CANON.items():
            if tok in alts or any(a in tok for a in alts):
                out.add(canon)
    return out

def _split_list(raw: str):
    """
    Split on commas/newlines, strip, drop empties.
    """
    if not raw:
        return []
    items = []
    for line in raw.splitlines():
        items.extend([x.strip() for x in line.split(",")])
    return [x for x in items if x]

def _parse_year_range(raw: str):
    """
    Accepts '1996' or '1996-1999'. Returns (min_year, max_year).
    If single year, returns (year, year). None if not parseable.
    """
    if not raw:
        return None
    raw = raw.strip()
    m2 = re.match(r"^\s*(\d{4})\s*[-–]\s*(\d{4})\s*$", raw)
    if m2:
        y1, y2 = int(m2.group(1)), int(m2.group(2))
        return (min(y1, y2), max(y1, y2))
    m1 = re.match(r"^\s*(\d{4})\s*$", raw)
    if m1:
        y = int(m1.group(1))
        return (y, y)
    return None

def parse_issue_alert(issue):
    """
    Parse a GitHub issue that uses your template:
      ### Email to notify
      <email>
      ### Make(s)
      Ford, Chevy
      ### Model(s)
      Thunderbird
      ### Year range
      1996-1997
      ### Yards
      Jalopy Jungle (Boise)
    Produces:
      email: str
      yards: set of canonical yard keys
      filters: {years:(min,max) or None, makes:set[str], models:set[str], row:None}
    """
    title = issue.title or ""
    body  = issue.body or ""
    text  = f"{title}\n{body}"

    sections = _parse_sections(body)

    # email: prefer section, fallback to any email in text
    email = EMAIL_RE.search(sections.get("email to notify", "")) or EMAIL_RE.search(text)
    email = email.group(0) if email else None

    # yards
    yards = _canon_yards(sections.get("yards"))

    # makes/models (uppercase for comparison)
    makes  = {m.upper() for m in _split_list(sections.get("make(s)", ""))}
    models = {m.upper() for m in _split_list(sections.get("model(s)", ""))}

    # years
    yr = _parse_year_range(sections.get("year range", ""))
    filters = {
        "years":  yr,          # (min,max) or None
        "makes":  makes,       # set[str] (upper) or empty
        "models": models,      # set[str] (upper) or empty
        "row":    None,        # not in your template, but supported
    }

    return {"issue": issue, "email": email, "yards": yards, "filters": filters}

# ---------- Matching ----------
def rows_matching(df, filters):
    """
    Filter df by optional filters:
      years=(min,max), makes=set[str], models=set[str], row=int
    CSV cols expected: 'year','make','model','row'
    """
    if df is None or df.empty:
        return df
    out = df.copy()

    # year range
    if filters.get("years"):
        lo, hi = filters["years"]
        years = pd.to_numeric(out["year"], errors="coerce")
        out = out[(years >= lo) & (years <= hi)]

    # makes/models to uppercase then membership test if provided
    if filters.get("makes"):
        out = out[out["make"].astype(str).str.upper().isin(filters["makes"])]
    if filters.get("models"):
        out = out[out["model"].astype(str).str.upper().isin(filters["models"])]

    # row exact (string-compare to be safe)
    if filters.get("row") is not None:
        out = out[out["row"].astype(str) == str(filters["row"])]

    return out

def find_matching_rows_for_issue(diffs, filters):
    added, removed, changed = diffs
    return {
        "added":   rows_matching(added,   filters),
        "removed": rows_matching(removed, filters),
        "changed": rows_matching(changed, filters),
    }

# ---------- Email ----------
def send_email(resend_api_key, from_email, to_email, subject, html_body):
    if not resend_api_key:
        print("WARN: RESEND_API_KEY missing; skipping email send.")
        return False
    if not from_email:
        print("WARN: RESEND_FROM missing; set a verified sender.")
        return False
    if not to_email:
        print("WARN: recipient email missing; skipping email send.")
        return False

    url = "https://api.resend.com/emails"
    headers = {"Authorization": f"Bearer {resend_api_key}", "Content-Type": "application/json"}
    data = {"from": from_email, "to": [to_email], "subject": subject, "html": html_body}
    resp = requests.post(url, json=data, headers=headers)

    if resp.status_code >= 400:
        print(f"ERROR: Resend returned {resp.status_code}: {resp.text}")
        if FAIL_ON_EMAIL_ERROR:
            resp.raise_for_status()
        return False
    return True

# ---------- Main ----------
if __name__ == "__main__":
    key_cols = [c.lower() for c in KEY_COLUMNS]

    # Pull and parse all open issues into alert definitions
    issues = fetch_open_issues(GITHUB_REPO, GITHUB_TOKEN)
    alerts = [parse_issue_alert(iss) for iss in issues]

    # warn if any issue lacks an email
    for a in alerts:
        if not a["email"]:
            print(f"[issue #{a['issue'].number}] No email found; skipping this issue for notifications.")

    # Diff each yard once, then notify per relevant issue (recipient from issue)
    for yard in YARD_NAMES:
        old_csv, new_csv = get_csv_paths_by_date(INVENTORY_DIR, yard)
        if not old_csv or not new_csv:
            print(f"[{yard}] missing CSV for yesterday or today, skipping yard.")
            continue

        print(f"[{yard}] Comparing:\n  yesterday → {old_csv}\n  today     → {new_csv}")
        df_old = load_csv(old_csv)
        df_new = load_csv(new_csv)
        print(f"[{yard}] old columns: {df_old.columns.tolist()}")
        print(f"[{yard}] new columns: {df_new.columns.tolist()}")

        added, removed, changed = diff_dataframes(df_old, df_new, key_cols)

        # relevant alerts (either yard unspecified = all yards, or explicitly includes this yard)
        relevant = [
            a for a in alerts
            if a["email"] and (not a["yards"] or yard in a["yards"])
        ]

        # Email *each* relevant issue's recipient whether matched or not
        for a in relevant:
            matches = find_matching_rows_for_issue((added, removed, changed), a["filters"])
            has_any = any(df is not None and not df.empty for df in matches.values())
            any_changes = any([
                added is not None and not added.empty,
                removed is not None and not removed.empty,
                changed is not None and not changed.empty
            ])

            subject = f"🔔 [{yard}] Inventory Alert for "
            html = [
                f"<h2>Inventory report for <strong>{yard}</strong></h2>",
                f"<p><strong>Vehicle:</strong> {a['issue'].title}</p>"
            ]

            # brief filter summary
            yr = a["filters"].get("years")
            makes = a["filters"].get("makes")
            models = a["filters"].get("models")
            filt_bits = []
            if yr:      filt_bits.append(f"years={yr[0]}–{yr[1]}")
            if makes:   filt_bits.append("makes=" + ", ".join(sorted(makes)))
            if models:  filt_bits.append("models=" + ", ".join(sorted(models)))
            if filt_bits:
                html.append("<p><strong>Filters:</strong> " + "; ".join(filt_bits) + "</p>")

            if not any_changes:
                subject += " – No changes"
                html.append("<p>No inventory changes since yesterday.</p>")
            elif not has_any:
                subject += " – No matches today"
                html.append("<p><em>No changes matched your alert today.</em></p>")
            else:
                subject += " – Matches found"
                if matches["added"] is not None and not matches["added"].empty:
                    html.append("<h3>Added:</h3><ul>")
                    for _, r in matches["added"].iterrows():
                        html.append(f"<li>Row {r['row']}: {r['year']} {r['make']} {r['model']}</li>")
                    html.append("</ul>")
                if matches["removed"] is not None and not matches["removed"].empty:
                    html.append("<h3>Removed:</h3><ul>")
                    for _, r in matches["removed"].iterrows():
                        html.append(f"<li>Row {r['row']}: {r['year']} {r['make']} {r['model']}</li>")
                    html.append("</ul>")
                if matches["changed"] is not None and not matches["changed"].empty:
                    html.append("<h3>Changed:</h3><ul>")
                    for _, r in matches["changed"].iterrows():
                        html.append(f"<li>Row {r['row']}: values changed</li>")
                    html.append("</ul>")

            ok = send_email(RESEND_API_KEY, RESEND_FROM, a["email"], subject, "\n".join(html))
            print(f"[{yard}] emailed {a['email']} for issue #{a['issue'].number} success={ok}")
