import os
import subprocess
from typing import List


def run_command(command: List[str]) -> str:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Command failed")
    return result.stdout.strip()


def get_duration(video_path: str) -> float:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    output = run_command(command)
    try:
        return float(output)
    except ValueError as exc:
        raise RuntimeError("Unable to parse video duration") from exc


def extract_keyframes(
    video_path: str,
    output_dir: str,
    start_s: float,
    end_s: float,
    every_s: float,
    max_frames: int,
) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    duration = max(end_s - start_s, 0.1)
    if every_s <= 0:
        raise ValueError("every_s must be > 0")

    fps = 1.0 / every_s
    estimated_frames = int(duration * fps)
    if estimated_frames > max_frames and duration > 0:
        fps = max_frames / duration

    output_pattern = os.path.join(output_dir, "frame_%03d.jpg")
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_s:.3f}",
        "-to",
        f"{end_s:.3f}",
        "-i",
        video_path,
        "-vf",
        f"fps={fps:.4f}",
        "-q:v",
        "2",
        output_pattern,
    ]
    run_command(command)

    frames = sorted(
        os.path.join(output_dir, filename)
        for filename in os.listdir(output_dir)
        if filename.lower().endswith(".jpg")
    )
    if not frames:
        raise RuntimeError("No keyframes extracted")
    return frames
