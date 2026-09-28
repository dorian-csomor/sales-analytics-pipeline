-- Purchase cost validity periods, used for an as-of join on the order date
SELECT product_id, valid_from, valid_to, unit_cost_eur
FROM ops.product_cost_history
ORDER BY product_id, valid_from;
