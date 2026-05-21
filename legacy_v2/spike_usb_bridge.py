"""
SPIKE Prime USB bridge helpers.

Paste the functions you need into your SPIKE robot code.
Flow:
1. SPIKE starts with its own button.
2. When analysis is needed, call `get_plan_from_pi()`.
3. Use `pick_sequence` in `ColorMove(...)`.
4. Use `direction` later in your own placement function.
"""

import hub
import utime


START_MARKER = "<<<"
END_MARKER = ">>>"
REQUEST_GET_PLAN = "GET_PLAN"


def open_usb_connection():
    connection = hub.USB_VCP()
    connection.init(flow=hub.USB_VCP.CTS | hub.USB_VCP.RTS)
    connection.setinterrupt(-1)
    return connection


def send_usb_message(connection, payload):
    message = START_MARKER + payload + END_MARKER
    connection.write(message.encode())


def read_usb_message(connection, timeout_ms=15000):
    start_time = utime.ticks_ms()
    buffer = ""

    while utime.ticks_diff(utime.ticks_ms(), start_time) < timeout_ms:
        if connection.any():
            data = connection.read()
            if data:
                try:
                    buffer += data.decode()
                except Exception:
                    continue

                start = buffer.find(START_MARKER)
                end = buffer.find(END_MARKER, start + len(START_MARKER))
                if start != -1 and end != -1:
                    return buffer[start + len(START_MARKER):end]

        utime.sleep_ms(10)

    return None


def parse_plan_response(payload):
    if payload is None:
        return None, []

    parts = payload.split("|")
    if len(parts) < 3:
        return None, []

    if parts[0] != "PLAN":
        return None, []

    direction = parts[1].upper()
    pick_sequence = [item.strip().upper() for item in parts[2].split(",") if item.strip()]
    return direction, pick_sequence


def get_plan_from_pi(timeout_ms=15000):
    connection = open_usb_connection()
    send_usb_message(connection, REQUEST_GET_PLAN)
    payload = read_usb_message(connection, timeout_ms=timeout_ms)
    direction, pick_sequence = parse_plan_response(payload)
    return direction, pick_sequence


def example_usage():
    direction, pick_sequence = get_plan_from_pi()
    print(direction)
    print(pick_sequence)
