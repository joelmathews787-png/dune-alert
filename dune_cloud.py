#!/usr/bin/env python3
"""
Cloud version of the Dune: Part Three alert bot (runs once per call).
GitHub Actions calls this every ~5 minutes. State is kept in state.json.

Needs the environment variable NTFY_TOPIC (stored as a GitHub secret).
"""
import json
import os
import re
import sys
import urllib.request

BASE_URL = (
    "https://in.bookmyshow.com/movies/hyderabad/dune-part-three/buytickets/"
    "ET00526390/{date}?etCodes=*&language=english&refEventCode=ET00526390"
)
DATES = [
    "20261216", "20261217", "20261218", "20261219", "20261220",
    "20261221", "20261222", "20261223", "20261224", "20261225",
]
SIGNALS = {"Prasads": r"prasad", "PCX shows": r'aria-label="[^"]*pcx[^"]*"'}
PCX_TIME = r'aria-label="(\d{1,2}:\d{2}\s?[AP]M),[^"]*pcx'
STATE_FILE = "state.json"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="ignore")


def count_signals(html):
    return {k: len(re.findall(p, html, re.I)) for k, p in SIGNALS.items()}


def notify(title, message, url=None):
    print(f"ALERT: {title} - {message}", flush=True)
    if not NTFY_TOPIC:
        print("NTFY_TOPIC is not set; cannot send phone alert.", flush=True)
        return
    headers = {"Title": title, "Priority": "high", "Tags": "movie_camera"}
    if url:
        headers["Click"] = url
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode(), headers=headers
    )
    urllib.request.urlopen(req, timeout=15).read()


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")


def label(d):
    return f"{d[6:]}/{d[4:6]}"


def main():
    if "--test" in sys.argv:
        notify("Dune bot test", "Cloud alerts work.")
        return

    state = load_state()
    first_run = "dates" not in state
    dates_state = state.setdefault("dates", {})
    meta = state.setdefault("meta", {"blocked_notified": False})

    grew, errors, ok = [], 0, 0
    first_url = None
    for d in DATES:
        url = BASE_URL.format(date=d)
        try:
            html = fetch(url)
            counts = count_signals(html)
        except Exception as e:
            errors += 1
            print(f"{label(d)}: fetch error: {e}", flush=True)
            continue
        ok += 1
        old = dates_state.get(d)
        if old is None:
            dates_state[d] = counts
            print(f"{label(d)}: starting counts {counts}", flush=True)
            continue
        up = [k for k in counts if counts[k] > old.get(k, 0)]
        if up:
            times = sorted(set(re.findall(PCX_TIME, html, re.I)))
            grew.append(f"{label(d)}: new {', '.join(up)}. "
                        f"PCX times: {', '.join(times) or 'see page'}")
            first_url = first_url or url
            dates_state[d] = counts
        else:
            print(f"{label(d)}: no change {counts}", flush=True)
            dates_state[d] = {k: min(old.get(k, 0), counts[k]) for k in counts}

    if ok == 0:
        if not meta["blocked_notified"]:
            notify("Dune bot problem",
                   "Cloud bot could not load any BookMyShow page (probably blocked).")
            meta["blocked_notified"] = True
    else:
        meta["blocked_notified"] = False

    if grew:
        notify("Dune: Prasads/PCX update!", "\n".join(grew), first_url)
    elif first_run and ok:
        summary = "; ".join(f"{label(d)} P{c['Prasads']}/PCX{c['PCX shows']}"
                            for d, c in sorted(dates_state.items()))
        notify("Dune cloud bot started",
               f"Watching {ok} dates. Starting counts: {summary}")

    save_state(state)


if __name__ == "__main__":
    main()
