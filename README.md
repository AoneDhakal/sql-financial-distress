# Corporate Financial Distress & Macroeconomic Analysis (SQL)

Ranks 20 large U.S. public companies by financial-distress risk each year (FY2016–FY2025, 200 company-years) and tests whether distress rises when the economy tightens (higher rates, wider credit spreads, higher unemployment). Built entirely on primary sources: SEC EDGAR 10-K filings (XBRL) and FRED.

## Files
| File | What it does |
| --- | --- |
| `build_csvs.py` | Parses the raw SEC "companyfacts" JSON and FRED CSVs in `raw/` into `companies.csv`, `financials.csv`, `macro.csv` |
| `schema.sql` | Creates three tables: `companies`, `financials` (one row per company-year), `macro` (one row per year of FRED data) |
| `load_data.py` | Loads the three CSVs into `distress.db` (SQLite), builds the views, exports `dashboard_export.csv` |
| `queries.sql` | Eight analysis queries: data check, ratios, year-over-year change, distress score, ranking, macro join, sector-by-rate-regime, dashboard export |
| `results/Q1.csv`–`Q7.csv` | Output of each query |

## Steps
1. Download the raw data into `raw/sec/` (one `CIK##########.json` per company from `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`) and `raw/fred/` (one CSV per series from `https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES`).
2. Run `python build_csvs.py`, then `python load_data.py`.
3. Open `distress.db` in DB Browser for SQLite and run each query in `queries.sql`.
4. Load `dashboard_export.csv` into Power BI or Tableau.

## Companies (20, eight sectors)
Technology: AAPL, MSFT · Consumer Discretionary: AMZN, NKE, F, GM · Consumer Staples: WMT, KO, PG · Health Care: JNJ, PFE · Energy: XOM, CVX · Industrials: BA, CAT, GE, DAL · Communication Services: T, VZ · Utilities: NEE. Banks and insurers are excluded because current-ratio and debt-to-equity logic doesn't apply to their balance sheets.

## SQL techniques used
Joins (inner and left), GROUP BY aggregations, CASE scoring, views, CTEs, window functions (LAG, RANK, ROW_NUMBER, COUNT OVER), NULLIF for divide-by-zero safety.

## Distress score (0–5)
One point each for: debt-to-equity > 2.0 **or negative equity**, interest coverage < 1.5, current ratio < 1.0, negative net margin, operating cash flow / total liabilities < 0.1. A score of 3+ is "high risk".

## Findings
1. **Distress follows credit conditions and the labor market, not the Fed funds rate.** Across 2016–2025, average distress correlates +0.54 with the BAA credit spread and +0.47 with unemployment, but −0.50 with the Fed funds rate. It peaked in 2020 (average 1.75; unemployment 8.1%, spread 2.72%), when high-risk companies rose to 5 of 20, up from 3 in 2016–2018.
2. **The 2023–2025 rate hikes did not raise distress.** With the Fed funds rate above 4%, average distress fell to 1.28, versus 1.50 in 2016–2022, and only 1 company was high-risk in 2024. Large companies had locked in long-term fixed-rate debt and credit spreads stayed tight (1.55–1.91%), so higher policy rates hadn't reached their cost of debt.
3. **Industrials and Utilities carry the most structural risk.** These sectors average 2.0–2.6 versus 0.1–1.2 for Health Care, Technology and Consumer Staples. Boeing has negative shareholder equity in every year from 2019 to 2024 and is the top-ranked risk in 5 of 10 years. NextEra is "distressed" by liquidity and leverage rules despite 18–31% net margins, which shows the limits of a one-size-fits-all score for regulated utilities.
4. **34 of 200 company-years (17%) scored high-risk.** The cases cluster around known events: GE's 2017–2019 restructuring, the 2020 oil crash (Exxon −12.4% net margin, interest coverage −23.9) and the 2020 travel collapse (Delta −72.4% net margin).

## Data notes and limitations
- **As-reported values.** Each figure is taken from the first 10-K that reported it, so it reflects what investors knew at the time, not later restatements.
- **Fiscal-year mapping.** A fiscal year is assigned to the calendar year it ends in. Fiscal years ending January–March are assigned to the prior year; for example, Walmart's year ending January 2025 counts as 2024.
- **Units.** All amounts are in USD millions.
- **EBIT.** This is reported operating income. For companies with no operating-income line (JNJ, PFE, XOM, CVX, GE, and Ford in some years), it is pre-tax income plus interest expense.
- **Interest expense.**
  - Caterpillar and GE tag only cash interest paid in XBRL, so that figure is used.
  - Apple stopped disclosing interest expense from FY2024, so its interest coverage is blank for 2024–2025.
- **Captive finance arms.** Ford and GM report consolidated figures that include Ford Credit and GM Financial. Those units borrow to fund customer loans, which inflates leverage and depresses coverage relative to the auto business alone. Ford's interest figure also switches between consolidated and automotive-only in FY2016 and FY2024–25.
- **GE current ratio.** GE did not present current assets or liabilities for FY2016–2018, so its current ratio is blank for those years.
- **Missing values.** A blank ratio scores 0 for that flag.
- **Macro data.** Values are annual averages of monthly or daily FRED data. CPI inflation is the average 12-month % change. GDP growth is compounded fourth-quarter-over-fourth-quarter real growth.
- **Sample size.** Ten years is a small sample for correlations, and the rate regimes overlap with COVID, so treat the macro findings as descriptive, not causal.

## Data sources
- Company financials: SEC EDGAR XBRL company facts API (10-K filings), data.sec.gov
- Economic data: FRED (Federal Reserve Bank of St. Louis): A191RL1Q225SBEA, UNRATE, FEDFUNDS, CPIAUCSL, BAA10Y
