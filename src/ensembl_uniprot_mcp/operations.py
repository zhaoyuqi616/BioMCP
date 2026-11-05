"""Per-operation outbound budget and payload-free process health measurements."""

import time
from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass, field

ACTIVE = ContextVar("active_operation", default=None)
COUNTS = Counter()


@dataclass
class Operation:
    started: float = field(default_factory=time.monotonic)
    attempts: int = 0
    core_seconds: float | None = None

    @property
    def remaining(self):
        return max(0, 45 - (time.monotonic() - self.started))

    def summary(self):
        return {
            "core_seconds": self.core_seconds,
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "outbound_attempts": self.attempts,
            "max_attempts": 24,
            "deadline_seconds": 45,
        }
