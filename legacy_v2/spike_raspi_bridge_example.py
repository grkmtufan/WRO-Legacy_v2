"""
SPIKE-side example for getting the planned color sequence from Raspberry Pi.

Before using this in the SPIKE app:
1. Paste the SpiBerryEngine `raspi-util-class.py` contents above this code.
2. Paste your movement helper functions above this code.
3. Then fill the `# yapilacak is` sections with your real robot actions.
"""


def parse_color_sequence(raw_value):
    if raw_value is None:
        return []

    if isinstance(raw_value, list):
        return raw_value

    text = str(raw_value).strip()
    if text == "":
        return []

    return [item.strip().upper() for item in text.split(",") if item.strip()]


def ColorMove(color_sequence):
    for i in range(len(color_sequence)):
        color = color_sequence[i]

        if i < len(color_sequence) - 1:
            next_color = color_sequence[i + 1]
        else:
            next_color = None

        if i == 0:
            if color == "YELLOW":
                # yapilacak is
                if next_color == "YELLOW":
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

            elif color == "GREEN":
                # yapilacak is
                if next_color == "GREEN":
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

            elif color == "BLUE":
                # yapilacak is
                if next_color == "BLUE":
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

            elif color == "WHITE":
                # yapilacak is
                if next_color == "WHITE":
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

        elif i == 1:
            if color == "YELLOW":
                # yapilacak is
                if next_color == "YELLOW":
                    # yapilacak is
                    pass
                elif next_color is not None:
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

            elif color == "GREEN":
                # yapilacak is
                if next_color == "GREEN":
                    # yapilacak is
                    pass
                elif next_color is not None:
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

            elif color == "BLUE":
                # yapilacak is
                if next_color == "BLUE":
                    # yapilacak is
                    pass
                elif next_color is not None:
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

            elif color == "WHITE":
                # yapilacak is
                if next_color == "WHITE":
                    # yapilacak is
                    pass
                elif next_color is not None:
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

        elif i == 2:
            if color == "YELLOW":
                # yapilacak is
                if next_color == "YELLOW":
                    # yapilacak is
                    pass
                elif next_color is not None:
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

            elif color == "GREEN":
                # yapilacak is
                if next_color == "GREEN":
                    # yapilacak is
                    pass
                elif next_color is not None:
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

            elif color == "BLUE":
                # yapilacak is
                if next_color == "BLUE":
                    # yapilacak is
                    pass
                elif next_color is not None:
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

            elif color == "WHITE":
                # yapilacak is
                if next_color == "WHITE":
                    # yapilacak is
                    pass
                elif next_color is not None:
                    # yapilacak is
                    pass
                else:
                    # yapilacak is
                    pass

        elif i == 3:
            if color == "YELLOW":
                # yapilacak is
                pass
            elif color == "GREEN":
                # yapilacak is
                pass
            elif color == "BLUE":
                # yapilacak is
                pass
            elif color == "WHITE":
                # yapilacak is
                pass


async def main():
    raspi = Raspi()
    raw_sequence = raspi.get_color_sequence_csv()
    color_sequence = parse_color_sequence(raw_sequence)
    print("PI COLOR SEQUENCE:", color_sequence)
    ColorMove(color_sequence)
