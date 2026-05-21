#!/usr/bin/env python3
"""
Capture an image on Raspberry Pi, let the user select a region, and generate
an HSV range around the average color of that region.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

try:
    from picamera2 import Picamera2
except ImportError as exc:  # pragma: no cover - runtime dependency on Pi
    raise SystemExit(
        "picamera2 is required on Raspberry Pi. Install with: "
        "sudo apt install -y python3-picamera2"
    ) from exc


DEFAULT_OFFSET = (10, 55, 55)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HSV ranges from a selected image region."
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=960)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--image", type=Path, help="Optional existing image path.")
    parser.add_argument(
        "--import",
        dest="import_image",
        action="store_true",
        help="Open a file picker and calibrate from an existing image.",
    )
    parser.add_argument("--label", default="color")
    parser.add_argument("--h-offset", type=int, default=DEFAULT_OFFSET[0])
    parser.add_argument("--s-offset", type=int, default=DEFAULT_OFFSET[1])
    parser.add_argument("--v-offset", type=int, default=DEFAULT_OFFSET[2])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("generated_color_range.json"),
        help="Where to save the generated range.",
    )
    parser.add_argument(
        "--captured-image",
        type=Path,
        default=Path("calibration_capture.jpg"),
        help="Where to save the captured calibration image.",
    )
    return parser.parse_args()


def choose_image_file() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("File picker is not available. Use --image /path/to/photo.jpg instead.")
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_path = filedialog.askopenfilename(
        title="Select calibration image",
        filetypes=[
            ("Image files", "*.jpg *.jpeg *.png *.bmp"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()

    if not file_path:
        return None
    return Path(file_path)


def open_camera(width: int, height: int, camera_index: int) -> Picamera2:
    camera = Picamera2(camera_index)
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


def capture_image(width: int, height: int, camera_index: int) -> np.ndarray:
    camera = open_camera(width, height, camera_index)
    try:
        return normalize_frame(camera.capture_array())
    finally:
        camera.stop()


def select_color_region_hsv_average(
    img: np.ndarray, title: str = "Select Color Region"
) -> tuple[int, int, int] | None:
    if img is None:
        print("Error: image is None")
        return None

    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    window_name = title
    cv2.namedWindow(window_name)

    rect_start = None
    rect_end = None
    dragging = False
    selection_complete = False
    img_copy = rgb_img.copy()

    def mouse_callback(event, x, y, flags, param):
        nonlocal rect_start, rect_end, dragging, img_copy, selection_complete

        if event == cv2.EVENT_LBUTTONDOWN:
            rect_start = (x, y)
            rect_end = (x, y)
            dragging = True
            img_copy = rgb_img.copy()
            selection_complete = False
        elif event == cv2.EVENT_MOUSEMOVE and dragging:
            rect_end = (x, y)
            temp_img = rgb_img.copy()
            cv2.rectangle(temp_img, rect_start, rect_end, (0, 255, 0), 2)
            img_copy = temp_img
        elif event == cv2.EVENT_LBUTTONUP:
            rect_end = (x, y)
            dragging = False
            cv2.rectangle(img_copy, rect_start, rect_end, (0, 255, 0), 2)
            selection_complete = True

    cv2.setMouseCallback(window_name, mouse_callback)

    print("Drag a box on the color area, then press 'c'. Reset with 'r', quit with 'q'.")
    while True:
        cv2.imshow(window_name, cv2.cvtColor(img_copy, cv2.COLOR_RGB2BGR))
        key = cv2.waitKey(1) & 0xFF

        if key == ord("c") and selection_complete:
            break
        if key == ord("r"):
            rect_start = None
            rect_end = None
            img_copy = rgb_img.copy()
            selection_complete = False
        if key == ord("q"):
            cv2.destroyAllWindows()
            return None

    cv2.destroyAllWindows()

    if rect_start is None or rect_end is None:
        return None

    x1, y1 = min(rect_start[0], rect_end[0]), min(rect_start[1], rect_end[1])
    x2, y2 = max(rect_start[0], rect_end[0]), max(rect_start[1], rect_end[1])
    if x2 <= x1 or y2 <= y1:
        return None

    region = rgb_img[y1:y2, x1:x2]
    if region.size == 0:
        return None

    hsv_region = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
    h_vals = hsv_region[:, :, 0].astype(np.float32)
    angles = np.deg2rad(h_vals * 2.0)
    mean_x = np.mean(np.cos(angles))
    mean_y = np.mean(np.sin(angles))
    mean_angle = np.arctan2(mean_y, mean_x)
    if mean_angle < 0:
        mean_angle += 2 * np.pi
    h_avg = int(np.round(np.rad2deg(mean_angle) / 2.0)) % 180
    s_avg = int(np.mean(hsv_region[:, :, 1]))
    v_avg = int(np.mean(hsv_region[:, :, 2]))

    print(f"Average HSV: ({h_avg}, {s_avg}, {v_avg})")
    return h_avg, s_avg, v_avg


def generate_hsv_range(
    center: tuple[int, int, int], offset: tuple[int, int, int]
) -> list[dict[str, list[int]]]:
    h, s, v = center
    h_off, s_off, v_off = offset

    lower = [h - h_off, max(s - s_off, 0), max(v - v_off, 0)]
    upper = [h + h_off, min(s + s_off, 255), min(v + v_off, 255)]

    ranges: list[tuple[list[int], list[int]]] = []
    if lower[0] < 0:
        ranges.append(([0, lower[1], lower[2]], [upper[0], upper[1], upper[2]]))
        ranges.append(([180 + lower[0], lower[1], lower[2]], [179, upper[1], upper[2]]))
    elif upper[0] > 179:
        ranges.append(([0, lower[1], lower[2]], [upper[0] - 180, upper[1], upper[2]]))
        ranges.append(([lower[0], lower[1], lower[2]], [179, upper[1], upper[2]]))
    else:
        ranges.append((lower, upper))

    return [{"lower": low, "upper": high} for low, high in ranges]


def main() -> int:
    args = parse_args()

    image_path = args.image
    if args.import_image:
        image_path = choose_image_file()
        if image_path is None:
            print("No image selected.")
            return 1

    if image_path:
        image = cv2.imread(str(image_path))
        if image is None:
            raise SystemExit(f"Could not read image: {image_path}")
        print(f"Loaded image: {image_path}")
    else:
        image = capture_image(args.width, args.height, args.camera_index)
        cv2.imwrite(str(args.captured_image), image)
        print(f"Captured image saved to: {args.captured_image}")

    hsv_center = select_color_region_hsv_average(image, title=f"Select {args.label}")
    if hsv_center is None:
        print("Selection cancelled.")
        return 1

    hsv_ranges = generate_hsv_range(
        hsv_center, (args.h_offset, args.s_offset, args.v_offset)
    )

    result = {
        "label": args.label.upper(),
        "center_hsv": list(hsv_center),
        "offset": [args.h_offset, args.s_offset, args.v_offset],
        "ranges": hsv_ranges,
    }
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    print(f"Saved to: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
