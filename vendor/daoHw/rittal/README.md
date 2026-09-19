# rittal — Rittal CMC III PDU

`rittal_pdu_controller.py` — switch and monitor outlets on a **Rittal CMC III**
power distribution unit over **SNMP**.

Outlets can be addressed by PDU socket index or by their configured name.

```bash
rittal_pdu_controller.py status
rittal_pdu_controller.py status 3
rittal_pdu_controller.py status "NGS LAMP1"
rittal_pdu_controller.py on  "NGS LAMP1"
rittal_pdu_controller.py off 3
```

Device map (dev 2 = Master PDU, dev 4 = Slave PDU; idx 1-5 are power sensors,
idx ≥ 6 are switchable outlets) and the exact OIDs are documented in the file
header.

## Dependency

`pip install pysnmp` (v7). SNMP read/write access enabled on the PDU.

## Build / install

Pure Python. `../wscript` installs `rittal/*.py` to both `$DAOROOT/bin` and
`$DAOROOT/python`.
