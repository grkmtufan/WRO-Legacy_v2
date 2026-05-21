# Raspberry Pi Grid Color Detector

This project contains a first-pass detector for a WRO board captured with a Raspberry Pi camera.

Current scope:
- Capture one frame from the Raspberry Pi camera
- Automatically find the board in the image
- Split the board into a `4 x 3` grid
- Detect each cell as `YELLOW`, `GREEN`, `BLUE`, or `WHITE`
- Compute the best row placement plan and travel direction
- Save the result as JSON and an annotated image

## Raspberry Pi setup

Enable the camera first:

```bash
sudo raspi-config
```

Then install the needed packages:

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv
pip install -r requirements.txt
```

## Run

```bash
python3 color_grid_detector.py
```

This now tries to find the board automatically anywhere in the photo.

Live preview:

```bash
python3 color_grid_detector.py --preview
```

Optional ROI if the board does not fill the whole image:

```bash
python3 color_grid_detector.py --roi 160 120 960 720
```

Disable auto-detect and use the full image directly:

```bash
python3 color_grid_detector.py --no-auto-detect
```

Outputs:
- `last_detection.json`
- `last_detection.jpg`

## Notes

- The HSV thresholds are a solid starting point, but you will likely tune them under your real competition lighting.
- `--margin 0.18` ignores cell borders so grid lines and shadows affect detection less.
- By default the script tries to detect the board automatically and marks it in the saved image.
- `--preview` opens a live window and updates the detected 4x3 grid continuously. Press `Q` to quit.
- The JSON output now includes a `plan` field with the recommended pick sequence, row assignments, direction, and expected score.
