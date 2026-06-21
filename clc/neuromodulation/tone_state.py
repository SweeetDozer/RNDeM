from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ToneState:
    integrity: float = 1.0
    stability: float = 0.8
    curiosity: float = 0.3
    risk_sensitivity: float = 0.5
    fatigue: float = 0.0
    tension: float = 0.1
    satisfaction: float = 0.0
    pain: float = 0.0

    def shifted(self, **deltas: float) -> "ToneState":
        values = self.as_debug_dict()
        for key, delta in deltas.items():
            values[key] = _clamp(values[key] + delta)
        return replace(self, **values)

    def as_debug_dict(self) -> dict[str, float]:
        return {
            "integrity": round(self.integrity, 3),
            "stability": round(self.stability, 3),
            "curiosity": round(self.curiosity, 3),
            "risk_sensitivity": round(self.risk_sensitivity, 3),
            "fatigue": round(self.fatigue, 3),
            "tension": round(self.tension, 3),
            "satisfaction": round(self.satisfaction, 3),
            "pain": round(self.pain, 3),
        }


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
