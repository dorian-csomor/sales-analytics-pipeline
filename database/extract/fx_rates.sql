-- Monthly average exchange rates (units per 1 EUR)
SELECT rate_month, UPPER(currency) AS currency, units_per_eur
FROM ops.fx_rates;
