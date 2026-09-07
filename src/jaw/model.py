from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class DateFormat(Enum):
    NUMERIC = ("11/2024", "%m/%Y", False)
    NUMERIC_SPLIT = ("11  →  2024", "%m", True)
    SHORT_SPLIT = ("Nov  →  2024", "%b", True)
    LONG_SPLIT = ("November  →  2024", "%B", True)

    def __init__(self, label: str, month_format: str, split: bool):
        self.label = label
        self.month_format = month_format
        self.split = split

    def values_for(self, value: date) -> list[str]:
        if self is DateFormat.NUMERIC:
            return [value.strftime("%m/%Y")]
        return [value.strftime(self.month_format), value.strftime("%Y")]


@dataclass(frozen=True)
class PasteItem:
    label: str
    value: str
    group: str
    item_id: str = ""
