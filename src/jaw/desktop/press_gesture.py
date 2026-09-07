from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PressResult = Literal["short", "long"]


@dataclass
class LongPressGesture:
    """Turn a physical press/release sequence into one short or long action."""

    threshold_ms: int
    key: str = ""
    started_at: float | None = None
    long_fired: bool = False

    @property
    def active(self) -> bool:
        return self.started_at is not None

    def begin(self, key: str, now: float) -> bool:
        if self.active:
            return False
        self.key = key.upper()
        self.started_at = now
        self.long_fired = False
        return True

    def poll(self, held: bool, now: float) -> PressResult | None:
        if self.started_at is None:
            return None
        if held:
            elapsed_ms = (now - self.started_at) * 1000
            if not self.long_fired and elapsed_ms + 1e-6 >= self.threshold_ms:
                self.long_fired = True
                return "long"
            return None
        result: PressResult | None = None if self.long_fired else "short"
        self.reset()
        return result

    def reset(self) -> None:
        self.key = ""
        self.started_at = None
        self.long_fired = False
