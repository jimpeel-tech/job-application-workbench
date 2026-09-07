from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

JOB_EXTRACTOR_VERSION = "rules-v3"

_SECTION_ALIASES = {
    "responsibilities": {
        "responsibilities", "key responsibilities", "position responsibilities",
        "primary responsibilities", "essential duties", "essential functions",
        "duties", "key duties", "key accountabilities", "what you'll do",
        "what you’ll do", "the work you'll do", "the work you’ll do",
        "your responsibilities", "role responsibilities", "key role",
        "essential duties and responsibilities",
        "essential duties and responsibilities include the following",
        "duties will include but not limited to", "what you will be doing",
        "a day in the life",
        "duties responsibilities", "what you'll be doing", "what youâ€™ll be doing",
        "missions",
        "major duties",
    },
    "required_skills": {
        "qualifications", "requirements", "job requirements",
        "required qualifications", "basic qualifications",
        "minimum qualifications", "minimum qualification requirements",
        "qualifications & requirements", "qualifications and requirements",
        "qualifications, experience, and skills",
        "here's what we're looking for", "here’s what we’re looking for",
        "what we're looking for", "what we’re looking for", "who you are",
        "what you'll bring", "what you’ll bring", "skills and qualifications",
        "who we are seeking",
        "education & experience", "education and experience",
        "education requirements", "experience requirements",
        "what you need (must have before applying)",
        "what we need to see",
        "required skills", "required skills and experience", "key requirements",
        "qualifications and evaluations",
        "additional skills and knowledge", "other requirements", "computer skills",
    },
    "preferred_skills": {
        "preferred qualifications", "recommended qualifications",
        "recommended qualifications for site project manager",
        "desired qualifications", "nice to have",
        "nice-to-have", "bonus points", "preferred skills",
        "preferred \u2014 not required", "preferred - not required",
        "ways to stand out from the crowd", "ways to stand out",
    },
    "benefits": {
        "benefits", "benefits and perks", "benefits & perks", "our benefits",
        "perks and benefits", "perks & benefits", "what we offer",
        "total rewards", "compensation and benefits",
        "what benefits are we offering?",
        "employee perks", "we also provide a variety of benefits including",
    },
    "application_questions": {
        "application questions", "application question(s)",
        "screening questions", "required questions",
    },
}

_SECTION_BOUNDARIES = {
    "about us", "about the company", "about the role", "additional information",
    "additional offerings", "apply", "company description", "compensation",
    "conditions of employment", "decisions expected", "disclaimer",
    "diversity and inclusion", "education", "eeo statement",
    "equal opportunity", "full job description", "job description", "job details",
    "how it works", "how to get started", "industries", "job dimensions",
    "job function", "job overview", "job purpose", "job type", "location",
    "other information", "our beliefs about the future of technical work",
    "our divisions", "overview", "physical demands", "physical requirements",
    "position overview",
    "posted pay range", "required documentation", "role description", "salary",
    "seniority level", "special agent application process", "summary",
    "team description",
    "what you can expect", "work location", "working conditions", "show less",
}


@dataclass(frozen=True)
class CaptureClassification:
    content_type: str
    confidence: float
    reason: str


_QUESTION_OPENERS = (
    "are ", "can ", "could ", "describe ", "did ", "do ", "explain ",
    "have ", "how ", "is ", "tell ", "what ", "when ", "where ",
    "which ", "why ", "will ", "would ", "please ",
)
_TITLE_WORDS = {
    "administrator", "agent", "analyst", "architect", "associate", "attendant",
    "clerk", "concierge", "consultant", "designer", "developer", "director",
    "engineer", "engineering", "handler", "host", "labeler", "laborer", "lead",
    "maintenance", "manager", "member", "merchandising", "officer", "principal", "reliability",
    "scientist", "secretary", "shopper", "specialist", "teacher", "technician",
    "typist", "worker", "apprentice", "supervisor",
}
_DESCRIPTION_WORDS = {
    "benefits", "description", "duties", "employment", "experience",
    "qualifications", "responsibilities", "requirements", "salary",
    "skills", "years",
}
_COMPANY_SUFFIX = re.compile(
    r"\b(?:inc\.?|incorporated|llc|ltd\.?|limited|corp\.?|corporation|"
    r"company|co\.?|associates|group|partners|products|technologies|solutions)\b",
    re.IGNORECASE,
)
_TITLE_PATTERN = (
    r"(?:Administrator|Agent|Analyst|Architect|Associate|Attendant|Clerk|Concierge|"
    r"Consultant|Designer|Developer|Director|Engineer|Engineering Manager|Handler|Host|"
    r"Labeler|Laborer|Lead|Maintenance|Manager|Member|Merchandising|Officer|Principal|"
    r"Scientist|Secretary|Shopper|Specialist|Supervisor|Teacher|Technician|Typist|Worker|Apprentice)"
)
_GENERIC_HEADINGS = {
    "about the role", "benefits", "company description", "education",
    "full job description", "job description", "job details", "job overview",
    "overview", "responsibilities", "role overview", "role summary",
}
_NON_COMPANIES = {
    "a", "about us", "company", "it", "our", "role", "the company",
    "this", "this role", "us", "we", "you", "your",
}


