-- Warehouse-friendly starting point for the household feature model.
-- Adapt date functions and percentile syntax to your SQL engine.
WITH purchase_lines AS (
  SELECT
    household_key,
    basket_id,
    day,
    sales_value,
    ABS(COALESCE(retail_disc, 0)) + ABS(COALESCE(coupon_disc, 0))
      + ABS(COALESCE(coupon_match_disc, 0)) AS total_discount,
    FLOOR(day / 7) AS week_index
  FROM transaction_data
  WHERE sales_value > 0
), bounds AS (
  SELECT MAX(day) AS analysis_end_day, MAX(week_index) - 13 AS recent_week_cutoff
  FROM purchase_lines
), customer_features AS (
  SELECT
    p.household_key,
    MIN(p.day) AS first_day,
    MAX(p.day) AS last_day,
    b.analysis_end_day - MAX(p.day) AS recency_days,
    COUNT(DISTINCT p.basket_id) AS frequency,
    SUM(p.sales_value) AS monetary_value,
    SUM(p.total_discount) / NULLIF(SUM(p.sales_value + p.total_discount), 0) AS discount_share,
    SUM(CASE WHEN p.week_index > b.recent_week_cutoff THEN p.sales_value ELSE 0 END) AS sales_recent_13_weeks,
    SUM(CASE WHEN p.week_index <= b.recent_week_cutoff THEN p.sales_value ELSE 0 END) AS sales_prior_history
  FROM purchase_lines p CROSS JOIN bounds b
  GROUP BY p.household_key, b.analysis_end_day
)
SELECT *
FROM customer_features;
