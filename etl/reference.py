"""Reference mappings used by the cleansing rules."""

# canonical country -> ISO code and home currency
COUNTRIES = {
    "Hungary":  {"code": "HU", "currency": "HUF"},
    "Austria":  {"code": "AT", "currency": "EUR"},
    "Czechia":  {"code": "CZ", "currency": "CZK"},
    "Slovakia": {"code": "SK", "currency": "EUR"},
    "Romania":  {"code": "RO", "currency": "RON"},
}

# every spelling seen in the source (lower-cased, trimmed) -> canonical name
COUNTRY_ALIASES = {
    "hungary": "Hungary", "hu": "Hungary", "magyarország": "Hungary", "magyarorszag": "Hungary",
    "austria": "Austria", "at": "Austria", "österreich": "Austria", "osterreich": "Austria",
    "czechia": "Czechia", "cz": "Czechia", "czech republic": "Czechia",
    "slovakia": "Slovakia", "sk": "Slovakia", "slovak republic": "Slovakia",
    "romania": "Romania", "ro": "Romania", "românia": "Romania",
}

STATUS_ALIASES = {
    "delivered": "Delivered",
    "shipped": "Shipped",
    "open": "Open",
    "cancelled": "Cancelled",
    "canceled": "Cancelled",
}

CURRENCY_ALIASES = {"FT": "HUF", "HUF": "HUF", "EUR": "EUR", "€": "EUR", "CZK": "CZK", "KČ": "CZK", "RON": "RON", "LEI": "RON"}

# Date formats found in ops.orders.order_date, tried in this order
ORDER_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",   # web shop / EDI timestamp
    "%Y-%m-%d",            # sales rep app
    "%Y.%m.%d.",           # Hungarian manual entry
    "%d.%m.%Y",            # Austrian / Czech / Slovak manual entry
    "%d/%m/%Y",            # Romanian manual entry
]
