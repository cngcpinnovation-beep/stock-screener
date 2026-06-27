"""Editable watchlist of NSE stocks to analyze.

Tickers use Yahoo Finance format with the ".NS" suffix for NSE (India) stocks.
Add or remove tickers freely; the screener reads this list automatically.
For BSE stocks use the ".BO" suffix instead.
"""

TICKERS = [
    # Large-cap / index heavyweights
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "LT.NS",
    "KOTAKBANK.NS",
    # Auto
    "TATAMOTORS.NS",
    "MARUTI.NS",
    "M&M.NS",
    # IT / tech
    "WIPRO.NS",
    "HCLTECH.NS",
    # Pharma / FMCG
    "SUNPHARMA.NS",
    "HINDUNILVR.NS",
    "NESTLEIND.NS",
    # Metals / energy / PSU
    "TATASTEEL.NS",
    "ONGC.NS",
    "POWERGRID.NS",
    "NTPC.NS",
    # Finance / others
    "BAJFINANCE.NS",
    "ASIANPAINT.NS",
    "TITAN.NS",
]
