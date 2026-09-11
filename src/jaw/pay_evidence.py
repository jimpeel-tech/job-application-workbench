from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PayEvidence:
    pay_min: str
    pay_max: str
    currency: str
    period: str
    evidence: str
    confidence: float
    rule: str


@dataclass(frozen=True)
class _Candidate:
    score: int
    start: int
    end: int
    pay: PayEvidence


_PAY_CONTEXT = re.compile(
    r"\b(?:base\s+(?:pay|salary)|salary\s+range|pay\s+range|hiring\s+range|"
    r"compensation(?:\s+range|\s+package)?|expected\s+compensation|target\s+salary|"
    r"wage|pay\s+and\s+benefits)\b",
    re.IGNORECASE,
)
_BAD_CONTEXT = re.compile(
    r"\b(?:deal\s+sizes?|transactional\s+solutions?|project\s+budget|revenue|"
    r"funding|valuation|assets?\s+under\s+management)\b",
    re.IGNORECASE,
)
_SECONDARY_LOCATION = re.compile(
    r"\b(?:different\s+range\s+applicable|specific\s+work\s+locations?|"
    r"san\s+francisco\s+bay|new\s+york\s+city\s+metropolitan)\b",
    re.IGNORECASE,
)
_STRUCTURED_BANDS = re.compile(
    r"\b(?:US\s+)?Zone\s+[A-Z0-9]+\b|"
    r"\bLevel\s+\d+\b|"
    r"\b(?:National|Premium)\s+Market\b",
    re.IGNORECASE,
)


