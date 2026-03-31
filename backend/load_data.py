"""
Pull full historical OHLCV data from Alpha Vantage into Supabase.
Run from the backend/ directory: python load_data.py
Note: Alpha Vantage free tier = 25 requests/day. Full load needs 10 requests
      (5 crypto + 5 forex) so it fits in one run.
"""
import asyncio
import pathlib
import sys
import os

# Make sure we can import app modules
sys.path.insert(0, str(pathlib.Path(__file__).parent))

# Load .env from repo root
env_path = pathlib.Path(__file__).parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

from app.services.data_loader import (
    load_all_historical,
    CRYPTO_ASSETS,
    FOREX_PAIRS,
)


async def main():
    print(f"Starting historical data load...")
    print(f"  Crypto: {CRYPTO_ASSETS}")
    print(f"  Forex:  {FOREX_PAIRS}")
    print(f"  Timeframes: 1d + 1h + 4h")
    print(f"  Note: 1d via Alpha Vantage, 1h/4h via yfinance (free, no key needed).\n")

    async def progress(msg):
        print(f"  {msg}")

    results = await load_all_historical(
        crypto_assets=CRYPTO_ASSETS,
        forex_pairs=FOREX_PAIRS,
        timeframes=["1d", "1h", "4h"],
        progress_cb=progress,
    )

    print("\n── Results ──────────────────────────────────────")
    for asset, info in results.items():
        if isinstance(info, dict) and "error" in info:
            print(f"  ✗ {asset}: {info['error']}")
        else:
            bars = info.get("bars_upserted", 0) if isinstance(info, dict) else info
            print(f"  ✓ {asset}: {bars} bars")
    print("─────────────────────────────────────────────────")
    print("Done. Data is now in Supabase historical_data table.")


if __name__ == "__main__":
    asyncio.run(main())
