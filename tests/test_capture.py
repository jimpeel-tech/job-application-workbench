from jaw.capture import classify_capture, extract_job_fields


def test_classifies_common_job_fields():
    assert classify_capture(
        "Cloud Solution Observability Engineer", "job_capture"
    ).content_type == "job_title"
    assert classify_capture(
        "RED & Associates, Inc.", "job_capture"
    ).content_type == "company"
    assert classify_capture(
        "Responsibilities\nBuild reliable services\nFive years of experience\n"
        "Required skills include Kubernetes and AWS.",
        "job_capture",
    ).content_type == "job_description"


def test_application_question_and_following_answer_are_paired_by_context():
    question = classify_capture(
        "Why do you want to work here?", "application"
    )
    assert question.content_type == "application_question"
    answer = classify_capture(
        "The role closely matches my production platform experience.",
        "application",
        [{"content_type": "application_question", "classification_status": "classified"}],
    )
    assert answer.content_type == "application_answer"


def test_uncertain_short_text_stays_unclassified():
    result = classify_capture("Something ambiguous", "job_capture")
    assert result.content_type == "unclassified"
    assert result.confidence == 0


def test_extracts_fields_and_questions_from_full_description():
    content = """Senior Observability Engineer

Job details
Job Req ID: JR-48291
RFD & Associates, Inc. is hiring a full-time, remote Sr. Observability Engineer.
Responsibilities
Build observability platforms and dashboards.
Job Type: Full-time
Application Question(s):
Please list observability products you have direct experience with.
What is your current Dynatrace certification level?
Education:
Bachelor's (Required)
Work Location: Remote
"""
    result = extract_job_fields(content)
    assert result["fields"] == {
        "title": "Senior Observability Engineer",
        "job_id": "JR-48291",
        "company": "RFD & Associates, Inc.",
        "employment_type": "Full-time",
        "location": "Remote",
        "education": "Bachelor's (Required)",
        "responsibilities": ["Build observability platforms and dashboards."],
    }
    assert result["application_questions"] == [
        "Please list observability products you have direct experience with.",
        "What is your current Dynatrace certification level?"
    ]


def test_extracts_adjacent_labels_pay_and_negative_remote_status():
    content = """IT Specialist (Network)
Department of Veterans Affairs  Austin, TX
job requisition id
JR2017192
Remote job
No
Telework eligible
Yes—as determined by agency policy.
Work schedule
Full-time
Appointment type
Permanent
Salary
$109,428 - $142,259 per year
"""

    fields = extract_job_fields(content)["fields"]

    assert fields["title"] == "IT Specialist (Network)"
    assert fields["company"] == "Department of Veterans Affairs"
    assert fields["job_id"] == "JR2017192"
    assert fields["location"] == "Austin, TX"
    assert fields["remote_status"] == "Telework eligible; not remote"
    assert fields["employment_type"] == "Full-time/Permanent"
    assert fields["pay_min"] == "109428"
    assert fields["pay_max"] == "142259"
    assert fields["pay_period"] == "year"


def test_extracts_common_labeled_and_standalone_job_identifiers():
    assert extract_job_fields(
        "Legal Secretary\nRecruitment Number 23-0042"
    )["fields"]["job_id"] == "23-0042"
    assert extract_job_fields(
        "Oracle Consultant\nJob Identification\n341967\nPosting Date"
    )["fields"]["job_id"] == "341967"
    assert extract_job_fields(
        "Program Manager\n#8681\nUnited States"
    )["fields"]["job_id"] == "8681"


def test_extracts_employment_type_variants_and_qualifiers():
    assert extract_job_fields(
        "Engineer\nJob Type Full Time/Permanent"
    )["fields"]["employment_type"] == "Full-time/Permanent"
    assert extract_job_fields(
        "Apprentice\nJob Type: Full-time Â· Apprenticeship"
    )["fields"]["employment_type"] == "Full-time apprenticeship"
    assert extract_job_fields(
        "Contractor\nJob type\nPart-time\nExample LLC — Contract (1099)"
    )["fields"]["employment_type"] == "Part-time independent contractor (1099)"


def test_noisy_result_list_uses_selected_detail_boundary():
    content = """Machine Learning Systems Engineer, Networking
JR2018261
Another Role
JR9999999
Return to selected search result
Product Program Manager
locations
US, CA, Santa Clara
time type
Full time
job requisition id
JR2017192
NVIDIA is seeking a Product Program Manager.
"""

    fields = extract_job_fields(content)["fields"]

    assert fields["title"] == "Product Program Manager"
    assert fields["job_id"] == "JR2017192"
    assert fields["company"] == "NVIDIA"
    assert fields["location"] == "Santa Clara, CA"


