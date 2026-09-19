# ekarelab

Offline DataElab readers and analysis tools for Ekarus telemetry products.

## Install

```bash
pip install -e .
```

`ekarelab` uses the telemetry-key definitions installed by `daoEkarus`. Make
sure `daoEkarus/src/python` is available on `PYTHONPATH`:

```bash
export PYTHONPATH="/path/to/daoEkarus/src/python${PYTHONPATH:+:$PYTHONPATH}"
```

## Use

```python
import ekarelab

factory = ekarelab.get_factory('lorenzo')
analyzer = factory.analyzer('20260901_002125')
```

## Analyzer Data

`EkarusAnalyzer` groups telemetry by subsystem. DataElab data objects expose
their arrays through `get_data()`; temporal reductions preserve a single time
axis, so use `.value` when an array without singleton dimensions is needed.

```python
# Deformable mirror
commands = analyzer.dm.commands.get_data()
offset = analyzer.dm.offset.get_data()
timestamps = analyzer.dm.timestamps.get_data()

# Main AO loop
residual_modes_nm = analyzer.loop.residual_modes.get_data()
modal_std_nm = analyzer.loop.residual_modes.time_std.value
pseudo_open_loop_modes_nm = analyzer.loop.pseudo_open_loop_modes.get_data()
m2c = analyzer.loop.m2c.get_data()
c2m = analyzer.loop.c2m.get_data()
integrated_modes = analyzer.loop.integrated_modes.get_data()
valid_if_pixels = analyzer.dm.influence_functions.valid_pixels()
influence_functions_matrix = analyzer.dm.influence_functions.matrix()

# Residual versus pseudo-open-loop modal standard deviations
analyzer.modalplot()

# WFS intensity signals
wfs_signals = analyzer.wfs_signals.get_data()

# Fast tip-tilt loop
fast_tt_commands = analyzer.fast_tt.commands.get_data()
fast_tt_gain = analyzer.fast_tt.loop_gain

# OCAM
mean_ocam_frame = analyzer.ocam.mean_frame.get_data()
ocam_frame_rate = analyzer.ocam.fps

# Modulator
modulator_enabled = analyzer.modulator.enabled

# Telescope
telescope_offset = analyzer.telescope.offset.get_data()
telescope_guiding = analyzer.telescope.guiding.get_data()
telescope_ra_dec = analyzer.telescope.ra_dec.get_data()

# CBLUE
long_exposure = analyzer.cblue.long_exposure
cblue_background = analyzer.cblue.background.get_data()
cblue_frame_rate = analyzer.cblue.fps

# ORCA
orca_long_exposure = analyzer.orca.long_exposure
orca_background = analyzer.orca.background.get_data()
orca_frame_rate = analyzer.orca.fps
```

`analyzer.loop.residual_modes` is converted from controller volts to wavefront
nanometers using the DM468 influence functions in
`data_root/inputs/dm468/IF_zonal_cube.npy` and the loop M2C matrix.

## Data Roots

Use the factory appropriate to the machine hosting the analysis:

```python
ekarelab.get_factory('daortc')  # /home/daouser/DAODATA on the DAO RTC
ekarelab.get_factory('lorenzo')  # locally copied Google Drive data
ekarelab.Factory(data_root_dir='/Volumes/telemetry-data')  # any mounted or copied data
```

## Remote DAO RTC Data with SSHFS

To analyse telemetry without manually copying it from the DAO real-time
computer, mount its data directory with SSHFS. The mount is handled by the
operating system, so `ekarelab` reads it just like a local directory.

On macOS, install macFUSE and SSHFS with Homebrew:

```bash
brew install --cask macfuse
brew install gromgit/fuse/sshfs-mac
```

Create a local mount point and mount the DAO RTC data directory:

```bash
mkdir -p ~/daortc-data
sshfs daouser@daortc:/home/daouser/DAODATA ~/daortc-data
```

The first connection may ask for the SSH password of `daouser`. For repeated
use, configure an SSH key on the client and add its public key to
`~daouser/.ssh/authorized_keys` on the DAO RTC. Do not store SSH passwords in
Python code or configuration files.

Pass the mount point to the generic factory:

```python
import ekarelab

factory = ekarelab.Factory(data_root_dir='~/daortc-data')
analyzer = factory.analyzer('20260901_002125')
```

Expand the path before constructing the factory when using `~`:

```python
from pathlib import Path

factory = ekarelab.Factory(data_root_dir=Path('~/daortc-data').expanduser())
```

Unmount the filesystem when the analysis is complete:

```bash
umount ~/daortc-data
```

On systems where `umount` is unavailable, use the platform-specific FUSE
unmount command documented by the installed SSHFS package.