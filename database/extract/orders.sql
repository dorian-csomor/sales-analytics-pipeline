-- Order headers. Dates are extracted as raw text on purpose: the source mixes
-- five formats, and parsing them in Python lets us log exactly what failed.
SELECT order_id, order_number, customer_id, rep_id,
       order_date AS order_date_raw,
       ship_date  AS ship_date_raw,
       status, currency, sales_channel, created_at
FROM ops.orders;