def test_extracts_and_classifies_common_job_sections():
    content = """Data Entry Typist
Example Company

Key Responsibilities
- Enter and update customer data.
- Verify data accuracy.

Qualifications
High school diploma or equivalent.
Two years of data entry experience.
Microsoft Excel proficiency.
Valid driver's license.

Preferred Qualifications
Administrative training.

Benefits
Health insurance
Paid time off

Application Questions
Can you work weekends?
"""

    result = extract_job_fields(content)
    fields = result["fields"]

    assert fields["responsibilities"] == [
        "Enter and update customer data.", "Verify data accuracy.",
    ]
    assert fields["required_skills"] == ["Microsoft Excel proficiency."]
    assert fields["experience_requirements"] == [
        "Two years of data entry experience."
    ]
    assert fields["education"] == "High school diploma or equivalent."
    assert fields["required_certifications"] == ["Valid driver's license."]
    assert fields["preferred_skills"] == ["Administrative training."]
    assert "benefits" not in fields
    assert result["application_questions"] == ["Can you work weekends?"]


def test_qualification_blocks_stop_at_page_and_duty_boundaries():
    content = """Teacher
Example District
Minimum Qualification Requirements
Alaska Teacher Certificate required.
Knowledge of: classroom management; curriculum design; student assessment.
Essential Duties and Responsibilities
Prepare weekly lesson plans.
Physical Requirements
Lift up to 25 pounds.
"""

    fields = extract_job_fields(content)["fields"]

    assert fields["required_certifications"] == [
        "Alaska Teacher Certificate required."
    ]
    assert fields["required_skills"] == [
        "classroom management", "curriculum design", "student assessment."
    ]
    assert fields["responsibilities"] == ["Prepare weekly lesson plans."]


def test_disclaimer_does_not_become_a_qualification():
    content = """Project Manager
Oracle
Qualifications
Disclaimer:
Salary ranges depend on location and market conditions.
Benefits include medical and dental insurance.
"""

    fields = extract_job_fields(content)["fields"]

    assert "required_skills" not in fields


def test_extracts_explicit_pre_analysis_decision_facts():
    content = """Platform Engineer
Example Corp
Remote role, but employees must report to the Dallas office twice a week.
This role participates in an on-call rotation and may require up to 20% travel.
An active Secret security clearance is required.
We do not offer visa sponsorship for this position.
Night shift and weekends as needed.
Application deadline: August 20, 2026
"""

    fields = extract_job_fields(content)["fields"]

    assert fields["on_call"] == "Required"
    assert fields["travel"] == "Up to 20%"
    assert fields["clearance"] == "active Secret security clearance"
    assert fields["sponsorship"] == "Not offered"
    assert fields["schedule"] == "Night Shift; Weekends As Needed"
    assert fields["application_deadline"] == "August 20, 2026"
    assert fields["remote_status"] == "Conflicting remote claim"


def test_explicit_remote_is_not_overridden_by_optional_in_person_connection():
    fields = extract_job_fields(
        """Staff Engineer
Remote
Teams work remotely. We also prioritize intentional, in-person connection
through optional team gatherings and on-demand workspaces.
"""
    )["fields"]

    assert fields["remote_status"] == "Remote"


def test_plural_work_locations_prose_is_not_an_explicit_location_label():
    fields = extract_job_fields(
        """Senior Manager, Software Engineering
Remote
Salary Range Disclaimer
Compensation may vary based on where a role is performed, as work locations
are grouped into geographic pay tiers to reflect cost-of-labor differences.
"""
    )["fields"]

    assert fields["remote_status"] == "Remote"
    assert "location" not in fields


def test_explicit_singular_location_label_is_preserved():
    fields = extract_job_fields(
        "Azure Architect\nLocation: Remote\nThis is a remote position."
    )["fields"]

    assert fields["location"] == "Remote"
    assert fields["remote_status"] == "Remote"


def test_empty_location_label_does_not_consume_the_next_section():
    fields = extract_job_fields(
        "Cloud Engineer\nLocation:\nJob description\nBuild reliable services."
    )["fields"]

    assert "location" not in fields


def test_structured_remote_no_preserves_ad_hoc_telework_detail():
    fields = extract_job_fields(
        """IT Specialist
Telework eligible
Yes—Ad hoc telework may be authorized at management discretion.
Remote job
No
"""
    )["fields"]

    assert fields["remote_status"] == "Ad hoc telework eligible; not remote"


def test_explicit_on_site_and_field_based_arrangements_are_detected():
    on_site = extract_job_fields(
        "Data Labeler\nThis is a full-time, on-site position."
    )["fields"]
    field_based = extract_job_fields(
        "Site Surveyor\nNo sales or installs, just fieldwork you control."
    )["fields"]

    assert on_site["remote_status"] == "On-site"
    assert field_based["remote_status"] == "Field-based"


def test_negative_on_call_and_travel_are_preserved():
    fields = extract_job_fields(
        "Support Engineer\nThere is no on-call rotation and no travel is required."
    )["fields"]

    assert fields["on_call"] == "Not required"
    assert fields["travel"] == "None"


