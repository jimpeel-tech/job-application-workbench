"""Structured result schema shared by generative analysis providers."""

JOB_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company": {"type": "string"},
        "title": {"type": "string"},
        "location": {"type": "string"},
        "remote_status": {
            "type": "string",
            "enum": ["Remote", "Hybrid", "On-site", "Unclear"],
        },
        "pay_min": {"type": ["number", "null"]},
        "pay_max": {"type": ["number", "null"]},
        "currency": {"type": "string"},
        "pay_period": {"type": "string"},
        "pay_disclosed": {"type": "boolean"},
        "match_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
        },
        "summary": {"type": "string"},
        "strong_matches": {
            "type": "array",
            "items": {"type": "string"},
        },
        "concerns": {
            "type": "array",
            "items": {"type": "string"},
        },
        "missing_qualifications": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "company",
        "title",
        "location",
        "remote_status",
        "pay_min",
        "pay_max",
        "currency",
        "pay_period",
        "pay_disclosed",
        "match_score",
        "summary",
        "strong_matches",
        "concerns",
        "missing_qualifications",
    ],
}
