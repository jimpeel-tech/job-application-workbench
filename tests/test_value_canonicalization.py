from jaw.value_canonicalization import canonical_capture_value


def test_pay_canonicalization_treats_format_variants_as_equivalent():
    expected = canonical_capture_value("pay", "$200000–250000 per year")
    assert expected == canonical_capture_value("pay", "$200,000 - $250,000 /yr")
    assert expected == canonical_capture_value("pay", "$200K–$250K annually")
    assert expected == canonical_capture_value("pay", "USD 200000 to 250000 yearly")


def test_pay_canonicalization_preserves_meaningful_period_differences():
    annual = canonical_capture_value("pay", "$75-$90 per year")
    hourly = canonical_capture_value("pay", "$75-$90/hr")
    assert annual != hourly


def test_pay_canonicalization_distinguishes_cad_from_usd():
    cad = canonical_capture_value("pay", "CAD 115000–125000 per year")
    usd = canonical_capture_value("pay", "$115000–125000 per year")

    assert "currency=CAD" in cad
    assert "currency=USD" in usd
    assert cad != usd


def test_location_canonicalization_ignores_us_zip_suffix():
    expected = canonical_capture_value("location", "La Crescenta, CA 91214")
    assert expected == canonical_capture_value("location", "La Crescenta, CA")


def test_location_canonicalization_treats_state_name_and_code_as_equivalent():
    expected = canonical_capture_value("location", "McLean, Virginia")
    assert expected == canonical_capture_value("location", "McLean, VA")


def test_non_pay_values_keep_simple_whitespace_case_normalization():
    assert canonical_capture_value("company", "  Acme   Corp ") == "acme corp"
