# nuvu — Nüvü Camēras (EMCCD)

Control + acquisition for **Nüvü** HNü 512 EMCCD cameras via `nc_driver`.

| file | mode |
|------|------|
| `daoNuvu512SingleCtrl.c` | single full-frame stream |
| `daoNuvu512MultiCtrl.c`  | up to 3 independent ROIs |
| `daoNuvu512Ctrl.c`       | shared core |

Control SHMs (`<img>` = image SHM name): `…Dit`, `…Fps`, `…Gain` (analog),
`…EmGain` (EM gain), `…TargetTemp`, `…CurrentTemp`, `…NbRoi`, plus `<roiN>Pos`
`uint32[2]` per ROI and an external-trigger SHM. ROI *sizes* come from the ROI
image SHM shapes; ROI *positions* from the `Pos` SHMs.

```
daoNuvu512MultiCtrl -S imgName nbRoiName roi0Img roi1Img roi2Img extTrigName -L
```

## Dependency

Nüvü **SDK** (`nc_driver` / `libnuvu`), installed at `/opt/NuvuCameras` (headers
`nc_driver.h`). From Nüvü Camēras.

## Build

`../wscript` `configure` auto-detects the SDK (`--nuvu=/path` to override); if
not found, this folder is skipped (`HAVE_NUVU`).
