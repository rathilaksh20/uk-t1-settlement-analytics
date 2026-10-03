-- =====================================================================
-- Settlement KPI queries (all data is SYNTHETIC)
-- Run one query at a time in pgAdmin: highlight it, then press the play button.
-- =====================================================================

-- Q1. Headline KPIs
SELECT
    COUNT(*)                                                             AS total_trades,
    ROUND(SUM(t.trade_value))                                            AS total_notional_gbp,
    ROUND(100.0 * COUNT(*) FILTER (WHERE s.settlement_status = 'READY_TO_SETTLE') / COUNT(*), 1) AS ready_pct,
    COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK')              AS at_risk_trades,
    ROUND(100.0 * COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM exceptions e WHERE e.trade_id = t.trade_id)) / COUNT(*), 1) AS trades_with_exception_pct,
    ROUND(SUM(t.trade_value) FILTER (WHERE s.settlement_status = 'AT_RISK')) AS at_risk_notional_gbp
FROM trades t
JOIN settlement_status s USING (trade_id);

-- Q2. Daily at-risk rate with a rolling 7-trading-day rate (window functions)
WITH daily AS (
    SELECT t.trade_datetime::date AS trade_day,
           COUNT(*)                                                  AS trades,
           COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK')   AS at_risk
    FROM trades t JOIN settlement_status s USING (trade_id)
    GROUP BY 1
)
SELECT trade_day, trades, at_risk,
       ROUND(100.0 * at_risk / trades, 1) AS daily_at_risk_pct,
       ROUND(100.0 * SUM(at_risk) OVER w / SUM(trades) OVER w, 1) AS rolling_7d_at_risk_pct
FROM daily
WINDOW w AS (ORDER BY trade_day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
ORDER BY trade_day;

-- Q3. Exceptions by type and severity
SELECT exception_type,
       COUNT(*)                                      AS total,
       COUNT(*) FILTER (WHERE severity = 'HIGH')     AS high,
       COUNT(*) FILTER (WHERE severity = 'MEDIUM')   AS medium,
       COUNT(*) FILTER (WHERE severity = 'LOW')      AS low,
       COUNT(*) FILTER (WHERE resolution_status = 'OPEN') AS still_open
FROM exceptions
GROUP BY 1
ORDER BY total DESC;

-- Q4. Resolution time (elapsed hours): average, median and 90th percentile by type
SELECT exception_type,
       COUNT(*) AS resolved,
       ROUND(AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600)::numeric, 1) AS avg_hours,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600))::numeric, 1) AS median_hours,
       ROUND((PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600))::numeric, 1) AS p90_hours
FROM exceptions
WHERE resolution_status = 'RESOLVED'
GROUP BY 1
ORDER BY avg_hours DESC;

-- Q5. Ageing of open exceptions, measured against the latest exception timestamp
WITH as_of AS (SELECT MAX(created_at) AS ts FROM exceptions)
SELECT CASE
           WHEN a.ts - e.created_at < INTERVAL '1 day'  THEN '0-1 days'
           WHEN a.ts - e.created_at < INTERVAL '2 days' THEN '1-2 days'
           WHEN a.ts - e.created_at < INTERVAL '5 days' THEN '2-5 days'
           ELSE '5+ days'
       END AS age_bucket,
       COUNT(*) AS open_exceptions
FROM exceptions e CROSS JOIN as_of a
WHERE e.resolution_status = 'OPEN'
GROUP BY 1
ORDER BY MIN(a.ts - e.created_at);

-- Q6. Counterparties ranked by at-risk value, with share of the total
WITH cp AS (
    SELECT c.counterparty_name,
           COUNT(*) AS trades,
           COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK') AS at_risk_trades,
           COALESCE(SUM(t.trade_value) FILTER (WHERE s.settlement_status = 'AT_RISK'), 0) AS at_risk_value
    FROM trades t
    JOIN settlement_status s USING (trade_id)
    JOIN counterparties c USING (counterparty_id)
    GROUP BY c.counterparty_name
)
SELECT RANK() OVER (ORDER BY at_risk_value DESC) AS rnk,
       counterparty_name,
       trades,
       at_risk_trades,
       ROUND(100.0 * at_risk_trades / trades, 1) AS at_risk_pct,
       ROUND(at_risk_value) AS at_risk_value_gbp,
       ROUND(100.0 * at_risk_value / SUM(at_risk_value) OVER (), 1) AS share_of_at_risk_value_pct
FROM cp
ORDER BY rnk;

-- Q7. Concentration: share of exceptions coming from the top 5 counterparties
WITH per_cp AS (
    SELECT t.counterparty_id, COUNT(*) AS n
    FROM exceptions e JOIN trades t USING (trade_id)
    GROUP BY 1
), ranked AS (
    SELECT n, ROW_NUMBER() OVER (ORDER BY n DESC) AS rn FROM per_cp
)
SELECT ROUND(100.0 * SUM(n) FILTER (WHERE rn <= 5) / SUM(n), 1) AS top5_share_pct
FROM ranked;

-- Q8. Stage lateness: share of trades late at each stage
SELECT event_type,
       COUNT(*) AS trades,
       COUNT(*) FILTER (WHERE event_status = 'LATE') AS late,
       ROUND(100.0 * COUNT(*) FILTER (WHERE event_status = 'LATE') / COUNT(*), 1) AS late_pct
FROM settlement_events
WHERE event_type <> 'TRADE_CREATED'
GROUP BY 1
ORDER BY late_pct DESC;

-- Q9. Time-of-day effect: at-risk rate by the hour the trade was executed
SELECT EXTRACT(HOUR FROM t.trade_datetime)::int AS trade_hour,
       COUNT(*) AS trades,
       ROUND(100.0 * COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK') / COUNT(*), 1) AS at_risk_pct
FROM trades t JOIN settlement_status s USING (trade_id)
GROUP BY 1
ORDER BY 1;

-- Q10. Hidden reliability versus observed at-risk rate (a check on the simulation, NOT a feature source)
SELECT p.counterparty_id, p.reliability, p.responsiveness,
       COUNT(*) AS trades,
       ROUND(100.0 * COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK') / COUNT(*), 1) AS at_risk_pct
FROM counterparty_profile p
JOIN trades t USING (counterparty_id)
JOIN settlement_status s USING (trade_id)
GROUP BY 1, 2, 3
ORDER BY at_risk_pct DESC;