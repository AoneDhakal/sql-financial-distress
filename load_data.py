"""Load the CSV files into a SQLite database and run the analysis queries.

Put three CSVs in the same folder as this script (column names must match schema.sql):
  companies.csv   ticker, name, sector
  financials.csv  ticker, fiscal_year, revenue, net_income, ebit, interest_expense,
                  total_assets, total_liabilities, total_equity, current_assets,
                  current_liabilities, operating_cash_flow
  macro.csv       year, gdp_growth_pct, unemployment_pct, fed_funds_pct,
                  cpi_inflation_pct, baa_spread_pct

Run:  python load_data.py
Output: distress.db (open in DB Browser for SQLite) and dashboard_export.csv
"""
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DB = HERE / "distress.db"

con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys = ON")
con.executescript((HERE / "schema.sql").read_text())

for table in ["companies", "financials", "macro"]:
    df = pd.read_csv(HERE / f"{table}.csv")
    df.to_sql(table, con, if_exists="append", index=False)
    print(f"Loaded {len(df):>4} rows into {table}")

con.executescript((HERE / "queries.sql").read_text())  # creates the views

export = pd.read_sql("SELECT * FROM dashboard_export ORDER BY ticker, fiscal_year", con)
export.to_csv(HERE / "dashboard_export.csv", index=False)
print(f"Wrote dashboard_export.csv ({len(export)} rows)")
con.close()
