from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    hint = payload.get("hintWindow", {"start_s": 3.0, "end_s": 5.0})
    return {
        "incident_type": "robot_fall_with_spill",
        "confidence": 0.80,
        "timeline": {
            "loss_of_balance_s": round(hint.get("start_s", 3.0), 1),
            "impact_s": round(hint.get("start_s", 3.0) + 1.1, 1),
            "spill_s": round(hint.get("start_s", 3.0) + 1.6, 1),
        },
        "observations": [
            "Placeholder analysis generated in dummy mode.",
            "Robot appears to lose balance and items spill after impact.",
        ],
        "environmental_factors": ["Possible slippery surface", "Load shift"],
        "human_involvement": "unclear",
        "summary": "Dummy analysis: robot fall with spill within hint window.",
        "inputs": payload,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "dummy",
    }
