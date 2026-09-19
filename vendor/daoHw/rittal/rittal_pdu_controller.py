#!/usr/bin/env python3
"""
Rittal CMC III PDU Control — SNMP-based (pysnmp v7)

OID layout (verified from live snmpwalk):
  1.3.6.1.4.1.2606.7.4.3.2.1.3.<dev>.<idx>  →  outlet name  (STRING)
  1.3.6.1.4.1.2606.7.4.3.2.1.4.<dev>.<idx>  →  outlet state (INTEGER: 10=OFF 11=ON)

Device map (from your PDU):
  dev 1 — CMC III unit (system sensors, Input, Login — skip entirely)
  dev 2 — Master PDU   (idx 1-5: power sensors; idx 6+ = switchable outlets)
  dev 3 — CMC III unit (same as dev 1 — skip entirely)
  dev 4 — Slave PDU    (idx 1-5: power sensors; idx 6+ = switchable outlets)

Install:  pip install pysnmp

Usage:
    python rittal_pdu.py status
    python rittal_pdu.py status 3          # by PDU socket index
    python rittal_pdu.py status "NGS LAMP1"
    python rittal_pdu.py on 3
    python rittal_pdu.py off "NGS LAMP1"
"""

import sys
import asyncio
import argparse
import warnings
warnings.filterwarnings("ignore")

from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity,
    set_cmd, walk_cmd,
    Integer32,
)

# ── Configuration ─────────────────────────────────────────────────────────────

PDU_HOST       = "192.168.5.94"
SNMP_COMMUNITY = "public"
SNMP_WRITE_COM = "pdu"
SNMP_PORT      = 161
SNMP_TIMEOUT   = 2
SNMP_RETRIES   = 3

OID_NAME_BASE   = "1.3.6.1.4.1.2606.7.4.3.2.1.3"
OID_STATUS_BASE = "1.3.6.1.4.1.2606.7.4.3.2.1.4"
# cmcIIIdevDetValue (column 11) — the actual R/W value column for outlet relay control
# Write 1=ON, 0=OFF.  var_idx = 63 + 9*(socket_idx - OUTLET_IDX_MIN)
OID_CMD_BASE    = "1.3.6.1.4.1.2606.7.4.2.2.1.11"

# Device indices that are actual PDUs (not CMC system units)
PDU_DEVS    = {2, 4}
MASTER_DEVS = {2}
# Within each PDU device, indices 1-5 are power/current sensors — skip them
OUTLET_IDX_MIN = 6

RELAY_ON  = 11
RELAY_OFF = 10
STATUS_MAP = {10: "OFF", 11: "ON"}
# Values to write to OID_CMD_BASE for relay control
RELAY_CMD_ON  = 1
RELAY_CMD_OFF = 0


# ── SNMP helpers ──────────────────────────────────────────────────────────────

def _community(write=False):
    return CommunityData(SNMP_WRITE_COM if write else SNMP_COMMUNITY, mpModel=1)

async def _transport():
    return await UdpTransportTarget.create(
        (PDU_HOST, SNMP_PORT), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES
    )

async def snmp_walk(base_oid: str) -> dict[str, object]:
    engine    = SnmpEngine()
    community = _community()
    transport = await _transport()
    results   = {}
    async for errInd, errStat, _, varBinds in walk_cmd(
        engine, community, transport, ContextData(),
        ObjectType(ObjectIdentity(base_oid)),
        lexicographicMode=False,
    ):
        if errInd:
            print(f"SNMP walk error: {errInd}"); break
        if errStat:
            print(f"SNMP walk error: {errStat.prettyPrint()}"); break
        for oid, val in varBinds:
            results[str(oid)] = val
    return results

async def snmp_set(oid: str, value: int) -> bool:
    engine    = SnmpEngine()
    community = _community(write=True)
    transport = await _transport()
    errInd, errStat, errIdx, varBinds = await set_cmd(
        engine, community, transport, ContextData(),
        ObjectType(ObjectIdentity(oid), Integer32(value)),
    )
    if errInd:
        print(f"SNMP set error: {errInd}"); return False
    if errStat:
        idx = int(errIdx) - 1 if errIdx else 0
        print(f"SNMP set error: {errStat.prettyPrint()} at {varBinds[idx][0]}")
        return False
    return True


# ── Outlet discovery ──────────────────────────────────────────────────────────

