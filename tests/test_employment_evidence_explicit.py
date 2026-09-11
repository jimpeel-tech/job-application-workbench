from jaw.general_evidence import extract_employment_type_evidence


def test_full_time_regular_staff_exempt_metadata_preserves_exempt():
    evidence = extract_employment_type_evidence(
        "Full Time Regular\nStaff - Exempt\nCincinnati, OH, US"
    )

    assert evidence is not None
    assert evidence.value == "Full-time, exempt"


def test_explicit_40_hour_workweek_preserves_schedule_detail():
    evidence = extract_employment_type_evidence(
        "You'll be working 40 hours a week and enjoy great company benefits."
    )

    assert evidence is not None
    assert evidence.value == "Full-time, 40 hours per week"


def test_scheduled_weekly_hours_40_is_full_time():
    evidence = extract_employment_type_evidence("Scheduled Weekly Hours:\n\n40")

    assert evidence is not None
    assert evidence.value == "Full-time"


def test_full_time_employment_basis_is_explicit_workload():
    evidence = extract_employment_type_evidence(
        "The salary for this role ranges from $132,200 to $226,600 annually "
        "based on full-time employment."
    )

    assert evidence is not None
    assert evidence.value == "Full-time"


def test_standalone_full_time_with_country_is_explicit_workload():
    evidence = extract_employment_type_evidence("Full time, United States")

    assert evidence is not None
    assert evidence.value == "Full-time"


def test_contract_type_label_can_be_permanent():
    evidence = extract_employment_type_evidence("Contract Type: Permanent")

    assert evidence is not None
    assert evidence.value == "Permanent"


def test_permanent_position_prose_is_employment_type():
    evidence = extract_employment_type_evidence(
        "This is a Permanent position based out of Austin, TX."
    )

    assert evidence is not None
    assert evidence.value == "Permanent"


def test_based_full_time_in_location_is_explicit_workload():
    evidence = extract_employment_type_evidence(
        "Based full-time in NYC, where the team works in-person"
    )

    assert evidence is not None
    assert evidence.value == "Full-time"
