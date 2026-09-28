-- Product catalogue, flagged with whether a cost history exists
-- (products created by the ERP migration have none - a hint they are duplicates).
SELECT p.product_id, p.sku, p.product_name, p.category, p.supplier,
       p.list_price_eur, p.is_active,
       EXISTS (SELECT 1 FROM ops.product_cost_history h
               WHERE h.product_id = p.product_id) AS has_cost_history
FROM ops.products p;