async def get_all_outlets() -> list[dict]:
    """
    Walk name + status trees, join on suffix, filter to real switchable outlets.

    Filters applied:
      1. dev must be in PDU_DEVS (skip CMC system units on dev 1, 3)
      2. idx must be >= OUTLET_IDX_MIN (skip per-phase power sensors at idx 1-5)
      3. status must be 10 or 11 (skip any remaining non-relay rows)
    """
    names    = await snmp_walk(OID_NAME_BASE)
    statuses = await snmp_walk(OID_STATUS_BASE)

    status_by_suffix: dict[str, int] = {}
    for oid, val in statuses.items():
        suffix = oid[len(OID_STATUS_BASE):]
        try:
            status_by_suffix[suffix] = int(val)
        except (ValueError, TypeError):
            pass

    outlets = []

    for oid in sorted(names):
        suffix = oid[len(OID_NAME_BASE):]       # e.g. ".2.8"
        parts  = suffix.strip(".").split(".")
        if len(parts) < 2:
            continue

        dev_idx    = int(parts[0])
        socket_idx = int(parts[1])              # real PDU socket number

        # Filter 1: only actual PDU devices
        if dev_idx not in PDU_DEVS:
            continue

        # Filter 2: skip power-sensor rows (idx 1-5)
        if socket_idx < OUTLET_IDX_MIN:
            continue

        # Filter 3: must be a relay (10=OFF or 11=ON)
        status_int = status_by_suffix.get(suffix)
        if status_int not in (RELAY_ON, RELAY_OFF):
            continue

        name     = str(names[oid]).strip()
        unit_lbl = "Master" if dev_idx in MASTER_DEVS else "Slave"

        # Socket number displayed to user: offset so idx 6 → socket 1
        display_socket = socket_idx - (OUTLET_IDX_MIN - 1)

        # Writable OID: cmcIIIdevDetValue column, var index = 63 + 9*(socket_idx - OUTLET_IDX_MIN)
        cmd_var_idx = 63 + 9 * (socket_idx - OUTLET_IDX_MIN)
        oid_set = f"{OID_CMD_BASE}.{dev_idx}.{cmd_var_idx}"

        outlets.append({
            "socket":  display_socket,
            "dev":     dev_idx,
            "name":    name,
            "unit":    unit_lbl,
            "status":  STATUS_MAP[status_int],
            "oid_set": oid_set,
        })

    # Sort: Master before Slave, then by socket number within each unit
    outlets.sort(key=lambda o: (0 if o["unit"] == "Master" else 1, o["socket"]))
    return outlets


# ── Display ───────────────────────────────────────────────────────────────────

def print_table(outlets: list[dict]):
    if not outlets:
        print("No relay outlets found.")
        print(f"  Diagnose: snmpwalk -v2c -c {SNMP_COMMUNITY} {PDU_HOST} {OID_NAME_BASE}")
        return
    print(f"\n{'Socket':<8} {'Description':<28} {'Unit':<8} Status")
    print("─" * 56)
    for o in outlets:
        sym = "✔  ON " if o["status"] == "ON" else "✘  OFF"
        print(f"{o['socket']:<8} {o['name']:<28} {o['unit']:<8} {sym}")
    print()

def find_outlets(outlets: list[dict], query: str) -> list[dict]:
    """Match by socket number (within a unit) or name substring."""
    try:
        n = int(query)
        m = [o for o in outlets if o["socket"] == n]
        if m:
            return m
    except ValueError:
        pass
    return [o for o in outlets if query.lower() in o["name"].lower()]


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_status(target=None, unit=None):
    outlets = await get_all_outlets()
    if unit:
        outlets = [o for o in outlets if o["unit"].lower() == unit.lower()]
    if target:
        outlets = find_outlets(outlets, target)
        if not outlets:
            label = f"{unit} socket {target!r}" if unit else f"{target!r}"
            print(f"No outlet found matching: {label}"); sys.exit(1)
    print_table(outlets)

async def cmd_switch(action: str, target: str, unit=None):
    outlets = await get_all_outlets()
    if unit:
        outlets = [o for o in outlets if o["unit"].lower() == unit.lower()]
    matches = find_outlets(outlets, target)
    if not matches:
        label = f"{unit} socket {target!r}" if unit else f"{target!r}"
        print(f"No outlet found matching: {label}"); sys.exit(1)
    value = RELAY_CMD_ON if action == "on" else RELAY_CMD_OFF
    for o in matches:
        label = f"socket {o['socket']} [{o['name']}] ({o['unit']})"
        print(f"→ {action.upper()} {label} …", end=" ", flush=True)
        ok = await snmp_set(o["oid_set"], value)
        print("done ✔" if ok else "FAILED — check write community string")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Rittal CMC III PDU control via SNMP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rittal_pdu_controller.py status
  python rittal_pdu_controller.py status master
  python rittal_pdu_controller.py status slave
  python rittal_pdu_controller.py status master 3
  python rittal_pdu_controller.py status slave 3
  python rittal_pdu_controller.py status "NGS LAMP1"
  python rittal_pdu_controller.py on master 3
  python rittal_pdu_controller.py on slave 3
  python rittal_pdu_controller.py on 3
  python rittal_pdu_controller.py off master "NGS LAMP1"
  python rittal_pdu_controller.py off "NGS LAMP1"
        """,
    )
    parser.add_argument("action", choices=["status", "on", "off"])
    parser.add_argument("unit", nargs="?", default=None,
                        help="Unit filter: master or slave (status only)")
    parser.add_argument("target", nargs="?", default=None,
                        help="Socket number or name substring")
    args = parser.parse_args()

    # Allow omitting unit for on/off or bare status (e.g. "status 3" or "on 3")
    # If unit is not 'master'/'slave', treat it as the target instead
    unit = None
    target = args.target
    if args.unit and args.unit.lower() not in ("master", "slave"):
        # user did: status 3  or  on 3  (no unit given)
        target = args.unit
    elif args.unit:
        unit = args.unit

    if args.action in ("on", "off") and not target:
        parser.error("on/off requires a target (socket number or name).")

    if args.action == "status":
        asyncio.run(cmd_status(target, unit))
    else:
        asyncio.run(cmd_switch(args.action, target, unit))

if __name__ == "__main__":
    main()