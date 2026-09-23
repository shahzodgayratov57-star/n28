"""
USD/UZS Central Bank rate tracker.

Scrapes bank.uz's currency archive (server-rendered, one page per date),
keeps a growing CSV history, renders a 1-year line chart, and sends it to
a Telegram chat via bot API.

Usage:
    python usd_tracker.py backfill [--days 365]   # fill history from archive
    python usd_tracker.py update                  # fetch latest day, append
    python usd_tracker.py chart                    # (re)build chart from CSV
    python usd_tracker.py send                     # send latest chart to Telegram
    python usd_tracker.py daily                     # update + chart + send (used by the scheduled routine)
"""
import csv
import json
import os
import re
import sys
import argparse
from datetime import date, timedelta

import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CSV = os.path.join(REPO_ROOT, "data", "usd_rates.csv")
CHART_PNG = os.path.join(REPO_ROOT, "charts", "usd_last_year.png")
TELEGRAM_CONFIG = os.path.join(REPO_ROOT, "config", "telegram.json")

ARCHIVE_URL = "https://bank.uz/uz/currency/archive/{d}-{m}-{y}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; usd-tracker/1.0)"}


def _load_telegram_creds():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if (not token or not chat_id) and os.path.exists(TELEGRAM_CONFIG):
        with open(TELEGRAM_CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
        token = token or cfg.get("bot_token")
        chat_id = chat_id or cfg.get("chat_id")
    return token, chat_id


TELEGRAM_TOKEN, TELEGRAM_CHAT_ID = _load_telegram_creds()


def fetch_usd_rate(d: date):
    url = ARCHIVE_URL.format(d=d.day, m=d.month, y=d.year)
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return None
    match = re.search(r'"USD"\s*:\s*"([\d.]+)"', resp.text)
    if not match:
        return None
    return float(match.group(1))


def load_history():
    rows = {}
    if os.path.exists(DATA_CSV):
        with open(DATA_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows[row["date"]] = float(row["usd_rate"])
    return rows


def save_history(rows):
    os.makedirs(os.path.dirname(DATA_CSV), exist_ok=True)
    with open(DATA_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "usd_rate"])
        for d in sorted(rows):
            writer.writerow([d, rows[d]])


def backfill(days=365):
    rows = load_history()
    today = date.today()
    added = 0
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        key = d.isoformat()
        if key in rows:
            continue
        rate = fetch_usd_rate(d)
        if rate is not None:
            rows[key] = rate
            added += 1
    save_history(rows)
    print(f"Backfill complete. Added {added} new day(s). Total: {len(rows)}")
    return rows


def update_latest():
    rows = load_history()
    today = date.today()
    for d in (today, today - timedelta(days=1), today - timedelta(days=2)):
        key = d.isoformat()
        if key in rows:
            break
        rate = fetch_usd_rate(d)
        if rate is not None:
            rows[key] = rate
            save_history(rows)
            print(f"Added {key}: {rate}")
            return rows, key, rate
    print("No new rate found for the last 3 days.")
    return rows, None, None


def build_chart(rows=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    if rows is None:
        rows = load_history()

    cutoff = (date.today() - timedelta(days=365)).isoformat()
    items = sorted((d, r) for d, r in rows.items() if d >= cutoff)
    if not items:
        raise SystemExit("No data to chart yet.")

    dates = [date.fromisoformat(d) for d, _ in items]
    values = [r for _, r in items]

    fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
    ax.plot(dates, values, color="#2563eb", linewidth=1.6)

    for i in range(1, len(values)):
        color = "#16a34a" if values[i] >= values[i - 1] else "#dc2626"
        ax.plot(dates[i - 1:i + 1], values[i - 1:i + 1], color=color, linewidth=1.6)

    ax.set_title("USD/UZS - Markaziy bank kursi (so'nggi 1 yil)", fontsize=14)
    ax.set_ylabel("so'm")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate()
    ax.grid(True, alpha=0.3)

    last_date, last_value = items[-1]
    ax.annotate(f"{last_value:,.0f}", (dates[-1], values[-1]),
                textcoords="offset points", xytext=(0, 10), fontsize=10, fontweight="bold")

    os.makedirs(os.path.dirname(CHART_PNG), exist_ok=True)
    fig.tight_layout()
    fig.savefig(CHART_PNG)
    plt.close(fig)
    print(f"Chart saved to {CHART_PNG}")
    return CHART_PNG, items


def send_telegram(caption, photo_path=CHART_PNG):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars are required to send.")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    with open(photo_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={"photo": f},
            timeout=30,
        )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise SystemExit(f"Telegram send failed: {result}")
    print("Sent to Telegram.")
    return result


def make_caption(rows, latest_key):
    items = sorted(rows.items())
    latest_rate = rows[latest_key]
    prev_rate = None
    for d, r in items:
        if d == latest_key:
            break
        prev_rate = r
    change = "" if prev_rate is None else f" ({'+' if latest_rate - prev_rate >= 0 else ''}{latest_rate - prev_rate:,.2f} so'm)"
    return f"USD/UZS kursi - {latest_key}\nMarkaziy bank kursi: {latest_rate:,.2f} so'm{change}\n\nSo'nggi 1 yillik dinamika:"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["backfill", "update", "chart", "send", "daily"])
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()

    if args.command == "backfill":
        backfill(args.days)
    elif args.command == "update":
        update_latest()
    elif args.command == "chart":
        build_chart()
    elif args.command == "send":
        rows = load_history()
        latest_key = max(rows)
        build_chart(rows)
        send_telegram(make_caption(rows, latest_key))
    elif args.command == "daily":
        rows, latest_key, _ = update_latest()
        if latest_key is None:
            latest_key = max(rows)
        build_chart(rows)
        send_telegram(make_caption(rows, latest_key))


if __name__ == "__main__":
    main()
