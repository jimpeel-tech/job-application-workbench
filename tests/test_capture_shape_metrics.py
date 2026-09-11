from jaw.capture_context import capture_metrics


def test_capture_metrics_identify_short_identity_like_capture():
    metrics = capture_metrics("Senior Platform Engineer", sequence=1)

    assert metrics["shape"] == "identity_like"
    assert metrics["size_class"] == "short"
    assert metrics["first_capture"] is True
    assert metrics["paragraphs"] == 1


def test_capture_metrics_identify_key_value_table_like_capture():
    content = (
        "Job type        Full-time\n"
        "Location        Austin, TX\n"
        "Workplace       Hybrid\n"
        "Salary          $140K-$170K"
    )

    metrics = capture_metrics(content, sequence=2)

    assert metrics["shape"] == "table_like"
    assert metrics["key_value_lines"] >= 2
    assert metrics["first_capture"] is False


def test_capture_metrics_record_bullets_paragraphs_and_description_shape():
    content = (
        "Responsibilities\n"
        "- Operate production services.\n"
        "- Participate in incident response.\n\n"
        "Qualifications\n"
        "- Five years of relevant experience."
    )

    metrics = capture_metrics(content)

    assert metrics["shape"] == "description_like"
    assert metrics["paragraphs"] == 2
    assert metrics["bullet_lines"] == 3


def test_capture_metrics_flag_collapsed_job_metadata():
    metrics = capture_metrics("Full-TimeRemote$200,000-$250,000")

    assert metrics["shape"] == "metadata_like"
    assert metrics["metadata_signals"] >= 2
    assert metrics["collapsed_metadata_suspected"] is True
