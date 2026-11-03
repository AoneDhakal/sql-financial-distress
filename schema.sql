-- Corporate Financial Distress & Macroeconomic Analysis (SQL version)
-- Database: SQLite (works in DB Browser for SQLite or Python's sqlite3)

DROP TABLE IF EXISTS financials;
DROP TABLE IF EXISTS macro;
DROP TABLE IF EXISTS companies;

-- One row per company
CREATE TABLE companies (
    ticker      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sector      TEXT
);

-- One row per company per fiscal year (amounts in USD millions)
CREATE TABLE financials (
    ticker               TEXT    NOT NULL REFERENCES companies(ticker),
    fiscal_year          INTEGER NOT NULL,
    revenue              REAL,
    net_income           REAL,
    ebit                 REAL,     -- operating income
    interest_expense     REAL,
    total_assets         REAL,
    total_liabilities    REAL,
    total_equity         REAL,
    current_assets       REAL,
    current_liabilities  REAL,
    operating_cash_flow  REAL,
    PRIMARY KEY (ticker, fiscal_year)
);

-- One row per year of FRED data (annual averages)
CREATE TABLE macro (
    year               INTEGER PRIMARY KEY,
    gdp_growth_pct     REAL,   -- FRED: A191RL1Q225SBEA (real GDP growth)
    unemployment_pct   REAL,   -- FRED: UNRATE
    fed_funds_pct      REAL,   -- FRED: FEDFUNDS
    cpi_inflation_pct  REAL,   -- FRED: CPIAUCSL, % change from a year ago
    baa_spread_pct     REAL    -- FRED: BAA10Y (corporate credit spread)
);
