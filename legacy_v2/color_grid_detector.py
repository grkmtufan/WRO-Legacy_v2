#!/usr/bin/env python3
"""
Detect the dominant color in a side-view WRO board using a Raspberry Pi camera.

Current game model:
- The board is read as 6 rows x 2 columns after perspective correction.
- Left column is the front side.
- Right column is the back side.
- Each side is grouped vertically as top / middle / bottom, with 2 cells per group.
- A valid placement for one group is always a same-color pair.
- The planner chooses the best color pair for each group to maximize score.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None


COLOR_ORDER = ("YELLOW", "GREEN", "BLUE", "WHITE")
SIDE_ORDER = ("front", "back")
GROUP_ORDER = ("top", "middle", "bottom")
PICK_ORDER = ("top", "bottom", "middle")
GROUP_ROWS = {
    "top": (0, 1),
    "middle": (2, 3),
    "bottom": (4, 5),
}


@dataclass(frozen=True)
class HsvRange:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]


HSV_RANGES: dict[str, list[HsvRange]] = {
    "YELLOW": [HsvRange((16, 70, 90), (42, 255, 255))],
    "GREEN": [HsvRange((38, 45, 40), (92, 255, 255))],
    "BLUE": [HsvRange((90, 60, 40), (140, 255, 255))],
    "WHITE": [HsvRange((0, 0, 175), (179, 45, 255))],
}


@dataclass(frozen=True)
class CellCandidate:
    center: tuple[float, float]
    size: tuple[float, float]
    angle: float
    area: float
    color: str


@dataclass(frozen=True)
class PairChoice:
    group_name: str
    row_indices: tuple[int, int]
    color: str
    score: int
    confidence: float


@dataclass(frozen=True)
class SidePlan:
    side_name: str
    total_score: int
    placements: tuple[PairChoice, ...]
    pick_sequence: tuple[str, ...]


@dataclass(frozen=True)
class BoardPlan:
    total_score: int
    front: SidePlan
    back: SidePlan


def require_picamera2() -> type[Picamera2]:
    if Picamera2 is None:
        raise SystemExit(
            "picamera2 is required on Raspberry Pi. Install with: "
            "sudo apt install -y python3-picamera2"
        )
    return Picamera2


def order_points(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)

    top_left = points[np.argmin(sums)]
    bottom_right = points[np.argmax(sums)]
    top_right = points[np.argmin(diffs)]
    bottom_left = points[np.argmax(diffs)]
    return np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)


def four_point_transform(image: np.ndarray, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rect = order_points(points)
    top_left, top_right, bottom_right, bottom_left = rect

    width_top = np.linalg.norm(top_right - top_left)
    width_bottom = np.linalg.norm(bottom_right - bottom_left)
    max_width = int(max(width_top, width_bottom))

    height_left = np.linalg.norm(bottom_left - top_left)
    height_right = np.linalg.norm(bottom_right - top_right)
    max_height = int(max(height_left, height_right))

    max_width = max(max_width, 250)
    max_height = max(max_height, 500)

    destination = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(rect, destination)
    warped = cv2.warpPerspective(image, matrix, (max_width, max_height))
    return warped, rect


def contour_to_quad(contour: np.ndarray) -> np.ndarray:
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)

    if len(approx) == 4:
        return np.asarray(approx.reshape(4, 2), dtype=np.float32)

    rect = cv2.minAreaRect(contour)
    return np.asarray(cv2.boxPoints(rect), dtype=np.float32)


def is_valid_board_quad(quad: np.ndarray, image_area: int) -> tuple[bool, float]:
    ordered = order_points(quad)
    area = cv2.contourArea(ordered.astype(np.float32))
    if area < image_area * 0.04:
        return False, 0.0

    width = max(
        np.linalg.norm(ordered[1] - ordered[0]),
        np.linalg.norm(ordered[2] - ordered[3]),
    )
    height = max(
        np.linalg.norm(ordered[3] - ordered[0]),
        np.linalg.norm(ordered[2] - ordered[1]),
    )
    if width <= 0 or height <= 0:
        return False, 0.0

    aspect_ratio = height / width
    if not 1.6 <= aspect_ratio <= 4.5:
        return False, 0.0

    return True, area


def build_mask(hsv_image: np.ndarray, color_name: str) -> np.ndarray:
    masks = []
    for hsv_range in HSV_RANGES[color_name]:
        lower = np.array(hsv_range.lower, dtype=np.uint8)
        upper = np.array(hsv_range.upper, dtype=np.uint8)
        masks.append(cv2.inRange(hsv_image, lower, upper))
    mask = masks[0]
    for extra in masks[1:]:
        mask = cv2.bitwise_or(mask, extra)
    return mask


def build_board_color_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    combined = np.zeros(hsv.shape[:2], dtype=np.uint8)

    for color_name in COLOR_ORDER:
        combined = cv2.bitwise_or(combined, build_mask(hsv, color_name))

    kernel = np.ones((9, 9), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)
    combined = cv2.dilate(combined, kernel, iterations=1)
    return combined


def detect_colored_cells(image: np.ndarray) -> list[CellCandidate]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    image_area = image.shape[0] * image.shape[1]
    candidates: list[CellCandidate] = []

    for color_name in COLOR_ORDER:
        mask = build_mask(hsv, color_name)
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < image_area * 0.003 or area > image_area * 0.20:
                continue

            rect = cv2.minAreaRect(contour)
            (cx, cy), (width, height), angle = rect
            if width <= 1 or height <= 1:
                continue

            aspect_ratio = max(width, height) / min(width, height)
            if aspect_ratio > 2.4:
                continue

            box = cv2.boxPoints(rect)
            box_area = cv2.contourArea(box.astype(np.float32))
            if box_area <= 0:
                continue

            fill_ratio = area / box_area
            if fill_ratio < 0.55:
                continue

            candidates.append(
                CellCandidate(
                    center=(float(cx), float(cy)),
                    size=(float(width), float(height)),
                    angle=float(angle),
                    area=float(area),
                    color=color_name,
                )
            )

    candidates.sort(key=lambda candidate: candidate.area, reverse=True)
    deduped: list[CellCandidate] = []
    for candidate in candidates:
        too_close = False
        for kept in deduped:
            if np.linalg.norm(np.subtract(candidate.center, kept.center)) < 18:
                too_close = True
                break
        if not too_close:
            deduped.append(candidate)

    return deduped


def board_polygon_from_cells(cells: list[CellCandidate]) -> np.ndarray | None:
    if len(cells) < 6:
        return None

    cells = cells[:12]
    centers = np.array([candidate.center for candidate in cells], dtype=np.float32)
    mean = centers.mean(axis=0)

    centered = centers - mean
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    axis_x = vh[0]
    axis_y = vh[1]
    if axis_y[1] < 0:
        axis_y = -axis_y
    if axis_x[0] < 0:
        axis_x = -axis_x

    proj_x = centered @ axis_x
    proj_y = centered @ axis_y

    median_width = float(np.median([max(candidate.size) for candidate in cells]))
    median_height = float(np.median([min(candidate.size) for candidate in cells]))

    half_w = max(median_width * 0.75, 20.0)
    half_h = max(median_height * 0.75, 20.0)

    min_x = float(np.min(proj_x) - half_w)
    max_x = float(np.max(proj_x) + half_w)
    min_y = float(np.min(proj_y) - half_h)
    max_y = float(np.max(proj_y) + half_h)

    corners = np.array(
        [
            mean + axis_x * min_x + axis_y * min_y,
            mean + axis_x * max_x + axis_y * min_y,
            mean + axis_x * max_x + axis_y * max_y,
            mean + axis_x * min_x + axis_y * max_y,
        ],
        dtype=np.float32,
    )
    return order_points(corners)


def find_board_polygon(image: np.ndarray) -> np.ndarray | None:
    image_area = image.shape[0] * image.shape[1]
    candidates: list[tuple[float, np.ndarray]] = []

    cell_candidates = detect_colored_cells(image)
    cell_polygon = board_polygon_from_cells(cell_candidates)
    if cell_polygon is not None:
        valid, area = is_valid_board_quad(cell_polygon, image_area)
        if valid:
            candidates.append((area * 1.35, cell_polygon))

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 60, 180)
    kernel = np.ones((5, 5), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    edge_contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in edge_contours:
        quad = contour_to_quad(contour)
        valid, area = is_valid_board_quad(quad, image_area)
        if valid:
            candidates.append((area, order_points(quad)))

    color_mask = build_board_color_mask(image)
    color_contours, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in color_contours:
        quad = contour_to_quad(contour)
        valid, area = is_valid_board_quad(quad, image_area)
        if valid:
            candidates.append((area * 1.15, order_points(quad)))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect the color of each cell in the 6x2 side-view board."
    )
    parser.add_argument("--rows", type=int, default=6, help="Grid row count.")
    parser.add_argument("--cols", type=int, default=2, help="Grid column count.")
    parser.add_argument("--width", type=int, default=1280, help="Camera width.")
    parser.add_argument("--height", type=int, default=960, help="Camera height.")
    parser.add_argument(
        "--margin",
        type=float,
        default=0.18,
        help="Ignore this fraction around each cell border.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("last_detection.json"),
        help="Where to save detection results as JSON.",
    )
    parser.add_argument(
        "--image-output",
        type=Path,
        default=Path("last_detection.jpg"),
        help="Where to save the annotated image.",
    )
    parser.add_argument(
        "--roi",
        nargs=4,
        type=int,
        metavar=("X", "Y", "W", "H"),
        help="Optional ROI for the board inside the frame.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show live camera preview with detected cell colors.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Picamera2 camera index.",
    )
    parser.add_argument(
        "--no-auto-detect",
        action="store_true",
        help="Disable automatic board detection and use the full frame or ROI.",
    )
    return parser.parse_args()


def classify_patch(bgr_patch: np.ndarray) -> tuple[str, dict[str, float]]:
    if bgr_patch.size == 0:
        return "WHITE", {color_name: 0.0 for color_name in COLOR_ORDER}

    hsv_patch = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2HSV)
    total_pixels = float(hsv_patch.shape[0] * hsv_patch.shape[1])
    scores: dict[str, float] = {}

    for color_name in COLOR_ORDER:
        mask = build_mask(hsv_patch, color_name)
        scores[color_name] = float(cv2.countNonZero(mask)) / total_pixels

    mean_s = float(np.mean(hsv_patch[:, :, 1]))
    mean_v = float(np.mean(hsv_patch[:, :, 2]))

    color_only_scores = {name: scores[name] for name in ("YELLOW", "GREEN", "BLUE")}
    best_color = max(color_only_scores, key=color_only_scores.get)
    best_color_score = color_only_scores[best_color]
    white_score = scores["WHITE"]

    if mean_s < 55 and mean_v > 120 and white_score >= best_color_score * 0.9:
        detected_color = "WHITE"
    else:
        detected_color = best_color

    if max(scores.values()) < 0.05:
        detected_color = "WHITE"

    return detected_color, scores


def detect_grid(
    image: np.ndarray,
    rows: int,
    cols: int,
    margin_fraction: float,
    roi: tuple[int, int, int, int] | None,
) -> tuple[list[list[str]], list[list[dict[str, float]]], np.ndarray]:
    annotated = image.copy()

    if roi is None:
        x0, y0 = 0, 0
        width = image.shape[1]
        height = image.shape[0]
    else:
        x0, y0, width, height = roi

    cell_width = width / cols
    cell_height = height / rows

    grid: list[list[str]] = []
    score_grid: list[list[dict[str, float]]] = []

    for row in range(rows):
        row_colors: list[str] = []
        row_scores: list[dict[str, float]] = []

        for col in range(cols):
            cell_x1 = int(x0 + col * cell_width)
            cell_y1 = int(y0 + row * cell_height)
            cell_x2 = int(x0 + (col + 1) * cell_width)
            cell_y2 = int(y0 + (row + 1) * cell_height)

            inset_x = int((cell_x2 - cell_x1) * margin_fraction)
            inset_y = int((cell_y2 - cell_y1) * margin_fraction)

            sample_x1 = cell_x1 + inset_x
            sample_y1 = cell_y1 + inset_y
            sample_x2 = cell_x2 - inset_x
            sample_y2 = cell_y2 - inset_y

            patch = image[sample_y1:sample_y2, sample_x1:sample_x2]
            detected_color, scores = classify_patch(patch)

            row_colors.append(detected_color)
            row_scores.append(scores)

            cv2.rectangle(annotated, (cell_x1, cell_y1), (cell_x2, cell_y2), (0, 0, 0), 2)
            cv2.rectangle(
                annotated,
                (sample_x1, sample_y1),
                (sample_x2, sample_y2),
                (255, 255, 255),
                1,
            )
            cv2.putText(
                annotated,
                detected_color,
                (cell_x1 + 8, cell_y1 + 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        grid.append(row_colors)
        score_grid.append(row_scores)

    if roi is not None:
        cv2.rectangle(annotated, (x0, y0), (x0 + width, y0 + height), (0, 255, 255), 2)

    return grid, score_grid, annotated


def auto_detect_and_read_grid(
    image: np.ndarray,
    rows: int,
    cols: int,
    margin_fraction: float,
    roi: tuple[int, int, int, int] | None,
    auto_detect: bool,
) -> tuple[list[list[str]], list[list[dict[str, float]]], np.ndarray, list[list[float]] | None]:
    if roi is not None:
        grid, score_grid, annotated = detect_grid(image, rows, cols, margin_fraction, roi)
        return grid, score_grid, annotated, None

    if not auto_detect:
        grid, score_grid, annotated = detect_grid(image, rows, cols, margin_fraction, None)
        return grid, score_grid, annotated, None

    polygon = find_board_polygon(image)
    if polygon is None:
        grid, score_grid, annotated = detect_grid(image, rows, cols, margin_fraction, None)
        cv2.putText(
            annotated,
            "AUTO DETECT FAILED",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            3,
            cv2.LINE_AA,
        )
        return grid, score_grid, annotated, None

    warped, ordered_polygon = four_point_transform(image, polygon)
    grid, score_grid, board_annotated = detect_grid(warped, rows, cols, margin_fraction, None)

    annotated = image.copy()
    cv2.polylines(
        annotated,
        [ordered_polygon.astype(np.int32)],
        isClosed=True,
        color=(0, 255, 255),
        thickness=3,
    )
    cv2.putText(
        annotated,
        "BOARD",
        tuple(ordered_polygon[0].astype(np.int32) + np.array([0, -10])),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    preview_height = min(board_annotated.shape[0], image.shape[0] // 2)
    preview_width = min(board_annotated.shape[1], image.shape[1] // 2)
    board_preview = cv2.resize(board_annotated, (preview_width, preview_height))
    annotated[0:preview_height, 0:preview_width] = board_preview

    return grid, score_grid, annotated, ordered_polygon.tolist()


def score_pair_for_color(cells: list[str], color_name: str) -> int:
    return sum(1 for cell in cells if cell == color_name)


def confidence_pair_for_color(scores: list[dict[str, float]], color_name: str) -> float:
    return sum(cell_scores.get(color_name, 0.0) for cell_scores in scores)


def choose_pair_for_group(
    group_name: str,
    row_indices: tuple[int, int],
    cells: list[str],
    scores: list[dict[str, float]],
) -> PairChoice:
    best_color = COLOR_ORDER[0]
    best_score = -1
    best_confidence = -1.0

    for color_name in COLOR_ORDER:
        score = score_pair_for_color(cells, color_name)
        confidence = confidence_pair_for_color(scores, color_name)
        if score > best_score:
            best_color = color_name
            best_score = score
            best_confidence = confidence
            continue
        if score == best_score and confidence > best_confidence:
            best_color = color_name
            best_confidence = confidence

    return PairChoice(
        group_name=group_name,
        row_indices=row_indices,
        color=best_color,
        score=best_score,
        confidence=best_confidence,
    )


def build_side_plan(
    grid: list[list[str]],
    score_grid: list[list[dict[str, float]]],
    side_name: str,
    column_index: int,
) -> SidePlan:
    placements: list[PairChoice] = []

    for group_name in GROUP_ORDER:
        row_indices = GROUP_ROWS[group_name]
        cells = [grid[row_index][column_index] for row_index in row_indices]
        scores = [score_grid[row_index][column_index] for row_index in row_indices]
        placements.append(choose_pair_for_group(group_name, row_indices, cells, scores))

    placement_by_group = {placement.group_name: placement for placement in placements}
    pick_sequence = tuple(placement_by_group[group_name].color for group_name in PICK_ORDER)
    total_score = sum(placement.score for placement in placements)

    return SidePlan(
        side_name=side_name,
        total_score=total_score,
        placements=tuple(placements),
        pick_sequence=pick_sequence,
    )


def build_board_plan(
    grid: list[list[str]],
    score_grid: list[list[dict[str, float]]],
) -> BoardPlan:
    front_plan = build_side_plan(grid, score_grid, "front", 0)
    back_plan = build_side_plan(grid, score_grid, "back", 1)
    return BoardPlan(
        total_score=front_plan.total_score + back_plan.total_score,
        front=front_plan,
        back=back_plan,
    )


def side_plan_to_dict(plan: SidePlan) -> dict[str, object]:
    return {
        "side": plan.side_name,
        "total_score": plan.total_score,
        "pick_order": list(PICK_ORDER),
        "pick_sequence": list(plan.pick_sequence),
        "placements": [
            {
                "group_name": placement.group_name,
                "row_indices": list(placement.row_indices),
                "color": placement.color,
                "score": placement.score,
                "confidence": placement.confidence,
            }
            for placement in plan.placements
        ],
    }


def plan_to_dict(plan: BoardPlan) -> dict[str, object]:
    return {
        "total_score": plan.total_score,
        "front": side_plan_to_dict(plan.front),
        "back": side_plan_to_dict(plan.back),
    }


def board_plan_to_csv(plan: BoardPlan) -> str:
    parts = [
        "FRONT",
        *plan.front.pick_sequence,
        "BACK",
        *plan.back.pick_sequence,
    ]
    return ",".join(parts)


def capture_frame(width: int, height: int, camera_index: int) -> np.ndarray:
    camera = open_camera(width, height, camera_index)
    try:
        return normalize_frame(camera.capture_array())
    finally:
        camera.stop()


def open_camera(width: int, height: int, camera_index: int):
    picamera2_class = require_picamera2()
    camera = picamera2_class(camera_index)
    config = camera.create_preview_configuration(
        main={"size": (width, height), "format": "BGR888"}
    )
    camera.configure(config)
    camera.start()
    time.sleep(1.2)
    return camera


def normalize_frame(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 3 and frame.shape[2] == 3:
        return frame

    if frame.ndim == 3 and frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    if frame.ndim == 3 and frame.shape[2] == 2:
        return cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_YUYV)

    raise RuntimeError(f"Unsupported camera frame shape: {frame.shape}")


def preview_loop(args: argparse.Namespace) -> int:
    camera = open_camera(args.width, args.height, args.camera_index)

    try:
        while True:
            frame = normalize_frame(camera.capture_array())
            grid, scores, annotated, polygon = auto_detect_and_read_grid(
                frame,
                args.rows,
                args.cols,
                args.margin,
                tuple(args.roi) if args.roi else None,
                auto_detect=not args.no_auto_detect,
            )
            plan = build_board_plan(grid, scores)

            result = {
                "grid": grid,
                "scores": scores,
                "rows": args.rows,
                "cols": args.cols,
                "roi": tuple(args.roi) if args.roi else None,
                "board_polygon": polygon,
                "plan": plan_to_dict(plan),
                "csv": board_plan_to_csv(plan),
            }
            args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            cv2.imwrite(str(args.image_output), annotated)

            print("\033[2J\033[H", end="")
            print("Detected grid:")
            for row in grid:
                print(" ".join(f"{cell[:1]:>6}" for cell in row))
            print(f"\nFront pick sequence: {' '.join(plan.front.pick_sequence)}")
            print(f"Back pick sequence: {' '.join(plan.back.pick_sequence)}")
            print(f"Total score: {plan.total_score}")
            print(f"CSV: {board_plan_to_csv(plan)}")
            print("\nPress Q in the preview window to quit.")

            cv2.imshow("WRO Grid Preview", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                break
    finally:
        camera.stop()
        cv2.destroyAllWindows()

    return 0


def main() -> int:
    args = parse_args()
    if args.preview:
        return preview_loop(args)

    frame = capture_frame(args.width, args.height, args.camera_index)
    roi = tuple(args.roi) if args.roi else None
    grid, scores, annotated, polygon = auto_detect_and_read_grid(
        frame,
        args.rows,
        args.cols,
        args.margin,
        roi,
        auto_detect=not args.no_auto_detect,
    )
    plan = build_board_plan(grid, scores)

    result = {
        "grid": grid,
        "scores": scores,
        "rows": args.rows,
        "cols": args.cols,
        "roi": roi,
        "board_polygon": polygon,
        "plan": plan_to_dict(plan),
        "csv": board_plan_to_csv(plan),
    }

    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    cv2.imwrite(str(args.image_output), annotated)

    print("Detected grid:")
    for row in grid:
        print(" ".join(f"{cell:>6}" for cell in row))
    print("\nFront side:")
    print(f"Pick sequence: {' '.join(plan.front.pick_sequence)}")
    print(f"Score: {plan.front.total_score}")
    print("\nBack side:")
    print(f"Pick sequence: {' '.join(plan.back.pick_sequence)}")
    print(f"Score: {plan.back.total_score}")
    print(f"\nTotal score: {plan.total_score}")
    print(f"CSV: {board_plan_to_csv(plan)}")
    print(f"\nJSON saved to: {args.output}")
    print(f"Annotated image saved to: {args.image_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
