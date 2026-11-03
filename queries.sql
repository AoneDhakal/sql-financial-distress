-- Corporate Financial Distress & Macroeconomic Analysis: analysis queries
-- Run after schema.sql and load_data.py. Each query answers one question.

-------------------------------------------------------------------------------
-- Q1. Data check: how many years of data does each company have?
-------------------------------------------------------------------------------
SELECT c.ticker, c.name, c.sector,
       COUNT(f.fiscal_year) AS years_of_data,
       MIN(f.fiscal_year)   AS first_year,
       MAX(f.fiscal_year)   AS last_year
FROM companies c
LEFT JOIN financials f ON f.ticker = c.ticker
GROUP BY c.ticker, c.name, c.sector
ORDER BY years_of_data, c.ticker;

-------------------------------------------------------------------------------
-- Q2. Core distress ratios for every company-year (saved as a view)
-------------------------------------------------------------------------------
DROP VIEW IF EXISTS ratios;
CREATE VIEW ratios AS
SELECT f.ticker,
       f.fiscal_year,
       ROUND(f.total_liabilities / NULLIF(f.total_equity, 0), 2)        AS debt_to_equity,
       ROUND(f.ebit / NULLIF(f.interest_expense, 0), 2)                 AS interest_coverage,
       ROUND(f.current_assets / NULLIF(f.current_liabilities, 0), 2)    AS current_ratio,
       ROUND(100.0 * f.net_income / NULLIF(f.revenue, 0), 1)            AS net_margin_pct,
       ROUND(100.0 * f.net_income / NULLIF(f.total_assets, 0), 1)       AS roa_pct,
       ROUND(f.operating_cash_flow / NULLIF(f.total_liabilities, 0), 2) AS cash_flow_to_debt
FROM financials f;

SELECT * FROM ratios ORDER BY ticker, fiscal_year;

-------------------------------------------------------------------------------
-- Q3. Year-over-year change with window functions (LAG)
-------------------------------------------------------------------------------
SELECT ticker,
       fiscal_year,
       interest_coverage,
       LAG(interest_coverage) OVER (PARTITION BY ticker ORDER BY fiscal_year) AS prev_coverage,
       ROUND(interest_coverage
             - LAG(interest_coverage) OVER (PARTITION BY ticker ORDER BY fiscal_year), 2) AS coverage_change,
       debt_to_equity,
       ROUND(debt_to_equity
             - LAG(debt_to_equity) OVER (PARTITION BY ticker ORDER BY fiscal_year), 2)    AS leverage_change
FROM ratios
ORDER BY ticker, fiscal_year;

-------------------------------------------------------------------------------
-- Q4. Rule-based distress score (0-5): one point per warning sign
--     Thresholds are common rules of thumb; state them in your write-up.
--     Negative equity (liabilities exceed assets) also counts as over-leveraged:
--     it makes debt-to-equity negative, which would otherwise slip under "> 2.0".
-------------------------------------------------------------------------------
DROP VIEW IF EXISTS distress;
CREATE VIEW distress AS
SELECT r.*,
       (CASE WHEN debt_to_equity > 2.0 OR debt_to_equity < 0 THEN 1 ELSE 0 END
      + CASE WHEN interest_coverage < 1.5 THEN 1 ELSE 0 END
      + CASE WHEN current_ratio     < 1.0 THEN 1 ELSE 0 END
      + CASE WHEN net_margin_pct    < 0   THEN 1 ELSE 0 END
      + CASE WHEN cash_flow_to_debt < 0.1 THEN 1 ELSE 0 END) AS distress_score
FROM ratios r;

SELECT ticker, fiscal_year, distress_score
FROM distress
ORDER BY fiscal_year, distress_score DESC;

-------------------------------------------------------------------------------
-- Q5. Rank companies by distress within each year (RANK window function)
-------------------------------------------------------------------------------
SELECT fiscal_year, ticker, distress_score,
       RANK() OVER (PARTITION BY fiscal_year ORDER BY distress_score DESC,
                                                     interest_coverage ASC) AS risk_rank
FROM distress
ORDER BY fiscal_year, risk_rank;

-------------------------------------------------------------------------------
-- Q6. Join company scores to the economy: is distress higher in tight years?
-------------------------------------------------------------------------------
SELECT m.year,
       m.fed_funds_pct,
       m.unemployment_pct,
       m.baa_spread_pct,
       ROUND(AVG(d.distress_score), 2)                          AS avg_distress_score,
       SUM(CASE WHEN d.distress_score >= 3 THEN 1 ELSE 0 END)   AS companies_high_risk,
       COUNT(*)                                                 AS companies
FROM distress d
JOIN macro m ON m.year = d.fiscal_year
GROUP BY m.year
ORDER BY m.year;

-------------------------------------------------------------------------------
-- Q7. Sector view: which sectors are most exposed when rates are high?
--     (CTE splits years into high- vs low-rate using the median fed funds rate)
-------------------------------------------------------------------------------
WITH ordered AS (
    SELECT fed_funds_pct,
           ROW_NUMBER() OVER (ORDER BY fed_funds_pct) AS rn,
           COUNT(*) OVER ()                           AS n
    FROM macro
),
median_rate AS (
    SELECT AVG(fed_funds_pct) AS med
    FROM ordered
    WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
),
regime AS (
    SELECT m.year,
           CASE WHEN m.fed_funds_pct >= (SELECT med FROM median_rate)
                THEN 'High-rate year' ELSE 'Low-rate year' END AS rate_regime
    FROM macro m
)
SELECT c.sector,
       g.rate_regime,
       ROUND(AVG(d.distress_score), 2)    AS avg_distress_score,
       ROUND(AVG(d.interest_coverage), 2) AS avg_interest_coverage,
       COUNT(*)                           AS company_years
FROM distress d
JOIN companies c ON c.ticker = d.ticker
JOIN regime g    ON g.year   = d.fiscal_year
GROUP BY c.sector, g.rate_regime
ORDER BY c.sector, g.rate_regime;

-------------------------------------------------------------------------------
-- Q8. Export table for the Power BI / Tableau dashboard
-------------------------------------------------------------------------------
DROP VIEW IF EXISTS dashboard_export;
CREATE VIEW dashboard_export AS
SELECT d.*, c.name, c.sector,
       m.gdp_growth_pct, m.unemployment_pct, m.fed_funds_pct,
       m.cpi_inflation_pct, m.baa_spread_pct
FROM distress d
JOIN companies c ON c.ticker = d.ticker
LEFT JOIN macro m ON m.year = d.fiscal_year;
