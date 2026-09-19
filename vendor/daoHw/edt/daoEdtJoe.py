#!/usr/bin/env python3
"""
daoEdtJoe.py

Send ASCII commands to a SciMeasure Little Joe camera
through EDT serial_cmd and print the decoded reply.

• Automatically appends CR (\r)
• Removes leading ACK (0x06)
• Strips trailing CR/LF
"""

import argparse
import subprocess
import re
import sys

EDT_PATH = "/opt/EDTpdv/serial_cmd"


# ------------------------------------------------------------
# Convert ASCII command to hex string (with CR)
# ------------------------------------------------------------
def ascii_to_hex(cmd: str) -> str:
    return " ".join(f"{b:02x}" for b in (cmd + "\r").encode("ascii", "strict"))


# ------------------------------------------------------------
# Extract and decode ASCII response from serial_cmd output
# ------------------------------------------------------------
def extract_ascii_reply(text: str):
    payloads = re.findall(r"resp\s*<([^>]*)>", text, flags=re.IGNORECASE)
    if not payloads:
        return None

    all_bytes = []
    for p in payloads:
        toks = re.findall(r"\b[0-9a-fA-F]{2}\b", p)
        all_bytes.extend(int(t, 16) for t in toks)

    if not all_bytes:
        return None

    # Remove leading ACK (0x06)
    if all_bytes[0] == 0x06:
        all_bytes = all_bytes[1:]

    # Strip trailing CR/LF
    while all_bytes and all_bytes[-1] in (0x0D, 0x0A):
        all_bytes.pop()

    try:
        return bytes(all_bytes).decode("ascii", errors="ignore")
    except Exception:
        return None


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        prog="daoEdtJoe.py",
        description=(
            "Send ASCII commands to a SciMeasure Little Joe camera "
            "through EDT serial_cmd and print decoded reply."
        ),
        epilog=(
            "Examples:\n"
            "  daoEdtJoe.py \"@JOE?\"\n"
            "  daoEdtJoe.py -u 1 -c 0 \"@PRG 0\"\n"
            "  daoEdtJoe.py -u 0 -c 0 -b 38400 \"@SEQ 1\"\n"
            "\n"
            "Notes:\n"
            "  • Automatically appends CR (\\r)\n"
            "  • Removes leading ACK (0x06)\n"
            "  • Strips trailing CR/LF\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    ap.add_argument(
        "-u",
        type=int,
        default=0,
        metavar="UNIT",
        help="EDT board/unit number (default: 0)",
    )

    ap.add_argument(
        "-c",
        type=int,
        default=0,
        metavar="CHAN",
        help="EDT channel number (default: 0)",
    )

    ap.add_argument(
        "-b",
        type=int,
        default=38400,
        metavar="BAUD",
        help="Serial baud rate (default: 38400)",
    )

    ap.add_argument(
        "-t",
        type=int,
        default=100,
        metavar="TIMEOUT",
        help="serial_cmd timeout override in ms (default: 100)",
    )

    ap.add_argument(
        "command",
        metavar="\"@CMD ...\"",
        help="ASCII command to send (e.g. \"@JOE?\", \"@SEQ 1\")",
    )

    args = ap.parse_args()

    tx_hex = ascii_to_hex(args.command)

    cmd = [
        EDT_PATH,
        "-u", str(args.u),
        "-c", str(args.c),
        "-x",
        "-b", str(args.b),
        "-t", str(args.t),
        tx_hex,
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    reply = extract_ascii_reply(result.stdout)

    if reply:
        print(reply)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
