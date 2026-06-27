"""NSE stock screener.

Pulls 1 year of daily (1D interval) data for each ticker in watchlist.py using
the free yfinance library and writes a Markdown report (output.md) with:

*All Stocks* table - Stock, Above 20 EMA, 20 EMA > 50 EMA, Volume Good?, Resistance, Distance to Resistance, Score
*Breakout Candidates* table - stocks with Score > 1 shown with Close, Resistance zone, Distance, Distance %, and Breakout Status

Column logic
------------
Above 20 EMA            : last close > EMA(20) of close
20 EMA > 50 EMA         : EMA(20) > EMA(50) on the last bar
Volume Good?            : last-day volume > 20-day SMA of volume
Resistance              : nearest swing-high cluster above the current close, formatted as "low-high"
Distance to Resistance  : midpoint(resistance band) - last close (price units)
Score                   : sum of the three boolean checks (0-3)
Breakout Status         : Imminent (<=1%), Near (<=3%), Approaching (<=5%), Far (>5%)

Everything used here is free and requires no API key or subscription.
"""

from __future__ import annotations
import os
import sys
import pandas as pd
import yfinance as yf
from watchlist import TICKERS
import os
import requests

# Configuration
# ---------------------------------------------------------------------------
PERIOD = "1y"  # history pulled for indicator calculations
INTERVAL = "1d"  # daily candles
EMA_FAST = 20
EMA_SLOW = 50
VOL_MA = 20

# Resistance detection
PIVOT_WINDOW = 5  # bars on each side that define a swing high
DISTANCE_LOOKBACK = 126  # ~6 trading months to search for swing highs
CLUSTER_TOLERANCE = 0.01  # group swing highs within 1% of each other
SINGLE_BAND_PAD = 0.005  # +/-0.5% band when a cluster has only one high

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output.md")


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _display_name(ticker: str) -> str:
    """Strip the exchange suffix for a cleaner Stock column."""
    return ticker.split(".")[0]


def find_resistance(df: pd.DataFrame, close: float) -> tuple[str, float | None]:
    """Return (band_string, distance) for the nearest swing-high cluster above close.

    Returns ("N/A", None) when no swing high sits above the current close.
    """
    recent = df.tail(DISTANCE_LOOKBACK)
    highs = recent["High"].to_numpy()
    n = len(highs)

    # Identify swing-high pivots: a local maximum within +/- PIVOT_WINDOW bars
    pivots = []
    for i in range(PIVOT_WINDOW, n - PIVOT_WINDOW):
        window = highs[i - PIVOT_WINDOW : i + PIVOT_WINDOW + 1]
        if highs[i] == window.max():
            pivots.append(float(highs[i]))

    # Keep only pivots above the current close (true resistance)
    above = sorted(p for p in pivots if p > close)
    if not above:
        return "N/A", None

    # Cluster the nearest pivot with neighbours within CLUSTER_TOLERANCE
    nearest = above[0]
    cluster = [p for p in above if p <= nearest * (1 + CLUSTER_TOLERANCE)]

    low = min(cluster)
    high = max(cluster)
    if low == high:
        # Single swing high -> build a small band around it
        low = high * (1 - SINGLE_BAND_PAD)
        high = high * (1 + SINGLE_BAND_PAD)

    midpoint = (low + high) / 2
    distance = round(midpoint - close, 1)
    band = f"{round(low)}-{round(high)}"
    return band, distance


def analyze(ticker: str) -> dict:
    """Compute metrics for a ticker. Failures yield an N/A dict."""
    try:
        df = yf.download(
            ticker,
            period=PERIOD,
            interval=INTERVAL,
            auto_adjust=False,
            progress=False,
        )
    except Exception as exc:  # network / library errors
        print(f" ! {ticker}: download failed ({exc})", file=sys.stderr)
        df = pd.DataFrame()

    # yfinance may return MultiIndex columns for a single ticker; flatten them
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.empty or len(df) < EMA_SLOW:
        print(f" ! {ticker}: not enough data", file=sys.stderr)
        return {
            "stock": _display_name(ticker),
            "above_ema": "N/A",
            "ema_cross": "N/A",
            "volume_good": "N/A",
            "resistance": "N/A",
            "distance": "N/A",
            "score": "N/A",
            "close": "N/A",
        }

    df = df.dropna(subset=["Close", "Volume"])

    ema_fast = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()
    vol_ma = df["Volume"].rolling(VOL_MA).mean()

    close = float(df["Close"].iloc[-1])
    above_ema = close > float(ema_fast.iloc[-1])
    ema_cross = float(ema_fast.iloc[-1]) > float(ema_slow.iloc[-1])
    volume_good = float(df["Volume"].iloc[-1]) > float(vol_ma.iloc[-1])

    resistance, distance = find_resistance(df, close)
    score = int(above_ema) + int(ema_cross) + int(volume_good)

    return {
        "stock": _display_name(ticker),
        "above_ema": _yes_no(above_ema),
        "ema_cross": _yes_no(ema_cross),
        "volume_good": _yes_no(volume_good),
        "resistance": resistance,
        "distance": "N/A" if distance is None else distance,
        "score": score,
        "close": round(close, 2),
    }