def test_recognizes_common_unlabeled_platform_section_names():
    content = """Machine Learning Engineer
Example Corp
What you'll be doing:
Build production streaming ML pipelines.
What we need to see:
Strong programming skills in Go or Rust.
Five years of production ML experience.
Ways to stand out from the crowd:
Experience with Kafka streaming pipelines.
"""

    fields = extract_job_fields(content)["fields"]

    assert fields["responsibilities"] == [
        "Build production streaming ML pipelines."
    ]
    assert fields["required_skills"] == [
        "Strong programming skills in Go or Rust."
    ]
    assert fields["experience_requirements"] == [
        "Five years of production ML experience."
    ]
    assert fields["preferred_skills"] == [
        "Experience with Kafka streaming pipelines."
    ]


def test_recognizes_duties_responsibilities_heading():
    fields = extract_job_fields(
        "Warehouse Associate\nDuties Responsibilities\n"
        "Prepare grocery orders for delivery\nRequirements\nEnglish proficiency"
    )["fields"]

    assert fields["responsibilities"] == ["Prepare grocery orders for delivery"]
    assert fields["required_skills"] == ["English proficiency"]


def test_recognizes_section_heading_variants_and_inline_content():
    fields = extract_job_fields(
        """Operations Technician
Examples of Duties
Operate automated test equipment.
Skills & Knowledge: Strong analytical and problem-solving skills.
Preferred Additional Skills
Soldering experience.
"""
    )["fields"]

    assert fields["responsibilities"] == ["Operate automated test equipment."]
    assert fields["required_skills"] == [
        "Strong analytical and problem-solving skills."
    ]
    assert fields["preferred_skills"] == ["Soldering experience."]


def test_joins_lowercase_page_wraps_inside_extracted_sections():
    fields = extract_job_fields(
        """Network Engineer
Responsibilities
Configure network switches and routers
to provide resilient data-center connectivity.
"""
    )["fields"]

    assert fields["responsibilities"] == [
        "Configure network switches and routers to provide resilient data-center connectivity."
    ]


def test_recognizes_lifecycle_and_platform_specific_section_headings():
    fields = extract_job_fields(
        """Bakery Associate
A Day In The Life
Prepare baked goods and assist customers.
We Also Provide a Variety Of Benefits Including
Flexible work schedules
Associate discounts
Show less
Seniority level
Entry level
"""
    )["fields"]

    assert fields["responsibilities"] == [
        "Prepare baked goods and assist customers."
    ]
    assert "benefits" not in fields


def test_extracts_explicit_preferred_clauses_outside_a_section():
    fields = extract_job_fields(
        """Support Technician
Requirements
Linux troubleshooting
Experience with Grafana is preferred.
Prometheus experience would be a plus.
"""
    )["fields"]

    assert fields["preferred_skills"] == [
        "Experience with Grafana is preferred.",
        "Prometheus experience would be a plus.",
    ]


def test_extracts_explicit_experience_outside_qualification_sections():
    fields = extract_job_fields(
        """Repair Technician
Minimum 2 years of previous mechanical or electrical experience
Retail and customer service experience required
"""
    )["fields"]

    assert fields["experience_requirements"] == [
        "Minimum 2 years of previous mechanical or electrical experience",
        "Retail and customer service experience required",
    ]


def test_benefit_prose_is_ignored_by_first_pass_extraction():
    fields = extract_job_fields(
        """Platform Engineer
Our benefits include restricted stock units, pet insurance, an employee
assistance program, and training and certification assistance.
"""
    )["fields"]

    assert "benefits" not in fields


def test_extracts_explicit_education_outside_qualification_sections():
    fields = extract_job_fields(
        "Technician\nHigh School Graduate or General Education Degree (GED)"
    )["fields"]
    federal = extract_job_fields(
        "IT Specialist GS-13\nEducation\nThere is no educational substitution at this grade level."
    )["fields"]

    assert fields["education"] == "High School Graduate or General Education Degree (GED)"
    assert federal["education"] == "No educational substitution at GS-13"


def test_resolves_title_and_company_from_job_board_headers():
    indeed = extract_job_fields(
        "Honda\nStock & Material Handler I (100787)\nJob details\nPay\n$27 an hour"
    )["fields"]
    linkedin = extract_job_fields(
        "Warehouse Team Member\nChick-fil-A Supply LLC\n4.1 out of 5 stars"
    )["fields"]
    tabular = extract_job_fields(
        "POSITION OVERVIEW\nJob Title\tSPECIAL AGENT, GL-09/GL-10\nJob Type\tFull Time/Permanent"
    )["fields"]

    assert indeed["title"] == "Stock & Material Handler I"
    assert indeed["company"] == "Honda"
    assert linkedin["title"] == "Warehouse Team Member"
    assert linkedin["company"] == "Chick-fil-A Supply LLC"
    assert tabular["title"] == "SPECIAL AGENT, GL-09/GL-10"
