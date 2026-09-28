-- Customer master: full extract. Cleansing (names, countries, duplicates) happens in Python.
SELECT customer_id, customer_name, segment, city, country, assigned_rep_id, created_at
FROM ops.customers;
