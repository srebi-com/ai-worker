#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from analyzers.dummy_analyzer import analyze as analyze_dummy
from analyzers.openai_analyzer import analyze as analyze_openai
from r2_client import R2Client, load_r2_config
from video_tools import extract_keyframes, get_duration


logger = logging.getLogger("srebi-worker")


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def find_primary_file(meta: dict[str, Any], role: str) -> dict[str, Any] | None:
    files = meta.get("files", [])
    for entry in files:
        if entry.get("role") == role:
            return entry
    return None


def ensure_analysis_block(meta: dict[str, Any]) -> None:
    analysis = meta.get("analysis")
    if not isinstance(analysis, dict):
        meta["analysis"] = {}


def update_analysis_status(
    client: R2Client,
    incident_id: str,
    meta: dict[str, Any],
    status: str,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    ensure_analysis_block(meta)
    analysis = meta["analysis"]
    analysis["status"] = status
    analysis["objectKey"] = f"incidents/{incident_id}/derived/analysis.json"
    analysis["keyframesPrefix"] = f"incidents/{incident_id}/derived/keyframes/"
    analysis["updatedAt"] = datetime.now(timezone.utc).isoformat()
    if payload:
        analysis["incident_type"] = payload.get("incident_type")
        analysis["confidence"] = payload.get("confidence")
        analysis["timeline"] = payload.get("timeline")
        analysis["mode"] = payload.get("mode")
    if error:
        analysis["error"] = error

    meta_key = f"incidents/{incident_id}/meta.json"
    client.put_json(meta_key, meta)


def build_inputs(
    incident_id: str,
    video_object_key: str,
    log_object_key: str | None,
    hint_window: dict[str, float],
) -> dict[str, Any]:
    return {
        "incidentId": incident_id,
        "videoObjectKey": video_object_key,
        "logObjectKey": log_object_key,
        "hintWindow": hint_window,
    }


def main() -> int:
    load_dotenv(".env.local")

    parser = argparse.ArgumentParser(description="Srebi incident analysis worker")
    parser.add_argument("--incident", required=True, help="Incident ID")
    parser.add_argument("--hint-start", type=float, default=0.0)
    parser.add_argument("--hint-end", type=float, default=0.0)
    parser.add_argument("--mode", choices=["ai", "dummy"], default="dummy")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--every-s", type=float, default=0.5)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        config = load_r2_config()
        client = R2Client(config)
    except Exception as exc:
        logger.error("Failed to configure R2: %s", exc)
        return 2

    meta_key = f"incidents/{args.incident}/meta.json"
    meta = client.get_json(meta_key)
    if not meta:
        logger.error("Incident meta.json not found for %s", args.incident)
        return 3

    analysis_status = meta.get("analysis", {}).get("status")
    if analysis_status == "completed" and not args.force:
        logger.info("Analysis already completed. Use --force to rerun.")
        return 0

    video_entry = find_primary_file(meta, "video")
    if not video_entry:
        logger.error("No video file found in incident metadata.")
        return 4

    video_object_key = video_entry.get("objectKey")
    if not video_object_key:
        logger.error("Video entry missing objectKey.")
        return 5

    logs_entry = find_primary_file(meta, "logs")
    log_object_key = logs_entry.get("objectKey") if logs_entry else None

    workdir = os.path.join("workdir", args.incident)
    os.makedirs(workdir, exist_ok=True)
    input_path = os.path.join(workdir, "input.mp4")

    try:
        client.download(video_object_key, input_path)
    except Exception as exc:
        logger.error("Failed to download video: %s", exc)
        return 6

    try:
        duration = get_duration(input_path)
    except Exception as exc:
        logger.error("Failed to read video duration: %s", exc)
        return 7

    hint_start = clamp(args.hint_start, 0.0, duration)
    hint_end = clamp(args.hint_end, 0.0, duration)
    if hint_end <= hint_start:
        hint_start = 0.0
        hint_end = min(duration, max(hint_start + 1.0, 1.0))

    hint_window = {"start_s": hint_start, "end_s": hint_end}

    keyframe_dir = os.path.join(workdir, "keyframes")
    try:
        frames = extract_keyframes(
            input_path,
            keyframe_dir,
            hint_start,
            hint_end,
            args.every_s,
            args.max_frames,
        )
    except Exception as exc:
        logger.error("Failed to extract keyframes: %s", exc)
        update_analysis_status(client, args.incident, meta, "failed", error=str(exc))
        return 8

    keyframe_prefix = f"incidents/{args.incident}/derived/keyframes"
    for frame_path in frames:
        name = os.path.basename(frame_path)
        key = f"{keyframe_prefix}/{name}"
        try:
            client.upload(frame_path, key, "image/jpeg")
        except Exception as exc:
            logger.error("Failed to upload keyframe %s: %s", name, exc)
            update_analysis_status(
                client, args.incident, meta, "failed", error="keyframe upload failed"
            )
            return 9

    inputs = build_inputs(args.incident, video_object_key, log_object_key, hint_window)

    try:
        if args.mode == "ai":
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is required for ai mode")
            model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            analysis = analyze_openai(api_key, model, frames, inputs)
        else:
            analysis = analyze_dummy(inputs)
    except Exception as exc:
        logger.error("Analysis failed: %s", exc)
        update_analysis_status(client, args.incident, meta, "failed", error=str(exc))
        return 10

    analysis_key = f"incidents/{args.incident}/derived/analysis.json"
    analysis_payload = json.dumps(analysis, indent=2)
    analysis_path = os.path.join(workdir, "analysis.json")
    with open(analysis_path, "w", encoding="utf-8") as file:
        file.write(analysis_payload)

    try:
        client.upload(analysis_path, analysis_key, "application/json")
    except Exception as exc:
        logger.error("Failed to upload analysis.json: %s", exc)
        update_analysis_status(
            client, args.incident, meta, "failed", error="analysis upload failed"
        )
        return 11

    update_analysis_status(client, args.incident, meta, "completed", payload=analysis)
    logger.info("Analysis completed for %s", args.incident)
    return 0


if __name__ == "__main__":
    sys.exit(main())
