"""Small, dated reference tables for deterministic price adjustment.

Method: convert the observed price to USD at the ECB reference rate for the
price date, then adjust with US CPI-U from the price period to TARGET_PERIOD.
Anything not in these tables gives null (never guessed).
"""

# US CPI-U, all items, US city average, not seasonally adjusted (1982-84=100).
# Series CUUR0000SA0, BLS Public Data API, retrieved 2026-09-29:
# https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0
# "2023" = mean of the 12 monthly 2023 values (304.702, matches BLS annual average).
CPI_SOURCE = "https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0"
CPI_U = {
    "2023": 304.702,
    "2024-10": 315.664,
    "2026-08": 334.980,
}
TARGET_PERIOD = "2026-08"  # latest CPI-U month published at retrieval

# ECB euro foreign exchange reference rates: units of currency per 1 EUR.
# https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A?startPeriod=2024-10-01&endPeriod=2024-10-01
# Retrieved 2026-09-29. Currencies the ECB does not publish (e.g. ARS, COP, TWD) have no rate.
FX_SOURCE = "https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A (ECB euro reference rates)"
ECB_PER_EUR = {
    "2024-10-01": {
        "EUR": 1.0, "AUD": 1.604, "BGN": 1.9558, "BRL": 6.0377, "CAD": 1.4986, "CHF": 0.9394,
        "CNY": 7.7807, "CZK": 25.272, "DKK": 7.4578, "GBP": 0.83193, "HKD": 8.6181,
        "HUF": 397.83, "IDR": 16847.95, "ILS": 4.1262, "INR": 92.931, "ISK": 149.9,
        "JPY": 159.37, "KRW": 1463.99, "MXN": 21.8444, "MYR": 4.6168, "NOK": 11.7305,
        "NZD": 1.7548, "PHP": 62.287, "PLN": 4.2853, "RON": 4.9759, "SEK": 11.3145,
        "SGD": 1.4268, "THB": 36.124, "TRY": 37.9185, "USD": 1.1086, "ZAR": 19.1585,
    },
}


def fx_to_usd(amount, currency, fx_date):
    """USD value using ECB cross rates on fx_date, or None if unknown."""
    rates = ECB_PER_EUR.get(fx_date)
    if currency == "USD":
        return amount
    if not rates or currency not in rates:
        return None
    return amount / rates[currency] * rates["USD"]


def fx_date_for(price_period):
    """Only use a rate table dated in the same month as the price."""
    for d in ECB_PER_EUR:
        if price_period and d.startswith(price_period):
            return d
    return None


def to_target_usd(amount_usd, price_period):
    base = CPI_U.get(price_period)
    if amount_usd is None or base is None:
        return None
    return amount_usd * CPI_U[TARGET_PERIOD] / base