def analyze_pay(content: str) -> PayEvidence | None:
    """Return the strongest compensation range while ignoring unrelated money."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    candidates: list[_Candidate] = []

    # Explicit min-mid-max bands are one range, not two overlapping ranges.
    three_point = re.compile(
        r"(?:(?P<currency>USD|CAD)\s*)?\$?\s*(?P<a>\d[\d,]*(?:\.\d+)?)\s*"
        r"[-–—]\s*\$?\s*(?P<b>\d[\d,]*(?:\.\d+)?)\s*"
        r"[-–—]\s*\$?\s*(?P<c>\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for match in three_point.finditer(text):
        low = _amount(match.group("a"), "")
        high = _amount(match.group("c"), "")
        if not _plausible(low, high, "year"):
            continue
        context = _window(text, match.start(), match.end())
        score = 15 + _context_score(context)
        candidates.append(
            _Candidate(
                score,
                match.start(),
                match.end(),
                PayEvidence(
                    pay_min=_number(low),
                    pay_max=_number(high),
                    currency=(match.group("currency") or _currency(context)),
                    period="year",
                    evidence=_line(text, match.start(), match.end()),
                    confidence=0.99,
                    rule="min_mid_max_salary_range",
                ),
            )
        )

    # Prose such as "ranges from $150,000/year ... up to $230,000/year".
    prose = re.compile(
        r"\branges?\s+from\s+\$\s*(?P<low>\d[\d,]*(?:\.\d+)?)"
        r"\s*(?:/\s*|per\s+)?(?P<p1>hour|hr|year|yr)?[^.\n]{0,180}?"
        r"\bup\s+to\s+\$\s*(?P<high>\d[\d,]*(?:\.\d+)?)"
        r"\s*(?:/\s*|per\s+)?(?P<p2>hour|hr|year|yr)?",
        re.IGNORECASE,
    )
    for match in prose.finditer(text):
        period = _period(match.group("p1") or match.group("p2"), match.group(0))
        low = _amount(match.group("low"), "")
        high = _amount(match.group("high"), "")
        if not _plausible(low, high, period):
            continue
        context = _window(text, match.start(), match.end())
        candidates.append(
            _Candidate(
                16 + _context_score(context),
                match.start(),
                match.end(),
                PayEvidence(
                    pay_min=_number(low),
                    pay_max=_number(high),
                    currency=_currency(context),
                    period=period,
                    evidence=_line(text, match.start(), match.end()),
                    confidence=0.99,
                    rule="prose_salary_range",
                ),
            )
        )

    # "between $205,000 and $275,000" is common in prose-heavy postings.
    between = re.compile(
        r"\bbetween\s+\$\s*(?P<low>\d[\d,]*(?:\.\d+)?)\s+and\s+"
        r"\$\s*(?P<high>\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for match in between.finditer(text):
        low = _amount(match.group("low"), "")
        high = _amount(match.group("high"), "")
        context = _window(text, match.start(), match.end())
        period = _period(None, context, high)
        if not _plausible(low, high, period):
            continue
        candidates.append(
            _Candidate(
                15 + _context_score(context),
                match.start(),
                match.end(),
                PayEvidence(
                    pay_min=_number(low),
                    pay_max=_number(high),
                    currency=_currency(context),
                    period=period,
                    evidence=_line(text, match.start(), match.end()),
                    confidence=0.98,
                    rule="between_salary_range",
                ),
            )
        )

    # Market bands sometimes annotate each endpoint before the period marker.
    annotated = re.compile(
        r"\$\s*(?P<low>\d[\d,]*(?:\.\d+)?)\s*(?:\([^\n)]{0,80}\))?\s*"
        r"(?:-|–|—|to)\s*\$?\s*(?P<high>\d[\d,]*(?:\.\d+)?)\s*"
        r"(?:\([^\n)]{0,80}\))?\s*"
        r"(?P<period>annually|annual|per\s+year|/yr)?",
        re.IGNORECASE,
    )
    for match in annotated.finditer(text):
        low = _amount(match.group("low"), "")
        high = _amount(match.group("high"), "")
        context = _window(text, match.start(), match.end())
        period = _period(match.group("period"), context, high)
        if not _plausible(low, high, period):
            continue
        candidates.append(
            _Candidate(
                13 + _context_score(context),
                match.start(),
                match.end(),
                PayEvidence(
                    pay_min=_number(low),
                    pay_max=_number(high),
                    currency=_currency(context),
                    period=period,
                    evidence=_line(text, match.start(), match.end()),
                    confidence=0.97,
                    rule="annotated_salary_range",
                ),
            )
        )

    range_pattern = re.compile(
        r"(?:(?P<code1pre>USD|CAD)\s*)?(?P<dollar1>\$)?\s*"
        r"(?P<low>\d[\d,]*(?:\.\d+)?)(?P<scale1>\s*[kKmM])?\s*"
        r"(?P<code1post>USD|CAD)?\s*(?:-|–|—|to)\s*"
        r"(?:(?P<code2pre>USD|CAD)\s*)?(?P<dollar2>\$)?\s*"
        r"(?P<high>\d[\d,]*(?:\.\d+)?)(?P<scale2>\s*[kKmM])?\s*"
        r"(?P<code2post>USD|CAD)?\s*"
        r"(?:/\s*|per\s+)?(?P<period>hour|hr|year|yr|annum|month|week|annually)?",
        re.IGNORECASE,
    )
    for match in range_pattern.finditer(text):
        scale1, scale2 = match.group("scale1"), match.group("scale2")
        low, high = _range_amounts(
            match.group("low"), scale1, match.group("high"), scale2
        )
        context = _window(text, match.start(), match.end())
        line = _line(text, match.start(), match.end())
        prefix = " ".join(text[max(0, match.start() - 180):match.start()].split())
        period = _period(match.group("period"), context, high)
        if not _plausible(low, high, period):
            continue
        codes = (
            match.group("code1pre"),
            match.group("code1post"),
            match.group("code2pre"),
            match.group("code2post"),
        )
        explicit_money = bool(
            match.group("dollar1")
            or match.group("dollar2")
            or any(codes)
            or scale1
            or scale2
            or _PAY_CONTEXT.search(line)
        )
        if not explicit_money or _BAD_CONTEXT.search(line):
            continue

        score = 5 + _context_score(context)
        if match.group("dollar1") or match.group("dollar2") or any(codes):
            score += 3
        if scale1 or scale2:
            score += 2
        if match.group("period"):
            score += 3
        if _SECONDARY_LOCATION.search(prefix):
            score -= 6
        if score < 4:
            continue
        currency = next((code for code in codes if code), _currency(context)).upper()
        candidates.append(
            _Candidate(
                score,
                match.start(),
                match.end(),
                PayEvidence(
                    pay_min=_number(low),
                    pay_max=_number(high),
                    currency=currency,
                    period=period,
                    evidence=line,
                    confidence=min(0.99, 0.80 + score * 0.01),
                    rule="contextual_salary_range",
                ),
            )
        )

    # Explicit-period singles and strongly signaled annual amounts.
    single = re.compile(
        r"(?P<upto>\bup\s+to\s+)?\$\s*(?P<amount>\d[\d,]*(?:\.\d+)?)"
        r"(?P<scale>\s*[kKmM])?\s*(?:/\s*|per\s+)?"
        r"(?P<period>hour|hr|year|yr|annum|month|week|annually)?\b",
        re.IGNORECASE,
    )
    for match in single.finditer(text):
        amount = _amount(match.group("amount"), match.group("scale"))
        context = _window(text, match.start(), match.end())
        line = _line(text, match.start(), match.end())
        period = _period(match.group("period"), context, amount)
        strong_signal = bool(
            match.group("period")
            or match.group("upto")
            or _PAY_CONTEXT.search(line)
            or (amount >= 10_000 and _PAY_CONTEXT.search(context))
        )
        if (
            not strong_signal
            or not _plausible(amount, amount, period)
            or _BAD_CONTEXT.search(line)
        ):
            continue
        score = 9 + _context_score(context)
        if match.group("upto"):
            score += 2
        candidates.append(
            _Candidate(
                score,
                match.start(),
                match.end(),
                PayEvidence(
                    pay_min=_number(amount),
                    pay_max=_number(amount),
                    currency=_currency(context),
                    period=period,
                    evidence=line,
                    confidence=min(0.97, 0.80 + score * 0.01),
                    rule="contextual_single_pay",
                ),
            )
        )

    if not candidates:
        return None

    envelope = _structured_envelope(text, candidates)
    if envelope is not None:
        return envelope
    return max(candidates, key=lambda item: (item.score, -item.start)).pay


def _structured_envelope(text: str, candidates: list[_Candidate]) -> PayEvidence | None:
    annual = [
        candidate
        for candidate in candidates
        if candidate.pay.period == "year"
        and float(candidate.pay.pay_min) >= 10_000
        and candidate.pay.pay_min != candidate.pay.pay_max
    ]
    unique: dict[tuple[str, str, str], _Candidate] = {}
    for candidate in annual:
        key = (
            candidate.pay.pay_min,
            candidate.pay.pay_max,
            candidate.pay.currency,
        )
        current = unique.get(key)
        if current is None or candidate.score > current.score:
            unique[key] = candidate
    bands = list(unique.values())
    if len(bands) < 2:
        return None

    if _SECONDARY_LOCATION.search(text) and re.search(
        r"\bdifferent\s+range\s+applicable\b", text, re.IGNORECASE
    ):
        return None

    repeated_geo = len(
        re.findall(r"salary\s+range\s+for\s+this\s+role\s+in\b", text, re.IGNORECASE)
    ) >= 2
    if not (_STRUCTURED_BANDS.search(text) or repeated_geo):
        return None

    low = min(float(candidate.pay.pay_min) for candidate in bands)
    high = max(float(candidate.pay.pay_max) for candidate in bands)
    currencies = {candidate.pay.currency for candidate in bands}
    currency = currencies.pop() if len(currencies) == 1 else "USD"
    return PayEvidence(
        pay_min=_number(low),
        pay_max=_number(high),
        currency=currency,
        period="year",
        evidence="Multiple explicit salary bands",
        confidence=0.99,
        rule="structured_salary_band_envelope",
    )


def _context_score(context: str) -> int:
    score = 0
    if _PAY_CONTEXT.search(context):
        score += 7
    if re.search(r"\b(?:per\s+year|per\s+hour|annually|annual|/yr|/hour|/hr)\b", context, re.I):
        score += 3
    if re.search(r"\b(?:equity|bonus|benefits|total\s+compensation)\b", context, re.I):
        score += 1
    return score


def _range_amounts(
    low_value: str,
    low_scale: str | None,
    high_value: str,
    high_scale: str | None,
) -> tuple[float, float]:
    raw_low = float(str(low_value).replace(",", ""))
    raw_high = float(str(high_value).replace(",", ""))
    shared_low_scale = low_scale
    shared_high_scale = high_scale
    if not low_scale and high_scale and raw_low < 10_000:
        shared_low_scale = high_scale
    if low_scale and not high_scale and raw_high < 10_000:
        shared_high_scale = low_scale
    return (
        _amount(low_value, shared_low_scale),
        _amount(high_value, shared_high_scale),
    )


def _amount(value: str, scale: str | None) -> float:
    amount = float(str(value).replace(",", ""))
    marker = str(scale or "").strip().casefold()
    if marker == "k":
        amount *= 1_000
    elif marker == "m":
        amount *= 1_000_000
    return amount


def _period(value: str | None, context: str, high: float | None = None) -> str:
    lowered = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    if lowered in {"hour", "hr"}:
        return "hour"
    if lowered in {"year", "yr", "annum", "annually", "annual", "per year"}:
        return "year"
    if lowered == "month":
        return "month"
    if lowered == "week":
        return "week"
    if re.search(r"\b(?:hour|hourly|/hr)\b", context, re.I):
        return "hour"
    if re.search(r"\b(?:salary|annual|annum|per\s+year|/yr)\b", context, re.I):
        return "year"
    return "year" if high is not None and high >= 10_000 else ""


def _plausible(low: float, high: float, period: str) -> bool:
    if low <= 0 or high < low:
        return False
    if period == "hour":
        return high <= 2_000
    if period == "year":
        return 10_000 <= low <= 1_500_000 and high <= 1_500_000
    return high <= 1_500_000


def _currency(context: str) -> str:
    return "CAD" if re.search(r"\bCAD\b", context, re.I) else "USD"


def _number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _window(text: str, start: int, end: int) -> str:
    return " ".join(text[max(0, start - 180):min(len(text), end + 180)].split())


def _line(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    return " ".join(text[line_start:line_end].split())[:360]


__all__ = ["PayEvidence", "analyze_pay"]