def _score_key(row: dict) -> int:
    """Sort helper: numeric scores first (descending), N/A rows last."""
    return row["score"] if isinstance(row["score"], int) else -1


def _md_table(headers: list[str], rows: list[list]) -> str:
    """Build a markdown table string."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    def fmt_row(cells):
        return (
            "| "
            + " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(cells))
            + " |"
        )

    lines = [
        fmt_row(headers),
        "| " + " | ".join("-" * w for w in col_widths) + " |",
    ]
    for row in rows:
        lines.append(fmt_row(row))
    return "\n".join(lines)


def _breakout_status(close: float | str, distance: float | str) -> str:
    if distance == "N/A" or close == "N/A":
        return "N/A"
    pct = distance / close * 100
    if pct <= 1:
        return "Imminent"
    if pct <= 3:
        return "Near"
    if pct <= 5:
        return "Approaching"
    return "Far"

def build_telegram_message(rows):
    lines = []

    lines.append("📈 Daily Swing Scan")
    lines.append("")

    # Score 3 stocks
    score3 = [
        r for r in rows
        if isinstance(r["score"], int) and r["score"] == 3
    ]

    # Near breakout stocks
    near_breakout = []

    for r in rows:
        if not isinstance(r["score"], int):
            continue

        dist = r["distance"]
        close = r["close"]

        if not isinstance(dist, (int, float)):
            continue

        if not isinstance(close, (int, float)):
            continue

        pct = dist / close * 100

        if pct <= 3:
            near_breakout.append((r, pct))

    if score3:
        lines.append("🔥 Score 3 Stocks")
        lines.append("")

        for r in score3:
            dist = r["distance"]
            close = r["close"]

            pct = (
                dist / close * 100
                if isinstance(dist, (int, float))
                else None
            )

            lines.append(
                f"{r['stock']}\n"
                f"Resistance: {r['resistance']}\n"
                f"Distance: {dist}\n"
                f"Distance %: {pct:.1f}%\n"
            )

    if near_breakout:
        lines.append("")
        lines.append("⚡ Near Breakout (≤3%)")
        lines.append("")

        near_breakout.sort(key=lambda x: x[1])

        for r, pct in near_breakout:
            lines.append(
                f"{r['stock']} "
                f"({pct:.1f}%, "
                f"{_breakout_status(r['close'], r['distance'])})"
            )

    if not score3 and not near_breakout:
        lines.append("No actionable setups today.")

    return "\n".join(lines)


def send_telegram(message):
    token = os.environ["TELEGRAM_TOKEN"].strip()
    chat_id = os.environ["TELEGRAM_CHAT_ID"].strip()

    print(f"Token length: {len(token)}")
    print(f"Chat ID: {chat_id}")

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": message,
        },
        timeout=30,
    )

    print(response.text)
    response.raise_for_status()

def main() -> None:
    print(f"Analyzing {len(TICKERS)} stocks ({INTERVAL} interval, {PERIOD} history)...")
    rows = []
    for ticker in TICKERS:
        print(f"  - {ticker}")
        rows.append(analyze(ticker))

    rows.sort(key=_score_key, reverse=True)

    all_table_headers = [
        "Stock",
        "Above 20 EMA",
        "20 EMA > 50 EMA",
        "Volume Good?",
        "Resistance",
        "Distance to Resistance",
        "Score",
    ]
    all_table_rows = [
        [
            r["stock"],
            r["above_ema"],
            r["ema_cross"],
            r["volume_good"],
            r["resistance"],
            r["distance"],
            r["score"],
        ]
        for r in rows
    ]

    breakout_headers = [
        "Stock",
        "Close",
        "Resistance",
        "Distance",
        "Distance %",
        "Breakout Status",
    ]
    breakout_rows = []
    for r in rows:
        if not isinstance(r["score"], int) or r["score"] <= 1:
            continue
        dist = r["distance"]
        close = r["close"]
        if isinstance(dist, (int, float)) and isinstance(close, (int, float)):
            pct = f"{dist / close * 100:.1f}%"
        else:
            pct = "N/A"
        breakout_rows.append(
            [
                r["stock"],
                close,
                r["resistance"],
                dist,
                pct,
                _breakout_status(close, dist),
            ]
        )

    with open(OUTPUT_FILE, "w") as f:
        f.write("# Stock Screener Results\n\n")
        f.write("## All Stocks\n\n")
        f.write(_md_table(all_table_headers, all_table_rows))
        f.write("\n\n")
        if breakout_rows:
            f.write("## Breakout Candidates (Score > 1)\n\n")
            f.write(_md_table(breakout_headers, breakout_rows))
            f.write("\n")

    print(f"\nDone. Wrote {len(rows)} rows to {OUTPUT_FILE}")

    message = build_telegram_message(rows)

    print("\nTelegram Message")
    print("----------------")
    print(message)
    
    send_telegram(message)


if __name__ == "__main__":
    main()
