-- =============================================================================
-- Source data profiling
-- Run these queries before writing any cleansing logic: they show what is
-- actually in the source system. Every issue found here has a matching
-- check in etl/transform.py and a line in the data quality report.
-- =============================================================================

-- 1. Order date formats in use
SELECT CASE
         WHEN order_date ~ '^\d{4}-\d{2}-\d{2}T'     THEN 'YYYY-MM-DDTHH:MI:SS'
         WHEN order_date ~ '^\d{4}-\d{2}-\d{2}$'     THEN 'YYYY-MM-DD'
         WHEN order_date ~ '^\d{4}\.\d{2}\.\d{2}\.$' THEN 'YYYY.MM.DD.'
         WHEN order_date ~ '^\d{2}\.\d{2}\.\d{4}$'   THEN 'DD.MM.YYYY'
         WHEN order_date ~ '^\d{2}/\d{2}/\d{4}$'     THEN 'DD/MM/YYYY'
         ELSE 'other'
       END AS date_format,
       COUNT(*) AS orders
FROM ops.orders
GROUP BY 1
ORDER BY 2 DESC;

-- 2. Implausible years
SELECT order_id, order_number, order_date, created_at
FROM ops.orders
WHERE substring(order_date FROM '(\d{4})')::int NOT BETWEEN 2015 AND EXTRACT(YEAR FROM CURRENT_DATE);

-- 3. Status and currency spellings
SELECT 'status' AS field, status AS value, COUNT(*) FROM ops.orders GROUP BY status
UNION ALL
SELECT 'currency', COALESCE(currency, '<NULL>'), COUNT(*) FROM ops.orders GROUP BY currency
ORDER BY 1, 3 DESC;

-- 4. Duplicate business keys
SELECT order_number, COUNT(*) AS copies, MIN(created_at) AS first_created, MAX(created_at) AS last_created
FROM ops.orders
GROUP BY order_number
HAVING COUNT(*) > 1
ORDER BY copies DESC, order_number;

-- 5. Referential integrity (no foreign keys in the source)
SELECT 'orders without customer' AS check, COUNT(*)
FROM ops.orders o LEFT JOIN ops.customers c ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
UNION ALL
SELECT 'lines without product', COUNT(*)
FROM ops.order_lines l LEFT JOIN ops.products p ON p.product_id = l.product_id
WHERE p.product_id IS NULL
UNION ALL
SELECT 'products without cost history', COUNT(*)
FROM ops.products p
WHERE NOT EXISTS (SELECT 1 FROM ops.product_cost_history h WHERE h.product_id = p.product_id);

-- 6. Order line value checks
SELECT COUNT(*) FILTER (WHERE unit_price IS NULL)  AS missing_price,
       COUNT(*) FILTER (WHERE quantity <= 0)       AS non_positive_qty,
       COUNT(*) FILTER (WHERE discount_pct > 1)    AS discount_as_whole_pct,
       COUNT(*) FILTER (WHERE discount_pct < 0)    AS negative_discount
FROM ops.order_lines;

-- 7. Prices far above list price (possible currency mislabel)
SELECT o.order_id, o.currency, p.sku, l.unit_price, p.list_price_eur,
       ROUND(l.unit_price / NULLIF(p.list_price_eur, 0), 1) AS price_to_list_ratio
FROM ops.order_lines l
JOIN ops.orders o   ON o.order_id = l.order_id
JOIN ops.products p ON p.product_id = l.product_id
WHERE UPPER(TRIM(o.currency)) = 'EUR'
  AND l.unit_price > 20 * p.list_price_eur
ORDER BY price_to_list_ratio DESC;

-- 8. Near-duplicate SKUs and customers
SELECT UPPER(REGEXP_REPLACE(sku, '[^A-Za-z0-9]', '', 'g')) AS sku_key,
       STRING_AGG(product_id::text || ':' || sku, ', ') AS variants
FROM ops.products
GROUP BY 1 HAVING COUNT(*) > 1;

SELECT LOWER(REGEXP_REPLACE(TRIM(customer_name), '[^A-Za-z0-9 ]', '', 'g')) AS name_key, city,
       STRING_AGG(customer_id::text, ', ') AS ids
FROM ops.customers
GROUP BY 1, 2 HAVING COUNT(*) > 1;

-- 9. Free-text countries
SELECT COALESCE(country, '<NULL>') AS country, COUNT(*)
FROM ops.customers
GROUP BY 1
ORDER BY 2 DESC;

-- 10. Test and demo accounts
SELECT customer_id, customer_name
FROM ops.customers
WHERE customer_name ~* '(test|demo|do not use)';
