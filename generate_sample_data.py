"""Deterministic generator for fictional OHLCV sample prices.

Run: python generate_sample_data.py
Produces data/prices.csv with ~250 trading days per demo ticker.
"""
from modules.sample_prices import write_prices_csv


def main() -> None:
    out = write_prices_csv()
    print(f"Wrote sample prices to {out}")


if __name__ == "__main__":
    main()
