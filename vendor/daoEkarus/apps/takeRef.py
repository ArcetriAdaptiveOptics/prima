#!/usr/bin/env python3
#
# import argparse
import sys
import numpy as np
import dao
import daoEkarusShmNames as shm_names


# def parse_args(argv=None):
#     p = argparse.ArgumentParser(
#         description="Acquire a pyramid reference image: average OCAM frames "
#                      "and normalize by the flux on the illuminated (valid) pixels."
#     )
#     p.add_argument("-n", "--nFrame", type=int, default=1000,
#                    help="number of frames to average")
#     return p.parse_args(argv)


def main():
    # args = parse_args()

    ocamCal = dao.shm(shm_names.SHM_OCAM_REDUCED_FRAME)
    validMask = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS)
    ref = dao.shm(shm_names.SHM_OCAM_REFERENCE)
    refFlux = dao.shm(shm_names.SHM_OCAM_REFERENCE_FLUX)

    nFrame = int(sys.argv[1])
    acc = ocamCal.get_data().astype(np.float64) * 0
    for k in range(nFrame):
        sys.stdout.write(f"\raveraging... {k+1}/{nFrame}")
        sys.stdout.flush()
        acc = acc + ocamCal.get_data(check=True, semNb=5)
    print()

    avg = (acc / nFrame) #* validMask.get_data()

    flux = np.sum(avg * validMask.get_data())
    if flux == 0:
        print("ERROR: zero flux on the valid pixels; reference not updated.")
        sys.exit(1)

    ref.set_data(ref.get_data() * 0 + (avg / flux).astype(np.float32))
    refFlux.set_data(refFlux.get_data() * 0 + flux.astype(np.float32))


if __name__ == "__main__":
    main()
