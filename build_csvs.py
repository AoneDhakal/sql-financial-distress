"""Build companies.csv, financials.csv and macro.csv from raw SEC and FRED downloads.

Inputs (put the downloads here, keep their original names):
  raw/sec/CIK##########.json   SEC EDGAR XBRL "companyfacts" file, one per company
  raw/fred/<SERIES>.csv        FRED CSV for A191RL1Q225SBEA, UNRATE, FEDFUNDS, CPIAUCSL, BAA10Y

Run:  python build_csvs.py   (then python load_data.py)

Conventions
- Amounts are converted to USD millions.
- Only annual figures reported in 10-K filings are used. Duration items (revenue,
  net income, EBIT, interest, operating cash flow) must cover roughly 12 months.
- Where a figure was later restated, the value from the first 10-K that reported
  it is kept, so each year reflects what was known at the time.
- fiscal_year = calendar year the fiscal year ends in, except fiscal years ending
  January-March, which are assigned to the prior year (e.g. Walmart's year ending
  31 Jan 2025 is mostly 2024, so it is 2024). This keeps the macro join honest.
- Concepts are tried in order; the first one with a value for that year is used.
- EBIT: OperatingIncomeLoss where reported; otherwise pre-tax income + interest expense.
- Interest expense: income-statement interest where tagged; otherwise cash interest
  paid (Caterpillar and GE report interest only that way in XBRL). Apple stopped
  disclosing interest expense from FY2024, so those two years are blank and the
  interest-coverage flag can't fire for them.
- Macro: annual averages of monthly/daily FRED data; CPI inflation is the average
  12-month % change; GDP growth is compounded Q4-over-Q4 real growth.
- GE did not present a classified balance sheet (current assets/liabilities) for
  FY2016-2018, so its current ratio is blank for those years.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
YEARS = range(2016, 2026)  # 10 fiscal years

COMPANIES = {  # CIK: (ticker, name, sector)
    320193:  ("AAPL", "Apple", "Technology"),
    789019:  ("MSFT", "Microsoft", "Technology"),
    1018724: ("AMZN", "Amazon", "Consumer Discretionary"),
    320187:  ("NKE",  "Nike", "Consumer Discretionary"),
    104169:  ("WMT",  "Walmart", "Consumer Staples"),
    21344:   ("KO",   "Coca-Cola", "Consumer Staples"),
    80424:   ("PG",   "Procter & Gamble", "Consumer Staples"),
    200406:  ("JNJ",  "Johnson & Johnson", "Health Care"),
    78003:   ("PFE",  "Pfizer", "Health Care"),
    34088:   ("XOM",  "Exxon Mobil", "Energy"),
    93410:   ("CVX",  "Chevron", "Energy"),
    12927:   ("BA",   "Boeing", "Industrials"),
    18230:   ("CAT",  "Caterpillar", "Industrials"),
    40545:   ("GE",   "General Electric", "Industrials"),
    27904:   ("DAL",  "Delta Air Lines", "Industrials"),
    37996:   ("F",    "Ford Motor", "Consumer Discretionary"),
    1467858: ("GM",   "General Motors", "Consumer Discretionary"),
    732717:  ("T",    "AT&T", "Communication Services"),
    732712:  ("VZ",   "Verizon", "Communication Services"),
    753308:  ("NEE",  "NextEra Energy", "Utilities"),
}

# Each field has tiers of XBRL concepts. Within a tier the concepts are equivalent
# (companies switch tags over time), so the earliest-filed value across the tier wins.
# A later tier is only a fallback, used when no concept in an earlier tier has a value.
DURATION = {
    "revenue": [["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                 "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                 "RegulatedAndUnregulatedOperatingRevenue"],
                ["RevenuesNetOfInterestExpense"]],
    "net_income": [["NetIncomeLoss"], ["ProfitLoss"]],
    "ebit": [["OperatingIncomeLoss"],
             ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
              "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]],
    "interest_expense": [["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt",
                          "InterestAndDebtExpense", "InterestExpenseNet"],
                         ["InterestPaidNet", "InterestPaid"]],
    "operating_cash_flow": [["NetCashProvidedByUsedInOperatingActivities",
                             "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]],
}
INSTANT = {
    "total_assets": [["Assets"]],
    "total_liabilities": [["Liabilities"]],
    "total_equity": [["StockholdersEquity"],
                     ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]],
    "current_assets": [["AssetsCurrent"]],
    "current_liabilities": [["LiabilitiesCurrent"]],
}


def d(s):
    return date.fromisoformat(s)


def assign_year(end):
    return end.year - 1 if end.month <= 3 else end.year


def annual_facts(gaap, concept):
    """Annual 10-K USD facts for a concept -> list of dicts with parsed dates."""
    out = []
    for f in gaap.get(concept, {}).get("units", {}).get("USD", []):
        if not str(f.get("form", "")).startswith("10-K"):
            continue
        f = dict(f, end_d=d(f["end"]), filed_d=d(f["filed"]))
        if "start" in f:
            f["days"] = (f["end_d"] - d(f["start"])).days
        out.append(f)
    return out


def first_filed(facts):
    return min(facts, key=lambda f: f["filed_d"])["val"] if facts else None


def pick(gaap, tiers, ye, duration, field, sources):
    for tier in tiers:
        hits = []
        for rank, c in enumerate(tier):
            for f in annual_facts(gaap, c):
                if f["end_d"] != ye:
                    continue
                if duration and not 350 <= f.get("days", 0) <= 380:
                    continue
                if not duration and "start" in f:
                    continue
                hits.append((f["filed_d"], rank, c, f["val"]))
        if hits:
            filed, rank, c, val = min(hits)
            sources.setdefault(field, set()).add(c)
            return val, c
    return None, None


def extract(path):
    data = json.loads(path.read_text())
    gaap = data["facts"].get("us-gaap", {})

    # Fiscal year-ends: end dates of ~12-month revenue / net income facts in 10-Ks
    year_end = {}
    for concept in DURATION["net_income"][0] + DURATION["revenue"][0]:
        for f in annual_facts(gaap, concept):
            if 350 <= f.get("days", 0) <= 380:
                fy = assign_year(f["end_d"])
                year_end[fy] = max(year_end.get(fy, f["end_d"]), f["end_d"])

    rows, sources = [], {}
    for fy in YEARS:
        ye = year_end.get(fy)
        if ye is None:
            continue
        row, used = {"fiscal_year": fy}, {}
        for field, tiers in DURATION.items():
            row[field], used[field] = pick(gaap, tiers, ye, True, field, sources)
        for field, tiers in INSTANT.items():
            row[field], used[field] = pick(gaap, tiers, ye, False, field, sources)
        # Companies with no operating-income line (JNJ, PFE, XOM, CVX, GE...):
        # EBIT = pre-tax income + interest expense
        if used["ebit"] and used["ebit"].startswith("IncomeLoss") and row["interest_expense"]:
            row["ebit"] += row["interest_expense"]
        # Some filers don't tag total liabilities: derive it as assets - total equity
        if row["total_liabilities"] is None and row["total_assets"] is not None:
            for c in ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                      "StockholdersEquity"]:
                hits = [f for f in annual_facts(gaap, c) if f["end_d"] == ye and "start" not in f]
                if hits:
                    row["total_liabilities"] = row["total_assets"] - first_filed(hits)
                    sources.setdefault("total_liabilities", set()).add(f"Assets - {c}")
                    break
        rows.append(row)
    return data["entityName"], rows, sources


def build_financials():
    all_rows, log = [], []
    for cik, (ticker, name, sector) in COMPANIES.items():
        path = HERE / "raw" / "sec" / f"CIK{cik:010d}.json"
        if not path.exists():
            log.append(f"MISSING  {ticker}: {path.name}")
            continue
        entity, rows, sources = extract(path)
        for r in rows:
            r["ticker"] = ticker
        all_rows += rows
        log.append(f"OK       {ticker} ({entity}): {len(rows)} years")
        for field, used in sorted(sources.items()):
            if len(used) > 1 or field in ("interest_expense", "total_liabilities", "ebit"):
                log.append(f"           {field}: {', '.join(sorted(used))}")
    cols = ["ticker", "fiscal_year", "revenue", "net_income", "ebit", "interest_expense",
            "total_assets", "total_liabilities", "total_equity", "current_assets",
            "current_liabilities", "operating_cash_flow"]
    fin = pd.DataFrame(all_rows, columns=cols)
    money = cols[2:]
    fin[money] = (fin[money] / 1e6).round(1)
    present = set(fin["ticker"])
    comp = pd.DataFrame([(t, n, s) for (t, n, s) in COMPANIES.values() if t in present],
                        columns=["ticker", "name", "sector"])
    return comp, fin, log


def build_macro():
    def series(sid):
        df = pd.read_csv(HERE / "raw" / "fred" / f"{sid}.csv")
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df.dropna()

    def annual_mean(df):
        return df.groupby(df["date"].dt.year)["value"].mean()

    cpi = series("CPIAUCSL").set_index("date")["value"]
    cpi_yoy = (cpi.pct_change(12) * 100).dropna().reset_index()
    cpi_yoy.columns = ["date", "value"]
    # Quarterly GDP growth is annualized; compound the four quarters to get each
    # year's Q4-over-Q4 real growth (averaging them misstates crash years like 2020).
    gdp = series("A191RL1Q225SBEA")
    gdp_yr = gdp.groupby(gdp["date"].dt.year)["value"].apply(
        lambda q: ((1 + q / 100) ** 0.25).prod() * 100 - 100 if len(q) == 4 else float("nan"))
    macro = pd.DataFrame({
        "gdp_growth_pct": gdp_yr,
        "unemployment_pct": annual_mean(series("UNRATE")),
        "fed_funds_pct": annual_mean(series("FEDFUNDS")),
        "cpi_inflation_pct": annual_mean(cpi_yoy),
        "baa_spread_pct": annual_mean(series("BAA10Y")),
    })
    macro = macro.loc[[y for y in YEARS if y in macro.index]].round(2)
    macro.index.name = "year"
    return macro.reset_index()


if __name__ == "__main__":
    comp, fin, log = build_financials()
    print("\n".join(log))
    comp.to_csv(HERE / "companies.csv", index=False)
    fin.to_csv(HERE / "financials.csv", index=False)
    print(f"\ncompanies.csv: {len(comp)} rows, financials.csv: {len(fin)} rows")
    gaps = fin[fin.isna().any(axis=1)]
    if len(gaps):
        print("\nCompany-years with blank fields:")
        for _, r in gaps.iterrows():
            print(f"  {r.ticker} {r.fiscal_year}: {', '.join(c for c in fin.columns if pd.isna(r[c]))}")
    if all((HERE / "raw" / "fred" / f"{s}.csv").exists()
           for s in ["A191RL1Q225SBEA", "UNRATE", "FEDFUNDS", "CPIAUCSL", "BAA10Y"]):
        macro = build_macro()
        macro.to_csv(HERE / "macro.csv", index=False)
        print(f"macro.csv: {len(macro)} rows")
    else:
        print("macro.csv: skipped (FRED files missing)")
