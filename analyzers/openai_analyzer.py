from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from openai import OpenAI


SYSTEM_PROMPT = (
    "You are an objective insurer-ready robotics incident analyst. "
    "Avoid speculation. Separate direct observations from inference. "
    "Return strict JSON only."
)

SCHEMA_EXAMPLE = {
    "incident_type": "robot_fall_with_spill | robot_fall | object_drop | unclear",
    "confidence": 0.0,
    "timeline": {
        "loss_of_balance_s": None,
        "impact_s": None,
        "spill_s": None,
    },
    "observations": ["..."],
    "environmental_factors": ["..."],
    "human_involvement": "none | visible | unclear",
    "summary": "...",
    "inputs": {"incidentId": "...", "videoObjectKey": "...", "logObjectKey": None, "hintWindow": {"start_s": 0.0, "end_s": 0.0}},
    "generatedAt": "ISO8601",
    "mode": "ai",
}

USER_PROMPT = (
    "Context: This is a first-person camera mounted on a service robot carrying food/dishes. "
    "The incident occurs within the provided hint window. "
    "Task: Determine whether the robot loses balance / falls and whether dishes/food spill. "
    "Be objective and insurer-ready. Do not speculate beyond what is visible. "
    "\n\nReturn ONLY a single valid JSON object (no markdown, no extra text) "
    "that matches this schema EXACTLY (use these exact keys):\n"
    + json.dumps(SCHEMA_EXAMPLE, ensure_ascii=False, indent=2)
    + "\n\nRules:\n"
    "- Use incident_type exactly as one of: robot_fall_with_spill, robot_fall, object_drop, unclear\n"
    "- confidence must be a number between 0 and 1\n"
    "- timeline fields must be numbers (seconds) or null\n"
    "- observations/environmental_factors must be arrays of short strings\n"
    "- human_involvement must be one of: none, visible, unclear\n"
    "- If unsure, use null/unclear rather than guessing\n"
)
def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    # Common model variations
    key_map = {
        "incidentType": "incident_type",
        "environmentalFactors": "environmental_factors",
        "humanInvolvement": "human_involvement",
    }
    for src, dst in key_map.items():
        if src in payload and dst not in payload:
            payload[dst] = payload.pop(src)

    # Ensure timeline keys are snake_case
    if isinstance(payload.get("timeline"), dict):
        tl = payload["timeline"]
        tl_map = {
            "lossOfBalanceS": "loss_of_balance_s",
            "loss_of_balance": "loss_of_balance_s",
            "impactS": "impact_s",
            "spillS": "spill_s",
        }
        for src, dst in tl_map.items():
            if src in tl and dst not in tl:
                tl[dst] = tl.pop(src)

    return payload


def _encode_image(path: str) -> str:
    with open(path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON object found in response")
        return json.loads(text[start : end + 1])


def _validate_schema(payload: dict[str, Any]) -> None:
    required = [
        "incident_type",
        "confidence",
        "timeline",
        "observations",
        "environmental_factors",
        "human_involvement",
        "summary",
        "inputs",
        "generatedAt",
        "mode",
    ]
    if "timeline" in payload and not isinstance(payload.get("timeline"), dict):
        raise ValueError("timeline must be an object")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Missing keys in analysis: {', '.join(missing)}")


def analyze(
    api_key: str,
    model: str,
    keyframes: Iterable[str],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    client = OpenAI(api_key=api_key)
    images = []
    for path in keyframes:
        encoded = _encode_image(path)
        images.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
            }
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": USER_PROMPT},
                {"type": "text", "text": json.dumps(inputs)},
                *images,
            ],
        },
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    content = response.choices[0].message.content or ""
    payload = _extract_json(content)
    payload = _normalize_payload(payload)
    # Always inject inputs; the worker is the source of truth for these.
    payload["inputs"] = inputs
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat()
    payload["mode"] = "ai"
    _validate_schema(payload)
    return payload
