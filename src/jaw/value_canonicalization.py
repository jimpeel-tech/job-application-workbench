from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_AMOUNT_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[$€£]|US\$|USD|EUR|GBP)?\s*"
    r"(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<suffix>[kKmM])?(?![A-Za-z])"
)

_PERIOD_PATTERNS = (
    ("year", re.compile(r"(?:/|per\s+)?(?:year|yr|yearly|annual|annually|annum)\b", re.I)),
    ("month", re.compile(r"(?:/|per\s+)?(?:month|mo|monthly)\b", re.I)),
    ("week", re.compile(r"(?:/|per\s+)?(?:week|wk|weekly)\b", re.I)),
    ("day", re.compile(r"(?:/|per\s+)?(?:day|daily)\b", re.I)),
    ("hour", re.compile(r"(?:/|per\s+)?(?:hour|hr|hourly)\b", re.I)),
)

_STATE_NAME_TO_CODE = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
}
_STATE_NAME_PATTERN = re.compile(
    r",\s*(" + "|".join(re.escape(name) for name in _STATE_NAME_TO_CODE) + r")\b",
    re.IGNORECASE,
)
_ZIP_SUFFIX = re.compile(r"\s+\d{5}(?:-\d{4})?(?=\s*(?:,|$))")


def canonical_capture_value(field: str, value: str) -> str:
    """Return a stable comparison key without changing the displayed value."""
    text = " ".join(str(value).split()).strip()
    if not text:
        return ""
    normalized_field = str(field).strip().casefold()
    if normalized_field == "pay":
        pay = _canonical_pay(text)
        if pay:
            return pay
    if normalized_field == "location":
        return _canonical_location(text)
    return text.casefold()


def _canonical_location(value: str) -> str:
    text = _ZIP_SUFFIX.sub("", value)

    def replace_state(match: re.Match[str]) -> str:
        code = _STATE_NAME_TO_CODE[match.group(1).casefold()]
        return f", {code}"

    text = _STATE_NAME_PATTERN.sub(replace_state, text)
    text = re.sub(r"\s*,\s*", ", ", text)
    return " ".join(text.split()).strip().casefold()


def _canonical_pay(value: str) -> str:
    currency = _currency(value)
    period = _period(value)
    amounts = [_amount(match) for match in _AMOUNT_RE.finditer(value)]
    amounts = [amount for amount in amounts if amount is not None]
    if not amounts:
        return ""

    # Range punctuation/order is presentation, not meaning. Keep at most the
    # first two monetary values because Smart Capture Pay is a scalar/range field.
    amounts = amounts[:2]
    if len(amounts) == 2 and amounts[1] < amounts[0]:
        amounts.reverse()

    amount_key = ":".join(_decimal_text(amount) for amount in amounts)
    return f"pay|currency={currency}|amounts={amount_key}|period={period}"


def _amount(match: re.Match[str]) -> Decimal | None:
    raw = match.group("number").replace(",", "")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None
    suffix = str(match.group("suffix") or "").casefold()
    if suffix == "k":
        amount *= Decimal(1000)
    elif suffix == "m":
        amount *= Decimal(1_000_000)
    return amount


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal(1)))
    return format(normalized, "f").rstrip("0").rstrip(".")


def _currency(value: str) -> str:
    folded = value.casefold()
    if "$" in value or re.search(r"\b(?:usd|us dollars?)\b", folded):
        return "USD"
    if "€" in value or re.search(r"\beur\b", folded):
        return "EUR"
    if "£" in value or re.search(r"\bgbp\b", folded):
        return "GBP"
    return ""


def _period(value: str) -> str:
    for canonical, pattern in _PERIOD_PATTERNS:
        if pattern.search(value):
            return canonical
    return ""


__all__ = ["canonical_capture_value"]
