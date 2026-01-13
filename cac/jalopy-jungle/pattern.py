#!/usr/bin/env python3
"""
export_bolt_patterns.py

Exports bolt patterns from your tiresize.com bolt pattern finder CGI chain.

Requires:
  pip install requests beautifulsoup4

Usage:
  python export_bolt_patterns.py --out bolt_patterns.csv --delay 0.25
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

BASE = "https://tiresize.com"
FINDER_PATH = "/bolt-pattern-finder/"

# Sample response: "Bolt Pattern:<br><br>5-127mm (5x5")"
PATTERN_RE = re.compile(
    r"Bolt\s*Pattern:\s*<br>\s*<br>\s*(?P<metric>[^<\(\r\n]+)\s*\((?P<std>[^)]+)\)",
    re.IGNORECASE,
)

# Parses std like 5x5" or 5x114.3 etc.
STD_BC_RE = re.compile(r"(?P<count>\d+)\s*[xX]\s*(?P<circle>\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class Option:
    value: str
    label: str


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def parse_select_options(html: str, select_id: str) -> List[Option]:
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", {"id": select_id})
    if sel is None:
        # Sometimes response may include wrapper div and select inside; try a broader search
        sel = soup.select_one(f"select#{select_id}")
    if sel is None:
        raise RuntimeError(f"Could not find select#{select_id} in response")

    opts: List[Option] = []
    for opt in sel.find_all("option"):
        val = (opt.get("value") or "").strip()
        lab = (opt.text or "").strip()
        if not val or val == "0":
            continue
        if "select" in lab.lower():
            continue
        opts.append(Option(value=val, label=lab))

    # de-dupe by value
    seen = set()
    out = []
    for o in opts:
        if o.value in seen:
            continue
        seen.add(o.value)
        out.append(o)
    return out


def bolt_get(session: requests.Session, endpoint: str, year: str, make: str, model: str, submodel: str) -> str:
    url = f"{BASE}{endpoint}"
    params = {"year": year, "make": make, "model": model, "submodel": submodel}
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.text


def parse_pattern(resp_html: str) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[float]]:
    m = PATTERN_RE.search(resp_html)
    if not m:
        return None, None, None, None

    metric = m.group("metric").strip()     # e.g., "5-127mm"
    std = m.group("std").strip()           # e.g., '5x5"'

    bc = STD_BC_RE.search(std)
    if bc:
        count = int(bc.group("count"))
        circle = float(bc.group("circle"))
        return metric, std, count, circle

    return metric, std, None, None


def extract_years_from_finder(session: requests.Session) -> List[Option]:
    soup = get_soup(session, f"{BASE}{FINDER_PATH}")
    sel = soup.find("select", {"id": "boltyearselect"})
    if sel is None:
        raise RuntimeError("Could not find #boltyearselect on finder page")

    years: List[Option] = []
    for opt in sel.find_all("option"):
        val = (opt.get("value") or "").strip()
        lab = (opt.text or "").strip()
        if not val or val == "0":
            continue
        if "select" in lab.lower():
            continue
        years.append(Option(value=val, label=lab))

    # Note: your HTML shows duplicate value for 2025/2024/2023 all using value=2023
    # We will keep BOTH label and value. Use label for output year, value for queries.
    return years


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="Output CSV file")
    ap.add_argument("--delay", type=float, default=0.25, help="Delay between requests (seconds)")
    ap.add_argument("--max-years", type=int, default=0, help="Limit years processed (0 = no limit)")
    ap.add_argument("--max-makes", type=int, default=0, help="Limit makes per year (0 = no limit)")
    ap.add_argument("--max-models", type=int, default=0, help="Limit models per make (0 = no limit)")
    ap.add_argument("--max-submodels", type=int, default=0, help="Limit submodels per model (0 = no limit)")
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "BoltPatternExport/1.0 (site-owner)",
        "Accept": "text/html,*/*;q=0.9",
    })

    years = extract_years_from_finder(session)
    if args.max_years and args.max_years > 0:
        years = years[:args.max_years]

    fieldnames = [
        "year_label", "year_value",
        "make_name", "make_id",
        "model_name", "model_id",
        "submodel_name", "submodel_id",
        "bolt_pattern_metric", "bolt_pattern_std",
        "bolt_count", "bolt_circle",
        "source_url",
    ]

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        for y in years:
            # 1) makes
            make_html = bolt_get(session, "/cgi-bin/boltMake.cgi", y.value, "0", "0", "0")
            makes = parse_select_options(make_html, "boltmakeselect")
            if args.max_makes and args.max_makes > 0:
                makes = makes[:args.max_makes]

            for mk in makes:
                # 2) models
                model_html = bolt_get(session, "/cgi-bin/boltModel.cgi", y.value, mk.value, "0", "0")
                models = parse_select_options(model_html, "boltmodelselect")
                if args.max_models and args.max_models > 0:
                    models = models[:args.max_models]

                for md in models:
                    # 3) submodels/options
                    sub_html = bolt_get(session, "/cgi-bin/boltSubmodel.cgi", y.value, mk.value, md.value, "0")
                    submodels = parse_select_options(sub_html, "boltsubmodelselect")
                    if args.max_submodels and args.max_submodels > 0:
                        submodels = submodels[:args.max_submodels]

                    for sm in submodels:
                        # 4) final pattern
                        endpoint = "/cgi-bin/boltPattern.cgi"
                        params = f"year={y.value}&make={mk.value}&model={md.value}&submodel={sm.value}"
                        source_url = f"{BASE}{endpoint}?{params}"

                        resp = bolt_get(session, endpoint, y.value, mk.value, md.value, sm.value)
                        metric, std, count, circle = parse_pattern(resp)

                        # Some combos might return empty/unexpected; skip
                        if not metric and not std:
                            time.sleep(args.delay)
                            continue

                        w.writerow({
                            "year_label": y.label,
                            "year_value": y.value,
                            "make_name": mk.label,
                            "make_id": mk.value,
                            "model_name": md.label,
                            "model_id": md.value,
                            "submodel_name": sm.label,
                            "submodel_id": sm.value,
                            "bolt_pattern_metric": metric or "",
                            "bolt_pattern_std": std or "",
                            "bolt_count": "" if count is None else str(count),
                            "bolt_circle": "" if circle is None else str(circle),
                            "source_url": source_url,
                        })

                        time.sleep(args.delay)

            # be a little nicer between years
            time.sleep(args.delay * 2)

    print(f"Export complete: {args.out}")


if __name__ == "__main__":
    main()
