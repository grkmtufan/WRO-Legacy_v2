#!/usr/bin/env python3
"""
USB plan server for Raspberry Pi <-> SPIKE Prime communication.

Protocol:
- SPIKE sends: <<<GET_PLAN>>>
- Pi responds: <<<PLAN|DIRECTION|COLOR1,COLOR2,...>>>
- Pi can also respond with <<<ERROR|message>>>
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import serial

from color_grid_detector import (
    auto_detect_and_read_grid,
    capture_frame,
    choose_best_plan,
    plan_to_dict,
)


START_MARKER = "<<<"
END_MARKER = ">>>"
DEFAULT_REQUEST = "GET_PLAN"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve SPIKE plan requests over USB serial.")
    parser.add_argument("--port", default="/dev/ttyACM0", help="SPIKE serial device path.")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate.")
    parser.add_argument("--width", type=int, default=1280, help="Camera width.")
    parser.add_argument("--height", type=int, default=960, help="Camera height.")
    parser.add_argument("--camera-index", type=int, default=0, help="Camera index.")
    parser.add_argument("--margin", type=float, default=0.18, help="Detection cell margin fraction.")
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("usb_plan_server_last_plan.json"),
        help="Where to save the latest detected plan.",
    )
    return parser.parse_args()


def analyze_board(width: int, height: int, camera_index: int, margin: float) -> dict[str, object]:
    frame = capture_frame(width, height, camera_index)
    grid, scores, annotated, polygon = auto_detect_and_read_grid(
        frame,
        rows=4,
        cols=3,
        margin_fraction=margin,
        roi=None,
        auto_detect=True,
    )
    plan = choose_best_plan(grid)
    return {
        "grid": grid,
        "scores": scores,
        "board_polygon": polygon,
        "plan": plan_to_dict(plan),
    }


def format_plan_message(result: dict[str, object]) -> str:
    plan = result["plan"]
    direction = str(plan["direction"]).upper()
    pick_sequence = ",".join(plan["pick_sequence"])
    return f"{START_MARKER}PLAN|{direction}|{pick_sequence}{END_MARKER}"


def format_error_message(message: str) -> str:
    return f"{START_MARKER}ERROR|{message}{END_MARKER}"


def extract_requests(buffer: str) -> tuple[list[str], str]:
    requests: list[str] = []

    while True:
        start = buffer.find(START_MARKER)
        if start == -1:
            return requests, ""

        end = buffer.find(END_MARKER, start + len(START_MARKER))
        if end == -1:
            return requests, buffer[start:]

        payload = buffer[start + len(START_MARKER):end].strip()
        requests.append(payload)
        buffer = buffer[end + len(END_MARKER):]


def handle_request(request: str, args: argparse.Namespace) -> str:
    if request != DEFAULT_REQUEST:
        return format_error_message("UNKNOWN_REQUEST")

    try:
        result = analyze_board(args.width, args.height, args.camera_index, args.margin)
        args.log_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return format_plan_message(result)
    except Exception as exc:  # pragma: no cover - hardware path
        return format_error_message(str(exc).replace("\n", " "))


def main() -> int:
    args = parse_args()

    print(f"Opening serial port: {args.port}")
    with serial.Serial(args.port, args.baudrate, timeout=0.1) as connection:
        print("USB plan server is ready.")
        buffer = ""

        while True:
            incoming = connection.read(connection.in_waiting or 1)
            if incoming:
                buffer += incoming.decode("utf-8", errors="ignore")
                requests, buffer = extract_requests(buffer)

                for request in requests:
                    print(f"Received request: {request}")
                    response = handle_request(request, args)
                    connection.write(response.encode("utf-8"))
                    print(f"Sent response: {response}")

            time.sleep(0.01)


if __name__ == "__main__":
    raise SystemExit(main())