def classify_capture(
    content: str,
    phase: str,
    previous_events: list[dict[str, Any]] | None = None,
) -> CaptureClassification:
    """Classify a selection using conservative, deterministic rules."""
    text = " ".join(content.split())
    lowered = text.casefold()
    words = set(re.findall(r"[a-z]+", lowered))
    previous_events = previous_events or []

    if phase == "application":
        if text.endswith("?") or lowered.startswith(_QUESTION_OPENERS):
            return CaptureClassification(
                "application_question", 0.92, "question punctuation or wording"
            )
        last_typed = next(
            (
                str(event.get("content_type", ""))
                for event in reversed(previous_events)
                if event.get("classification_status") == "classified"
            ),
            "",
        )
        if last_typed == "application_question":
            return CaptureClassification(
                "application_answer", 0.78, "follows an application question"
            )

    line_count = len([line for line in content.splitlines() if line.strip()])
    description_score = len(words & _DESCRIPTION_WORDS)
    if len(text) >= 220 or line_count >= 4 or description_score >= 3:
        return CaptureClassification(
            "job_description", 0.88, "long or structured job content"
        )
    if len(text) <= 120 and words & _TITLE_WORDS:
        return CaptureClassification("job_title", 0.82, "job-title terminology")
    if len(text) <= 100 and _COMPANY_SUFFIX.search(text):
        return CaptureClassification("company", 0.84, "organization naming pattern")

    return CaptureClassification(
        "unclassified", 0.0, "no deterministic rule matched"
    )


