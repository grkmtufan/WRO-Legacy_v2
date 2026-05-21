#!/usr/bin/env python3
"""
Custom Raspberry Pi functions to be called from SPIKE via SpiBerryEngine.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2

from color_grid_detector import (
    auto_detect_and_read_grid,
    board_plan_to_csv,
    build_board_plan,
    capture_frame,
    plan_to_dict,
)


DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 960
DEFAULT_CAMERA_INDEX = 0
DEFAULT_MARGIN = 0.18
LAST_JSON_PATH = Path("last_detection_from_spike.json")
LAST_IMAGE_PATH = Path("last_detection_from_spike.jpg")


def analyze_board(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    camera_index: int = DEFAULT_CAMERA_INDEX,
    margin: float = DEFAULT_MARGIN,
) -> dict[str, object]:
    frame = capture_frame(width, height, camera_index)
    grid, scores, annotated, polygon = auto_detect_and_read_grid(
        frame,
        rows=6,
        cols=2,
        margin_fraction=margin,
        roi=None,
        auto_detect=True,
    )
    plan = build_board_plan(grid, scores)

    result = {
        "grid": grid,
        "scores": scores,
        "board_polygon": polygon,
        "plan": plan_to_dict(plan),
        "csv": board_plan_to_csv(plan),
    }

    LAST_JSON_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    cv2.imwrite(str(LAST_IMAGE_PATH), annotated)
    return result


def detect() -> str:
    return str(analyze_board()["csv"])


def get_pick_plan_csv() -> str:
    return detect()


def get_front_pick_sequence_csv() -> str:
    result = analyze_board()
    return ",".join(result["plan"]["front"]["pick_sequence"])


def get_back_pick_sequence_csv() -> str:
    result = analyze_board()
    return ",".join(result["plan"]["back"]["pick_sequence"])


def get_plan_json() -> str:
    return json.dumps(analyze_board())
