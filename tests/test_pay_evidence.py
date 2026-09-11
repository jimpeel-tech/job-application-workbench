from jaw.pay_evidence import analyze_pay
from jaw.parser_resolution import resolve_parser_evidence


def test_k_suffix_salary_range_is_normalized():
    evidence = analyze_pay("The expected compensation range is $150k - $250k + equity + benefits.")

    assert evidence is not None
    assert evidence.pay_min == "150000"
    assert evidence.pay_max == "250000"
    assert evidence.currency == "USD"
    assert evidence.period == "year"


def test_compact_k_salary_line_is_normalized_without_salary_word():
    evidence = analyze_pay("About Us:\n$150K – $185K • Offers Equity • Offers Bonus")

    assert evidence is not None
    assert evidence.pay_min == "150000"
    assert evidence.pay_max == "185000"
    assert evidence.period == "year"


def test_shared_k_suffix_applies_to_both_range_endpoints():
    evidence = analyze_pay("Why This Role Matters\n175-200k\nYou will define how systems evolve.")

    assert evidence is not None
    assert evidence.pay_min == "175000"
    assert evidence.pay_max == "200000"


def test_currency_after_amount_is_supported():
    evidence = analyze_pay(
        "Your base salary will be determined based on location. "
        "The base salary range is 320,000 USD - 488,750 USD."
    )

    assert evidence is not None
    assert evidence.pay_min == "320000"
    assert evidence.pay_max == "488750"
    assert evidence.currency == "USD"
    assert evidence.period == "year"


def test_range_candidate_beats_overlapping_single_endpoint():
    evidence = analyze_pay("Salary Range: $100,000 USD - $165,000 USD")

    assert evidence is not None
    assert evidence.pay_min == "100000"
    assert evidence.pay_max == "165000"


def test_min_mid_max_salary_uses_outer_bounds():
    evidence = analyze_pay(
        "We estimate the base salary will be in this range from (min-mid-max, USD):\n"
        "$166,000 - $237,200 - $308,400"
    )

    assert evidence is not None
    assert evidence.pay_min == "166000"
    assert evidence.pay_max == "308400"


def test_prose_from_up_to_salary_range_is_supported():
    evidence = analyze_pay(
        "The US base salary for this position ranges from $150,000/year in our lowest "
        "geographic market up to $230,000/year in our highest geographic market."
    )

    assert evidence is not None
    assert evidence.pay_min == "150000"
    assert evidence.pay_max == "230000"
    assert evidence.period == "year"


def test_between_salary_range_is_supported():
    evidence = analyze_pay(
        "The salary range for candidates in applicable jurisdictions is between "
        "$205,000 and $275,000."
    )

    assert evidence is not None
    assert evidence.pay_min == "205000"
    assert evidence.pay_max == "275000"
    assert evidence.period == "year"


def test_up_to_k_single_salary_is_supported():
    evidence = analyze_pay(
        "Leading CNCF Start Up Hiring for Senior SRE | Up to $200k + Equity | Remote"
    )

    assert evidence is not None
    assert evidence.pay_min == "200000"
    assert evidence.pay_max == "200000"
    assert evidence.period == "year"


def test_unrelated_deal_size_does_not_pollute_salary_range():
    evidence = analyze_pay(
        "deal sizes range from transactional solutions of $2-5M.\n"
        "Pay and Benefits\nThe pay range for this position is $148200.00 - $222400.00/yr."
    )

    assert evidence is not None
    assert evidence.pay_min == "148200"
    assert evidence.pay_max == "222400"


def test_primary_us_range_beats_special_location_range():
    evidence = analyze_pay(
        "The typical base pay range for this role across the U.S. is USD $139,900 - "
        "$274,800 per year. There is a different range applicable to specific work "
        "locations, within the San Francisco Bay area and New York City metropolitan "
        "area, and the base pay range for this role in those locations is USD $188,000 "
        "- $304,200 per year."
    )

    assert evidence is not None
    assert evidence.pay_min == "139900"
    assert evidence.pay_max == "274800"


def test_zone_salary_bands_use_outer_envelope():
    evidence = analyze_pay(
        "Compensation\n"
        "Zone A: USD $189,000 - USD $283,600\n"
        "Zone B: USD $179,600 - USD $269,400\n"
        "Zone C: USD $170,100 - USD $255,100\n"
        "Zone D: USD $160,700 - USD $241,100"
    )

    assert evidence is not None
    assert evidence.pay_min == "160700"
    assert evidence.pay_max == "283600"
    assert evidence.rule == "structured_salary_band_envelope"


def test_level_salary_bands_use_outer_envelope():
    evidence = analyze_pay(
        "The base salary range is 320,000 USD - 488,750 USD for Level 5, and "
        "384,000 USD - 575,000 USD for Level 6."
    )

    assert evidence is not None
    assert evidence.pay_min == "320000"
    assert evidence.pay_max == "575000"


def test_market_salary_bands_use_outer_envelope():
    evidence = analyze_pay(
        "National Market\n"
        "$130,500 (entry-level qualifications) to $145,000 (highly experienced) annually\n"
        "Premium Market\n"
        "$135,000 (entry-level qualifications) to $150,000 (highly experienced) annually"
    )

    assert evidence is not None
    assert evidence.pay_min == "130500"
    assert evidence.pay_max == "150000"


def test_plain_numeric_ranges_are_not_compensation():
    assert analyze_pay(
        "Experience with IL5–6 cloud environments.\nSchedule: M-F; 8-5.\nTravel: 0-10%"
    ) is None
    assert analyze_pay("Qualifications\n3–5+ years of IT management experience") is None
    assert analyze_pay("Team interviews (2-3 hours in total)") is None
    assert analyze_pay("Contact us by phone at (858) 201-7832") is None


def test_contextual_pay_evidence_overrides_legacy_money_noise():
    resolution = resolve_parser_evidence(
        [
            {
                "capture_context": "job_description",
                "fields": {
                    "pay_min": "2",
                    "pay_max": "222400",
                    "currency": "USD",
                    "pay_period": "year",
                },
            }
        ],
        (
            "deal sizes range from transactional solutions of $2-5M.\n"
            "Pay and Benefits\nThe pay range for this position is $148200.00 - $222400.00/yr."
        ),
    )

    assert resolution.values["pay"] == ("$148200–222400 per year",)
    assert resolution.fields["pay"].priority == 100
