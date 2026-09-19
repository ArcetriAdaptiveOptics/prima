#!/usr/bin/env python3
#
import argparse
import os
import sys
from datetime import datetime

import numpy as np
from astropy.io import fits

import dao
import daoEkarusShmNames as shm_names
from ekalib import calibration


def parse_args(argv=None):
    """Parse the command line.

    Positional arguments are kept so existing callers keep working:
        computeInteractionMatrix.py <nModes> <basis>

    The acquisition parameters coming from the Calibration Parameters panel
    are optional named flags. When omitted, the historical defaults are used.
    """
    p = argparse.ArgumentParser(
        description="Acquire a push-pull interaction matrix."
    )
    p.add_argument("nModes", type=int, help="number of modes to calibrate")
    p.add_argument("basis", type=str, help="M2C / basis label")

    p.add_argument(
        "--amplitude",
        type=float,
        default=None,
        help="peak-to-valley modal amplitude [a.u.]. "
             "Default: derived from the modulation radius.",
    )
    p.add_argument(
        "--nFrameAverage",
        type=int,
        default=25,
        help="number of WFS frames averaged per push and per pull",
    )
    p.add_argument(
        "--nRepetition",
        type=int,
        default=5,
        help="number of repetitions of the full modal sequence",
    )
    p.add_argument(
        "--modalScaling",
        type=int,
        default=0,
        help="1 to scale the amplitude with the mode index, 0 for a flat amplitude",
    )
    return p.parse_args(argv)


def modal_amplitude(max_amp, n_modes, enabled):
    """Return the per-mode amplitude to apply.

    Flat vector when scaling is disabled. When enabled, the amplitude grows
    towards the high orders as 1/sqrt of the mode index so the higher, less
    sensitive modes still produce a measurable WFS signal.

    Adjust the law here if the bench calls for a different weighting -- this
    is the only place it is defined.
    """

    modes = np.arange(n_modes, dtype=np.float32)
    radial_order = (np.ceil(-3.0/2.0+np.sqrt(1+8*(modes+2))/2.0)).astype(int)

    if not enabled:
        return np.full(n_modes, max_amp, dtype=np.float32)
    return (max_amp / np.sqrt(radial_order)).astype(np.float32)


if __name__ == "__main__":

    args = parse_args()

    nModes = args.nModes
    basis = args.basis

    m2c = dao.shm(shm_names.SHM_DM1_M2C).get_data()
    ocam = dao.shm(shm_names.SHM_OCAM_REDUCED_FRAME)
    dmCmd = dao.shm(shm_names.SHM_DM1_CHANNEL_2)
    bgp = dao.shm(shm_names.SHM_OCAM_DARK_MAP_PERCENT).set_data(dao.shm(shm_names.SHM_OCAM_DARK_MAP_PERCENT).get_data()*0)
    mod_radius = dao.shm(shm_names.SHM_MODULATOR).get_data()[1, 0]

    frames2avg = args.nFrameAverage
    n_rep = args.nRepetition
    modal_scaling = bool(args.modalScaling)

    # Amplitude: use the GUI value when given, otherwise fall back to the
    # modulation-dependent law.
    if args.amplitude is not None:
        max_amp = args.amplitude
    else:
        max_amp = (0.009 * mod_radius + 0.007) / 4.0

    if max_amp <= 0:
        sys.exit("amplitude must be strictly positive")

    # if the modal scaling box is checked, apply a given scaling for the modes based on the radial order
    amp = modal_amplitude(max_amp, nModes, modal_scaling)
    print(f"nModes       : {nModes}")
    print(f"basis        : {basis}")
    print(f"amplitude    : {max_amp:.4f}  (modal scaling: {modal_scaling})")
    print(f"nFrameAverage: {frames2avg}")
    print(f"nRepetition  : {n_rep}")

    imat = calibration(
        m2c[:, :nModes],
        dmCmd,
        ocam,
        frames2avg=frames2avg,
        amp=amp,
        n_rep=n_rep,
        progressBar=True,
    )

    im_folder = os.getenv("DAODATA") + (
        f"/inputs/calibration/interactionMatrix/{basis}/")
    if modal_scaling:
        extra = 'modal_scaling'
    else:
        extra = ''
    im_name = f"IM_rMod_{mod_radius:.1f}_nModes{nModes:.0f}_maxAmp{max_amp:.3f}_{extra}.npy"
    im_path = os.path.join(im_folder,im_name)
    
    if not os.path.isdir(im_folder):
        # If the folder does not exist, create it
        os.makedirs(im_folder)
    
    np.save(im_path, imat.astype(np.float32))

    # write a temporary file to keep track of the M2C path
    with open(os.getenv("DAODATA") + "/inputs/calibration/interactionMatrix/current_imat.txt","w",) as f:
        f.write(im_path)
        f.close()

    # Get the current timestamp
    timestamp = datetime.now()
    timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")

    hdr = fits.Header()
    hdr["BASIS"] = basis
    hdr["R_MOD"] = mod_radius
    hdr["NMODES"] = nModes
    hdr["PP_AMP"] = max_amp
    hdr["REPEATS"] = n_rep
    hdr["AVGFRAME"] = frames2avg
    hdr["MODSCALE"] = modal_scaling

    fits.writeto(
        os.getenv("DAODATA") + f"/calibration/IntMat_{timestamp_str}.fits",
        imat.astype(np.float32),
        header=hdr,
        overwrite=True,
    )