def extract_job_fields(content: str) -> dict[str, Any]:
    """Extract conservative job fields while preserving the source text."""
    content = _target_posting(content)
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    fields: dict[str, Any] = {}

    requisition = re.search(
        r"(?:^|\n)\s*(?:job\s*)?(?:requisition|req(?:uisition)?|job|"
        r"announcement|control|recruitment)\s*(?:(?:id|number)\b|#)\s*:?\s*"
        r"(?:\n\s*)?([A-Z0-9][A-Z0-9._/-]{1,40})\b",
        content,
        re.IGNORECASE,
    )
    if not requisition:
        requisition = re.search(
            r"(?:^|\n)\s*Job\s+Identification\s*(?:\n|\t|\s{2,})\s*"
            r"([A-Z0-9][A-Z0-9._/-]{1,40})\b",
            content,
            re.IGNORECASE,
        )
    if not requisition:
        requisition = re.search(
            r"(?:^|\n)\s*(CP-[A-Z0-9-]+|JR\d{5,}|ID\d{4,}|"
            r"[A-Z]{2,}(?:-[A-Z0-9]+){3,}|\d{5,}BR)\s*(?:\n|$)",
            content,
            re.IGNORECASE,
        )
    if not requisition:
        requisition = re.search(
            r"(?:^|\n)\s*#(\d[0-9._/-]{2,20})\s*(?:\n|$)",
            content,
            re.IGNORECASE,
        )
    if not requisition:
        requisition = re.search(
            r"(?:^|\n)\s*POSTING\s*(?:\n\s*)?"
            r"([A-Z0-9][A-Z0-9._/-]{2,20})\b|"
            r"\b(\d{2}-[A-Z]{2}-\d{8}-[A-Z]{2})\b",
            content,
            re.IGNORECASE,
        )
    if requisition:
        fields["job_id"] = next(
            group.strip() for group in requisition.groups() if group
        )

    explicit_title = re.search(
        r"(?:^|\n)\s*(?:Job\s+)?Title\s*(?::|\t|\s{2,})\s*([^\n]{2,120})",
        content,
        re.IGNORECASE,
    )
    if not explicit_title:
        explicit_title = re.search(
            r"(?:^|\n)\s*Position Description/PD#\s*:\s*"
            r"([^\n]{2,120})/PD[A-Z0-9]+\s*(?:\n|$)",
            content,
            re.I,
        )
    if explicit_title:
        fields["title"] = _clean_title(explicit_title.group(1))
    else:
        title = _best_title_candidate(lines, content)
        if title:
            fields["title"] = title

    hiring = re.search(
        r"(?:^|[\n.!?]\s*)([A-Z][A-Za-z0-9&'’.,\- ]{1,90}?)\s+"
        r"is\s+hiring\b(?:.*?\b(?:an?|the)\s+)?([^\n.!?]{2,100})?",
        content,
        re.MULTILINE,
    )
    if hiring:
        hiring_company = hiring.group(1).strip(" ,")
        if _valid_company(hiring_company):
            fields["company"] = hiring_company
        if "title" not in fields and hiring.group(2):
            candidate = re.sub(
                r"^(?:full[- ]time|part[- ]time|remote|hybrid)\s*,?\s*",
                "", hiring.group(2).strip(), flags=re.IGNORECASE,
            )
            if candidate:
                fields["title"] = candidate

    if "company" not in fields:
        company = _header_company(lines, fields.get("title", ""))
        if company:
            fields["company"] = company

    if "company" not in fields:
        company = _extract_company(content, lines)
        if company:
            fields["company"] = company

    employment_type = _extract_employment_type(content, lines)
    if employment_type:
        fields["employment_type"] = employment_type

    explicit_location = re.search(
        r"(?:^|\n)[ \t]*(?:(?:Work[ \t]+)?Location[ \t]*:[ \t]*([^\r\n]+)|"
        r"Work[ \t]+Location[ \t]*:?\r?\n[ \t]*([^\r\n]+))",
        content,
        re.IGNORECASE,
    )
    explicit_location_value = (
        (
            explicit_location.group(1) or explicit_location.group(2)
        ).strip()
        if explicit_location
        else ""
    )
    if explicit_location_value:
        fields["location"] = explicit_location_value
    else:
        location = _extract_location(lines, content)
        if location:
            fields["location"] = location

    remote_status = _extract_work_arrangement(content)
    if remote_status:
        fields["remote_status"] = remote_status
    pay = _extract_pay(content)
    fields.update({key: value for key, value in pay.items() if value})

    decision_fields = _extract_decision_fields(content)
    fields.update({key: value for key, value in decision_fields.items() if value})

    questions: list[str] = []
    question_section = re.search(
        r"Application\s+Question\(s\)\s*:\s*(.*?)(?=\n\s*(?:Education|"
        r"Work\s+Location|Job\s+Type|Benefits)\s*:|\Z)",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if question_section:
        questions = [
            line.strip(" •\t")
            for line in question_section.group(1).splitlines()
            if line.strip(" •\t")
        ]

    section_fields = _extract_section_fields(content)
    fields.update(section_fields)
    questions = fields.pop("application_questions", questions)

    return {
        "fields": fields,
        "application_questions": questions,
        "extractor": JOB_EXTRACTOR_VERSION,
    }


def _extract_decision_fields(content: str) -> dict[str, str]:
    """Extract explicit facts useful for deciding whether to analyze a job."""
    fields: dict[str, str] = {}

    if re.search(r"\b(?:on[- ]call|on call rotation|pager duty)\b", content, re.I):
        excluded = re.search(
            r"\b(?:no|not|without)\s+(?:an?\s+)?on[- ]call\b|"
            r"\bno on[- ]call rotation\b", content, re.I,
        )
        fields["on_call"] = "Not required" if excluded else "Required"

    travel = re.search(
        r"(?:\b(?:travel(?: requirements?)?|traveling)\s*:?[ \t]*"
        r"(?:up to\s+)?(\d{1,3}\s*%)|"
        r"\b(?:up to\s+)?(\d{1,3}\s*%)\s+travel)", content, re.I,
    )
    if travel:
        percent = travel.group(1) or travel.group(2)
        fields["travel"] = f"Up to {percent.replace(' ', '')}"
    elif re.search(r"\bno travel (?:is )?required\b", content, re.I):
        fields["travel"] = "None"

    clearance = re.search(
        r"\b((?:active\s+|current\s+)?(?:top secret(?:/sci| sci)?|secret|"
        r"public trust)\s+(?:security\s+)?clearance)\b", content, re.I,
    )
    if clearance:
        fields["clearance"] = re.sub(r"\s+", " ", clearance.group(1)).strip()
    elif re.search(r"\bmust be able to obtain a security clearance\b", content, re.I):
        fields["clearance"] = "Must be able to obtain"

    no_sponsorship = re.search(
        r"\b(?:no|without)\s+(?:visa\s+)?sponsorship\b|"
        r"\bnot (?:eligible|available) for (?:visa\s+)?sponsorship\b|"
        r"\b(?:will|do) not (?:provide|offer|sponsor)\b[^.\n]{0,45}"
        r"\b(?:visa|sponsorship)\b|"
        r"\bdoes not now or in the future require employer sponsorship\b",
        content, re.I,
    )
    if no_sponsorship:
        fields["sponsorship"] = "Not offered"
    elif re.search(r"\b(?:visa|immigration) sponsorship (?:is )?available\b", content, re.I):
        fields["sponsorship"] = "Available"

    deadline = re.search(
        r"\b(?:application|apply|closing)\s+(?:deadline|date)|"
        r"\bcloses?\b", content, re.I,
    )
    if deadline:
        nearby = content[deadline.start():deadline.start() + 100]
        date = re.search(
            r"\b(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/(?:20)?\d{2}\b|"
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
            r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
            r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?",
            nearby, re.I,
        )
        if date:
            fields["application_deadline"] = date.group(0)

    schedule_values: list[str] = []
    for label in (
        "day shift", "evening shift", "night shift", "overnight shift",
        "second shift", "2nd shift", "third shift", "3rd shift",
        "weekends as needed", "weekend availability", "overtime",
    ):
        if re.search(rf"\b{re.escape(label)}\b", content, re.I):
            schedule_values.append(label.title())
    if schedule_values:
        fields["schedule"] = "; ".join(schedule_values)

    return fields


def _extract_work_arrangement(content: str) -> str:
    """Return an explicit work arrangement using stable evidence precedence."""
    remote_no = re.search(
        r"\b(?:Remote job|Virtual/Remote)\s*:?[ \t]*(?:\n\s*)?"
        r"(?:No|This is not (?:a )?(?:virtual|remote))\b",
        content,
        re.I,
    )
    if remote_no:
        telework = re.search(
            r"\bTelework eligible\s*:?[ \t]*(?:\n\s*)?"
            r"Yes(?P<detail>[^\n.]*)",
            content,
            re.I,
        )
        if telework:
            detail = telework.group("detail")
            if re.search(r"\bad[ -]?hoc\b", detail, re.I):
                return "Ad hoc telework eligible; not remote"
            return "Telework eligible; not remote"
        return "On-site"

    explicit_remote = re.search(
        r"\A\s*Remote\b(?!\s+(?:access|desktop|sensing)\b)|"
        r"(?:^|\n)\s*(?:Fully\s+remote|Remote(?:\s+-\s+[^\n]+)?)\s*(?:\n|$)|"
        r"(?:^|\n)\s*(?:This\s+is\s+(?:a\s+)?)?Remote\s+"
        r"(?:role|position|job)\b|"
        r"(?:^|\n)\s*Remote\s+[^\n]{1,100}\b(?:role|position|job)\s*(?:\n|$)",
        content,
        re.I,
    )
    required_attendance = re.search(
        r"\b(?:must|required|expected|need(?:ed)?|will)\b[^.\n]{0,55}"
        r"\b(?:report|commute|work)\b[^.\n]{0,55}"
        r"\b(?:office|site|location)\b",
        content,
        re.I,
    )
    if explicit_remote:
        return "Conflicting remote claim" if required_attendance else "Remote"

    if re.search(
        r"\b(?:field[- ]based|(?:just|primarily|mostly)\s+fieldwork)\b",
        content,
        re.I,
    ):
        return "Field-based"
    if re.search(
        r"\b(?:on[- ]site|in[- ]person)\s+(?:position|role|job)\b|"
        r"\bWork Location\s*:?\s*(?:\n\s*)?In[- ]person\b|"
        r"\b(?:position|role|job)\s+is\s+(?:a\s+)?(?:full[- ]time,?\s+)?"
        r"(?:on[- ]site|in[- ]person)\b",
        content,
        re.I,
    ):
        return "On-site"
    return ""


def _extract_section_fields(content: str) -> dict[str, Any]:
    sections = _section_blocks(content)
    result: dict[str, Any] = {}
    for key in ("responsibilities", "preferred_skills"):
        items = _items_from_blocks(sections.get(key, []))
        if items:
            result[key] = items
    preferred = result.setdefault("preferred_skills", [])
    for item in _explicit_preferred_items(content):
        if item not in preferred:
            preferred.append(item)
    if not preferred:
        result.pop("preferred_skills", None)

    questions = _question_items(sections.get("application_questions", []))
    for question in _numbered_questions(content):
        if question not in questions:
            questions.append(question)
    if questions:
        result["application_questions"] = questions

    skills: list[str] = []
    experience: list[str] = []
    certifications: list[str] = []
    education: list[str] = []
    required_items = _items_from_blocks(sections.get("required_skills", []))
    for item in required_items:
        lowered = item.casefold()
        if re.search(
            r"\b(?:certificate|certification|certified|license|licence|security clearance|"
            r"driver['’]s license|driver license)\b", lowered,
        ):
            certifications.append(item)
        elif re.search(
            r"\b(?:(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
            r"[+ -]*(?:years?|yrs?)|year of|years of|experience "
            r"(?:in|with|working)|prior experience|no (?:prior )?experience)\b",
            lowered,
        ):
            experience.append(item)
        elif re.search(
            r"\b(?:bachelor|master|doctorate|ph\.?d|degree|diploma|g\.?e\.?d|"
            r"high school|college|university|education)\b", lowered,
        ):
            education.append(item)
        else:
            skills.append(item)
    for item in _explicit_experience_items(content):
        if item not in experience:
            experience.append(item)
    if skills:
        result["required_skills"] = skills
    if experience:
        result["experience_requirements"] = experience
    if certifications:
        result["required_certifications"] = certifications
    if education:
        result["education"] = "; ".join(education)
    elif explicit_education := _explicit_education(content):
        result["education"] = explicit_education
    return result


def _explicit_preferred_items(content: str) -> list[str]:
    """Extract explicit preference clauses missed by a dedicated section."""
    items: list[str] = []
    excluded = re.compile(
        r"\b(?:benefits?|education|degree|diploma|high school|g\.?e\.?d|"
        r"salary|pay|location|shift|veterans?|military|equal opportunity)\b",
        re.I,
    )
    for raw in content.splitlines():
        line = re.sub(r"^[-*â€“â€”•]\s*", "", raw.strip())
        if not line or len(line) > 180 or excluded.search(line):
            continue
        if _heading_key(line):
            continue
        if re.match(
            r"^preferred\s+(?:knowledge/skills/abilities|type of experience)",
            line,
            re.I,
        ):
            continue
        if re.search(r"\bpreferred\b|\b(?:is|are|would be) a plus\b", line, re.I):
            line = re.sub(r"^preferred\s*:?[ \t]*", "", line, flags=re.I)
            if len(line) >= 4 and line not in items:
                items.append(line)
    return items


def _explicit_experience_items(content: str) -> list[str]:
    """Extract explicitly quantified or required experience outside sections."""
    items: list[str] = []
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    count = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    choice_pattern = re.compile(
        r"(?:less than\s+)?\d+(?:\s+\d/\d)?\s+year(?:s)?"
        r"(?:\s+to\s+less than\s+\d+(?:\s+\d/\d)?\s+years?)?"
        r"\s+of experience",
        re.I,
    )
    has_choice_sequence = sum(
        bool(choice_pattern.fullmatch(line)) for line in lines
    ) >= 3
    for index, raw in enumerate(lines):
        line = re.sub(r"^[-*â€“â€”•]\s*", "", raw)
        if has_choice_sequence and choice_pattern.fullmatch(line):
            continue
        if re.fullmatch(r"Years", line, re.I) and index + 1 < len(lines):
            value = lines[index + 1]
            if re.fullmatch(r"\d+\s+to\s+\d+\+?\s+years", value, re.I):
                if value not in items:
                    items.append(value)
            continue
        quantified = re.search(
            rf"\b(?:minimum\s+)?{count}(?:\+|\s*\(\d+\))?\s*"
            rf"(?:years?|months?)(?:['â€™]s?)?\b",
            line,
            re.I,
        )
        explicit = re.search(
            r"\b(?:experience\s+required|proven\b[^.]{0,80}\bexperience|"
            r"no (?:prior )?experience required)\b",
            line,
            re.I,
        )
        labeled = re.match(r"^EDUCATION and/or EXPERIENCE\s*:", line, re.I)
        domain_year = re.search(r":\s*\d+\s+years?\s*\(Required\)", line, re.I)
        if (
            (quantified and re.search(r"\bexperience\b", line, re.I))
            or explicit
            or labeled
            or domain_year
        ):
            line = re.sub(
                r"^EDUCATION and/or EXPERIENCE\s*:\s*", "", line, flags=re.I
            )
            if 4 <= len(line) <= 500 and line not in items:
                items.append(line)
    return items


def _explicit_education(content: str) -> str:
    """Return the strongest explicit education requirement in the posting."""
    education_question = re.search(
        r"(?:^|\n)\s*What is (?:your|the) highest level of education\b",
        content,
        re.I,
    )
    if education_question:
        content = content[:education_question.start()]
    no_substitution = re.search(
        r"(?:there is )?no (?:educational substitution|substitution of education)"
        r"[^.\n]*",
        content,
        re.I,
    )
    if no_substitution:
        grade = re.search(r"\bGS[- ]?(\d{1,2})\b", content, re.I)
        return (
            f"No educational substitution at GS-{grade.group(1)}"
            if grade
            else re.sub(r"\s+", " ", no_substitution.group(0)).strip()
        )

    candidates: list[tuple[int, int, str]] = []
    academic = re.compile(
        r"\b(?:high school|diploma|g\.?e\.?d|bachelor['â€™]?s?|master['â€™]?s?|"
        r"doctorate|ph\.?d|college degree|associate['â€™]?s? degree)\b|"
        r"\b(?:B\.?S\.?|M\.?S\.?)\b(?=\s*(?:degree|,|or|and|\())",
        re.I,
    )
    excluded = re.compile(
        r"\b(?:education assistance|tuition|transcript instructions?|"
        r"equal opportunity|education benefit program|relevant education or training)\b",
        re.I,
    )
    for index, raw in enumerate(content.splitlines()):
        line = re.sub(r"\s+", " ", raw).strip(" -*â€“â€”•")
        if not 4 <= len(line) <= 500 or excluded.search(line) or not academic.search(line):
            continue
        if line.casefold().startswith("recent graduate"):
            continue
        previous = content.splitlines()[max(0, index - 3):index]
        if any("?" in prior and "education" in prior.casefold() for prior in previous):
            continue
        score = 4
        if re.search(r"\b(?:required|preferred|equivalent|minimum|in lieu)\b", line, re.I):
            score += 4
        if re.search(r"\b(?:degree|diploma|GED|Ph\.?D)\b", line, re.I):
            score += 2
        candidates.append((score, -index, line))
    return max(candidates, default=(0, 0, ""))[2]


def _section_blocks(content: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current = ""
    for raw in content.splitlines():
        line = raw.strip()
        inline_skills = re.match(r"Computer Skills\s*:?[ \t]+(.+)", line, re.I)
        if inline_skills:
            current = "required_skills"
            blocks.setdefault(current, []).append(inline_skills.group(1).strip())
            continue
        heading, remainder = _split_section_heading(line)
        if heading:
            current = heading if heading != "boundary" else ""
            if current and remainder:
                blocks.setdefault(current, []).append(remainder)
            continue
        if current and line and line.casefold() not in {
            "pulled from the full job description", "&nbsp;", "show more", "show less",
        }:
            blocks.setdefault(current, []).append(line)
    return blocks


def _split_section_heading(line: str) -> tuple[str, str]:
    """Return a recognized standalone heading and any colon-delimited content."""
    heading = _heading_key(line)
    if heading:
        return heading, ""
    if ":" not in line:
        return "", ""
    label, remainder = line.split(":", 1)
    heading = _heading_key(label)
    return (heading, remainder.strip()) if heading else ("", "")


def _heading_key(line: str) -> str:
    normalized = re.sub(r"\s+", " ", line.strip().rstrip(":")).casefold()
    if normalized.startswith("oracle us offers a comprehensive benefits package"):
        return "benefits"
    for key, aliases in _SECTION_ALIASES.items():
        if normalized in aliases:
            return key
    patterned_headings = (
        ("responsibilities", r"(?:examples of duties|job responsibilities|"
         r"responsibilities include|essential duties and responsibilities "
         r"include(?: the following)?)"),
        ("required_skills", r"(?:required|required qualifications(?: \([^)]*\))?|"
         r"skills (?:&|and) knowledge|education and experience requirements|"
         r"what you need|what you bring to the table|profil)"),
        ("preferred_skills", r"(?:preferred qualifications(?: \([^)]*\))?|"
         r"preferred additional skills|preferred skills and experience)"),
    )
    for key, pattern in patterned_headings:
        if re.fullmatch(pattern, normalized):
            return key
    if normalized in _SECTION_BOUNDARIES:
        return "boundary"
    if any(normalized.startswith(f"{heading}:") for heading in _SECTION_BOUNDARIES):
        return "boundary"
    if "typical base pay range for this role" in normalized:
        return "boundary"
    if normalized.startswith((
        "with competitive salaries", "your base salary will", "the base salary range",
        "applications for this job", "this posting is for", "equal opportunity employer",
    )):
        return "boundary"
    return ""


def _items_from_blocks(
    blocks: list[str], *, short_only: bool = False,
    split_semicolons: bool = False,
) -> list[str]:
    items: list[str] = []
    for raw in _join_wrapped_lines(blocks):
        dense_requirements = re.match(r"^(?:Knowledge of|Ability to)\s*:", raw)
        separator = r"\s*[•●▪]\s*|\s+\|\s+"
        if split_semicolons or dense_requirements:
            separator += r"|\s*;\s*"
        for part in re.split(separator, raw):
            item = re.sub(r"^[-*–—]\s*", "", part).strip()
            item = re.sub(r"^\d+[.)]\s+", "", item)
            item = re.sub(r"^(?:Knowledge of|Ability to)\s*:\s*", "", item)
            item = re.sub(r"\s+", " ", item).strip(" ;")
            if not item or len(item) < 3:
                continue
            if short_only and (len(item) > 100 or len(item.split()) > 14):
                continue
            if item.casefold() in _SECTION_BOUNDARIES:
                continue
            if item.casefold() in {"help", "disclaimer", "required question"}:
                continue
            if item not in items:
                items.append(item)
    return items


def _join_wrapped_lines(lines: list[str]) -> list[str]:
    """Join obvious lowercase continuations created by copied page wrapping."""
    joined: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (
            joined
            and stripped
            and stripped[0].islower()
            and not re.search(r"[.!?;:]$", joined[-1])
        ):
            joined[-1] = f"{joined[-1]} {stripped}"
        else:
            joined.append(stripped)
    return joined


def _question_items(blocks: list[str]) -> list[str]:
    questions: list[str] = []
    for item in _items_from_blocks(blocks):
        found = re.findall(r"(?:^|(?<=[?.]))\s*([^?]{5,250}\?)", item)
        standalone = item.endswith("?") or item.casefold().startswith(_QUESTION_OPENERS)
        for question in found or ([item] if standalone else []):
            question = question.strip()
            if question not in questions:
                questions.append(question)
    return questions


def _numbered_questions(content: str) -> list[str]:
    lines = [line.strip() for line in content.splitlines()]
    markers = [index for index, line in enumerate(lines) if re.fullmatch(r"\d{2}", line)]
    if len(markers) < 2:
        return []
    questions: list[str] = []
    for index in markers:
        prompt = next((line for line in lines[index + 1:] if line), "")
        if prompt and len(prompt) >= 8 and prompt not in questions:
            questions.append(prompt)
    return questions


def _target_posting(content: str) -> str:
    """Remove obvious result-list noise while preserving the selected posting."""
    marker = re.search(
        r"(?:^|\n)Return to selected search result\s*\n", content, re.IGNORECASE
    )
    if marker:
        return content[marker.end():]
    marker = re.search(r"(?:^|\n)Open Role\s*\n", content, re.IGNORECASE)
    if marker:
        return content[marker.end():]
    return content


def _employment_label(value: str) -> str:
    lowered = value.strip().casefold().replace(" ", "-")
    if lowered == "full-time":
        return "Full-time"
    if lowered == "part-time":
        return "Part-time"
    if lowered == "employment-type-may-vary":
        return "Varies"
    return value.strip().title()


def _clean_title(value: str) -> str:
    title = re.sub(r"\s+", " ", value).strip(" -â€“â€”•,")
    title = re.sub(r"\s*-\s*job post\s*$", "", title, flags=re.I)
    title = re.sub(r"\s*\(\d{4,}\)\s*$", "", title)
    return title.strip()


def _extract_employment_type(content: str, lines: list[str]) -> str:
    label = re.search(
        r"\b(?:Job\s+Type|Employment\s+type|Appointment\s+type|Time\s+type|Status)"
        r"\s*:?\s*(?:\n\s*)?(Full[- ]time|Part[- ]time|Temporary|Seasonal|"
        r"Permanent|Employment type may vary)"
        r"(?:\s*(?:[/,]|Â·|·)\s*(Permanent|Apprenticeship))?",
        content,
        re.I,
    )
    value = _employment_label(label.group(1)) if label else ""
    qualifier = label.group(2).title() if label and label.group(2) else ""
    if value and qualifier:
        value = (
            f"{value} apprenticeship"
            if qualifier == "Apprenticeship"
            else f"{value}/{qualifier}"
        )

    if not value:
        standalone = re.search(
            r"(?:^|\n)\s*(Full[- ]time|Part[- ]time|Temporary|Seasonal|"
            r"Employment type may vary)\s*(?:\n|$)",
            content,
            re.I,
        )
        if standalone:
            value = _employment_label(standalone.group(1))
    if not value and re.search(
        r"\bthis is (?:a )?(?:full[- ]time|part[- ]time),?\s+"
        r"(?:on[- ]site|in[- ]person)\s+position\b",
        content,
        re.I,
    ):
        kind = re.search(r"\b(full[- ]time|part[- ]time)\b", content, re.I)
        value = _employment_label(kind.group(1)) if kind else ""
    if not value and any(
        re.search(r"\s[-â€“â€”]\s*Seasonal\s*$", line, re.I)
        for line in lines[:5]
    ):
        value = "Seasonal"

    appointment = re.search(
        r"\bAppointment\s+type\s*(?:\n\s*)?(Permanent|Temporary)\b",
        content,
        re.I,
    )
    schedule = re.search(
        r"\bWork\s+schedule\s*(?:\n\s*)?(Full[- ]time|Part[- ]time)\b",
        content,
        re.I,
    )
    if appointment and schedule:
        value = f"{_employment_label(schedule.group(1))}/{appointment.group(1).title()}"
    if value == "Part-time" and re.search(r"\b(?:contract\s*\(1099\)|1099)\b", content, re.I):
        value = "Part-time independent contractor (1099)"
    elif value == "Part-time" and lines and re.search(r"\bon[- ]call\b", lines[0], re.I):
        value = "Part-time, on-call"
    return value


def _header_company(lines: list[str], title: str) -> str:
    if not lines or not title:
        return ""
    title_index = next(
        (
            index for index, line in enumerate(lines[:12])
            if _clean_title(line).casefold() == title.casefold()
        ),
        -1,
    )
    if title_index < 0:
        return ""
    candidate_lines: list[str] = []
    if title_index > 0:
        candidate_lines.append(lines[title_index - 1])
    if title_index + 1 < len(lines):
        candidate_lines.append(lines[title_index + 1])
    for line in candidate_lines:
        if (
            len(line) > 120
            or re.search(r"[$#]", line)
            or line.casefold().startswith(("about ", "remote "))
            or line.casefold() in {
                "remote", "full time", "full-time", "part time", "part-time",
                "apply", "save", "careers", "united states", "job details",
                "future opening", "locations", "location", "trending", "hot job",
            }
        ):
            continue
        location = re.search(
            r"\s{2,}(?:[A-Za-z.' -]+,\s*[A-Z]{2}|Remote|United States)\s*$",
            line,
        )
        candidate = line[:location.start()].strip() if location else line.strip()
        candidate = re.sub(
            r"^(?:Company|Employer|Organization)\s*:\s*", "", candidate, flags=re.I
        )
        if _valid_company(candidate) and candidate.casefold() not in _GENERIC_HEADINGS and not re.search(
            r"\b(?:location|posted|job identification|job category)\b",
            candidate,
            re.IGNORECASE,
        ):
            return candidate
    return ""


def _extract_location(lines: list[str], content: str) -> str:
    for index, line in enumerate(lines[:35]):
        if line.casefold() in {"locations", "location"} and index + 1 < len(lines):
            for candidate in lines[index + 1:index + 7]:
                lowered = candidate.casefold()
                if lowered.startswith(("help", "1 vacancy", "2 vacancies", "3 vacancies", "4 vacancies")):
                    continue
                if re.search(r"\b[A-Za-z.' -]+,\s*[A-Z]{2}(?:\s+\d{5})?\b", candidate):
                    return _clean_location(candidate)
                if len(candidate) <= 120 and not lowered.startswith(("remote job", "work site")):
                    return _clean_location(candidate)
    for line in lines[:8]:
        match = re.search(
            r"\s{2,}([A-Za-z.' -]+,\s*[A-Z]{2})(?:\s*$|\s{2,})", line
        )
        if match:
            return match.group(1).strip()
    address = re.search(
        r"(?:^|\n)(\d{1,6}\s+[^\n]{2,80})\n"
        r"([A-Za-z.' -]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)",
        content,
    )
    if address:
        return f"{address.group(1).strip()}, {address.group(2).strip()}"
    # Job boards frequently flatten the location into a standalone header line.
    # Prefer ZIP-bearing values because they are much less likely to be prose or
    # an unrelated recommendation card in a noisy capture.
    for line in lines[:50]:
        candidate = re.search(
            r"(?<![A-Za-z])((?:\d{1,6}\s+[^\n,]{2,55},\s*)?"
            r"[A-Za-z.' -]{2,55},\s*(?:[A-Z]{2}|Texas)\s+\d{5}(?:-\d{4})?)\b",
            line,
        )
        if candidate:
            return candidate.group(1).strip(" ,")
    for line in lines[:20]:
        candidate = re.fullmatch(r"([A-Za-z.' -]{2,55},\s*[A-Z]{2})", line)
        if candidate:
            return candidate.group(1).strip()
    return ""


def _clean_location(value: str) -> str:
    match = re.match(r"^US,\s*([A-Z]{2}),\s*(.+)$", value)
    if match:
        return f"{match.group(2).strip()}, {match.group(1)}"
    return value.strip()


def _extract_pay(content: str) -> dict[str, str]:
    patterns = (
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:-|–|—|to)\s*"
        r"\$?\s*([\d,]+(?:\.\d+)?)\s*(?:/|per\s+)?"
        r"(hr|hour|yr|year|annum|month|week|survey)?",
        r"(?:range|salary)[^\n]{0,100}?([\d,]+(?:\.\d+)?)\s*"
        r"(?:-|–|—|to)\s*([\d,]+(?:\.\d+)?)\s*(USD|CAD)?",
    )
    matches: list[tuple[float, float, str, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            low = float(match.group(1).replace(",", ""))
            high = float(match.group(2).replace(",", ""))
            suffix = (match.group(3) or "").casefold()
            nearby = content[max(0, match.start() - 80):match.end() + 80]
            currency = "CAD" if re.search(r"\bCAD\b", nearby) else "USD"
            period = _pay_period(suffix, nearby, high)
            matches.append((low, high, currency, period))
    if not matches:
        single = re.search(
            r"(?:\bpay(?: rate)?\s*:?\s*)?\$\s*([\d,]+(?:\.\d+)?)\s*"
            r"(?:/|an?\s+|per\s+)?(hour|hr|year|yr|month|week|annum|annually)\b",
            content, re.I,
        )
        if not single:
            return {}
        amount = float(single.group(1).replace(",", ""))
        nearby = content[max(0, single.start() - 40):single.end() + 40]
        period = _pay_period(single.group(2), nearby, amount)
        return {
            "pay_min": _number_text(amount),
            "pay_max": _number_text(amount),
            "currency": "CAD" if re.search(r"\bCAD\b", nearby) else "USD",
            "pay_period": period,
        }
    # Multiple location/level bands describe one posting; retain their envelope.
    low = min(item[0] for item in matches)
    high = max(item[1] for item in matches)
    currency = "CAD" if all(item[2] == "CAD" for item in matches) else "USD"
    periods = [item[3] for item in matches if item[3]]
    period = max(set(periods), key=periods.count) if periods else ""
    return {
        "pay_min": _number_text(low),
        "pay_max": _number_text(high),
        "currency": currency,
        "pay_period": period,
    }


def _pay_period(suffix: str, nearby: str, high: float) -> str:
    text = f"{suffix} {nearby}".casefold()
    if re.search(r"\b(?:hr|hour|hourly)\b", text):
        return "hour"
    if re.search(r"\b(?:yr|year|annual|annum|salary)\b", text):
        return "year"
    if "month" in text:
        return "month"
    if "week" in text:
        return "week"
    if "survey" in text:
        return "survey"
    return "year" if high >= 10000 else ""


def _number_text(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _best_title_candidate(lines: list[str], content: str) -> str:
    candidates: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines[:30]):
        cleaned = line.strip(" -–—•")
        lowered = cleaned.casefold()
        words = set(re.findall(r"[a-z]+", lowered))
        if (
            not cleaned or len(cleaned) > 125 or lowered in _GENERIC_HEADINGS
            or not words & _TITLE_WORDS
        ):
            continue
        title_pattern_match = re.search(
            rf"\b{_TITLE_PATTERN}\b", cleaned, re.IGNORECASE
        )
        if not title_pattern_match and cleaned.casefold() not in {"sre"}:
            continue
        score = 8 - min(index, 8)
        if len(cleaned.split()) <= 10:
            score += 5
        if index == 0:
            score += 12
        if title_pattern_match:
            score += 3
        if re.search(r"\b(?:we|you|our|your|this|the)\b", lowered):
            score -= 5
        if cleaned.endswith(('.', '!', '?')):
            score -= 3
        candidates.append((score, -index, cleaned))

    prose_patterns = (
        rf"\b(?:seeking|hiring|hire|looking\s+for)\s+(?:an?\s+)?([^.!?\n]{{2,90}}?\b{_TITLE_PATTERN}\b[^.!?\n]{{0,55}}?)(?=\s+(?:to|who|at|for|with|\.|,))",
        rf"(?:^|[.!?]\s+|\n)As\s+(?:an?\s+|our\s+)?([^.!?\n]{{2,90}}?\b{_TITLE_PATTERN}\b[^.!?\n]{{0,45}}?)(?=\s+(?:at|,|you|who|will))",
        rf"\b(?:role|position)\s+(?:of|is)\s+(?:an?\s+)?([^.!?\n]{{2,90}}?\b{_TITLE_PATTERN}\b[^.!?\n]{{0,45}}?)(?=\s+(?:at|,|who|to|\.))",
        rf"(?:^|[.!?]\s+|\n)(?:The|An?)\s+([^.!?\n]{{2,90}}?\b{_TITLE_PATTERN}\b[^.!?\n]{{0,45}}?)(?=\s+is\s)",
        r"\bThe\s+([A-Z][A-Za-z]+/[A-Za-z]+)\s+(?=performs|will|is)\b",
        rf"(?:^|[.!?]\s+|\n)The\s+([^.!?\n]{{2,80}}?\b{_TITLE_PATTERN}\b)\s+will\b",
    )
    for pattern in prose_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            candidate = re.sub(r"\s+", " ", match.group(1)).strip(" ,")
            candidates.append((15, -99, candidate))
    best = max(candidates, default=(0, 0, ""))
    if best[0] < 5:
        return ""
    candidate = best[2]
    candidate = re.sub(
        r"^(?:an?\s+)?(?:(?:and\s+)?(?:exceptional|experienced|great|strategic|"
        r"highly skilled|highly experienced|talented|seasoned|skilled)\s+)+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    return _clean_title(candidate)


def _extract_company(content: str, lines: list[str]) -> str:
    committed = re.search(
        r"(?:^|\n)([A-Z][A-Za-z0-9&.\- ]{1,70}?)\s+is committed to\b",
        content,
        re.MULTILINE,
    )
    if committed and _valid_company(committed.group(1)):
        return committed.group(1).strip()
    patterns = (
        r"(?:^|\n)([A-Z][A-Za-z0-9&'â€™.,\- ]{1,80}?)\s+provided pay range\b",
        r"(?:^|\n)\s*(?:Company|Employer|Organization)\s*:\s*([^\n]{2,100})",
        r"(?:^|\n)\s*About\s+Us\s+([A-Za-z][A-Za-z0-9&'’.\- ]{1,70}?)\s+is\b",
        r"(?:^|\n)\s*About\s+([A-Z][A-Za-z0-9&'’.,\- ]{1,80})\s*:?\s*(?:\n|$)",
        r"(?:^|[.!?]\s+|\n)At\s+([A-Za-z][A-Za-z0-9&'’.\- ]{1,70}?),\s+(?:we|our|you)",
        r"\bat\s+([A-Z][A-Za-z0-9&'’.\-]*(?:\s+[A-Z][A-Za-z0-9&'’.\-]*){0,4})(?=\.|,\s+(?:this|you|we))",
        r"(?:^|[.!?]\s+|\n)([A-Z][A-Za-z0-9&.,\-]*(?:\s+[A-Z][A-Za-z0-9&.,\-]*){0,4})\s+is\s+(?:an?|the|looking|seeking|your)\b",
        rf"\bAs\s+(?:an?\s+)?[^.!?\n]{{2,90}}?\b{_TITLE_PATTERN}\b\s+at\s+([A-Z][A-Za-z0-9&'’.\- ]{{1,70}}?)(?=,|\s+you\b)",
        r"(?:^|[.!?]\s+|\n)([A-Z][A-Za-z0-9&.\- ]{1,70}?)['’]s\s+(?:mission|team|Cybersecurity|platform)\b",
        r"(?:^|[.!?]\s+|\n)(?:Imagine\s+)?working\s+at\s+([A-Z][A-Za-z0-9&'’.\- ]{1,70}?)(?=\s+to|,|\.)",
        r"(?:^|[.!?]\s+|\n)Choosing\s+([A-Z][A-Za-z0-9&'’.\- ]{1,70}?)\s+means\b",
        r"(?:^|[.!?]\s+|\n)([A-Z][A-Za-z0-9&'’.\- ]{1,70}?)\s+(?:has been|builds|protects)\b",
        r"interest\s+in\s+employment\s+with\s+([A-Z][A-Za-z0-9&'’.\- ]{1,70}?)(?=\.|,)",
    )
    for pattern in patterns:
        match = re.search(pattern, content, re.MULTILINE)
        if not match:
            continue
        candidate = re.sub(r"\s+", " ", match.group(1)).strip(" ,:-")
        candidate = re.sub(
            r"^(?:Full[- ]time|Part[- ]time)\s+", "", candidate, flags=re.I
        )
        candidate = re.sub(
            r"^(?:CP-[A-Z0-9-]+|JR\d{5,}|ID\d{4,}|\d{5,}BR)\s+",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        if _valid_company(candidate):
            return candidate

    if lines:
        first = lines[0].strip(" ,:-")
        if (
            len(first) <= 80
            and _COMPANY_SUFFIX.search(first)
            and not set(re.findall(r"[a-z]+", first.casefold())) & _TITLE_WORDS
        ):
            return first
    return ""


def _valid_company(candidate: str) -> bool:
    normalized = re.sub(r"\s+", " ", candidate).strip().casefold()
    if len(normalized) < 2 or normalized in _NON_COMPANIES:
        return False
    words = normalized.split()
    if len(words) > 8:
        return False
    return not any(word in {"will", "your", "role"} for word in words)
