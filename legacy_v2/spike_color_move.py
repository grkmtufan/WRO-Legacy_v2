#!/usr/bin/env python3
"""
Simple SPIKE-side skeleton for the new 2-2-2 pair collection flow.

Rules:
- Each side is collected as three same-color pairs.
- Pick order is top -> bottom -> middle.
- After collecting all 6 cubes for one side, that side is placed at once.
- Then the same flow repeats for the other side.
"""

from __future__ import annotations


def CollectPairsForSide(side_name: str, pick_sequence: list[str]) -> None:
    """
    pick_sequence example:
    ["YELLOW", "BLUE", "GREEN"]

    Order:
    1. top pair
    2. bottom pair
    3. middle pair
    """

    for step_index, color_name in enumerate(pick_sequence, start=1):
        if step_index == 1:
            if color_name == "YELLOW":
                # top pair - yellow
                # yapilacak is
                pass
            elif color_name == "GREEN":
                # top pair - green
                # yapilacak is
                pass
            elif color_name == "BLUE":
                # top pair - blue
                # yapilacak is
                pass
            elif color_name == "WHITE":
                # top pair - white
                # yapilacak is
                pass

        elif step_index == 2:
            if color_name == "YELLOW":
                # bottom pair - yellow
                # yapilacak is
                pass
            elif color_name == "GREEN":
                # bottom pair - green
                # yapilacak is
                pass
            elif color_name == "BLUE":
                # bottom pair - blue
                # yapilacak is
                pass
            elif color_name == "WHITE":
                # bottom pair - white
                # yapilacak is
                pass

        elif step_index == 3:
            if color_name == "YELLOW":
                # middle pair - yellow
                # yapilacak is
                pass
            elif color_name == "GREEN":
                # middle pair - green
                # yapilacak is
                pass
            elif color_name == "BLUE":
                # middle pair - blue
                # yapilacak is
                pass
            elif color_name == "WHITE":
                # middle pair - white
                # yapilacak is
                pass


def PlaceSixForSide(side_name: str) -> None:
    if side_name == "FRONT":
        # front side 6 cubes are placed at once
        # yapilacak is
        pass

    elif side_name == "BACK":
        # back side 6 cubes are placed at once
        # yapilacak is
        pass


def RunFullPlan(front_pick_sequence: list[str], back_pick_sequence: list[str]) -> None:
    CollectPairsForSide("FRONT", front_pick_sequence)
    PlaceSixForSide("FRONT")

    CollectPairsForSide("BACK", back_pick_sequence)
    PlaceSixForSide("BACK")


if __name__ == "__main__":
    sample_front = ["YELLOW", "BLUE", "GREEN"]
    sample_back = ["WHITE", "BLUE", "WHITE"]
    RunFullPlan(sample_front, sample_back)
