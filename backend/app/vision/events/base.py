from dataclasses import dataclass


@dataclass(frozen=True)
class RallyEvent:
    time: str
    event_type: str
    label: str
    confidence: float
    evidence: str
