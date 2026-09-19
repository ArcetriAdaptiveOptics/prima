#!/usr/bin/env python3
#

import dao
import ast
import argparse
import daoEkarusShmNames as shm_names
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="Modulate/demodulate method to measure OG on DM modes"
    )
    parser.add_argument("modes", type=_parse_list_or_element(int), help="mode ids to be modulated")
    parser.add_argument("amps", type=_parse_list_or_element(float), help="modulation amplitudes")
    parser.add_argument("freqs", type=_parse_list_or_element(float), help="modulation frequencies")
    return parser.parse_args()


def demodulated_amplitude(signal_data, carrier_freq, sampling_freq):
    data = np.asarray(signal_data, dtype=np.float32)
    is_1d = (data.ndim == 1)
    if is_1d:
        data = data[:, np.newaxis]
    nt = data.shape[0]
    t = np.arange(nt, dtype=np.float32) / sampling_freq
    w = 2 * np.pi * carrier_freq
    # Linear detrend: remove mean and tilt
    cur_data = data - np.mean(data, axis=0, keepdims=True)
    tilt = (cur_data[-1:] - cur_data[0:1]) / nt
    t_ramp = np.arange(nt, dtype=np.float32)[:, np.newaxis]
    cur_data = cur_data - tilt * t_ramp - cur_data[0:1]
    # Directly compute I and Q components
    sin_carrier = np.sin(w * t)[:, np.newaxis]
    cos_carrier = np.cos(w * t)[:, np.newaxis]
    q_comp = np.mean(cur_data * sin_carrier, axis=0)
    i_comp = np.mean(cur_data * cos_carrier, axis=0)
    # Calculate amplitude from magnitude of I/Q vectors
    amplitude = 2.0 * np.sqrt(q_comp**2 + i_comp**2)
    return float(amplitude[0]) if is_1d else amplitude


def modulate_and_demodulate_modes(
    mode_ids,
    amplitudes,
    frequencies,
    n_reps:int=10,
    n_steps:int=1000,
    sem:int=8,
):
    """
    Modulates modes on the DM channel 3, records DM total commands and WFS reconstructed
    modes, and calculates the measured-to-commanded amplitude ratio after
    demodulation.
    """

    mode_ids = np.atleast_1d(mode_ids)
    frequencies = np.atleast_1d(frequencies)
    if len(mode_ids) != len(frequencies):
        raise ValueError('Expected number of modes to be the same length of the input frequencies. ' \
        f'Instead, modes are {mode_ids} and frequencies are {frequencies}')
    
    if np.isscalar(amplitudes):
        amplitudes = np.full(len(mode_ids), amplitudes, dtype=np.float32)
    else:
        amplitudes = np.atleast_1d(amplitudes)
    if len(mode_ids) != len(amplitudes):
        raise ValueError('Expected number of modes to be the same length of the input amplitudes. ' \
        f'Instead, modes are {mode_ids} and frequencies are {amplitudes}')
    
    # Attach to Shared Memory streams
    m2c_shm = dao.shm(shm_names.SHM_DM1_M2C)
    c2m_shm = dao.shm(shm_names.SHM_DM1_C2M)
    dm_dist_shm = dao.shm(shm_names.SHM_DM1_CHANNEL_3)
    dm_cmd_shm = dao.shm(shm_names.SHM_DM1_CMD)
    wfs_modes_shm = dao.shm(shm_names.SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN)

    fs = dao.shm("/tmp/ocam2fps.im.shm").get_data()[0,0]

    m2c = m2c_shm.get_data()
    c2m = c2m_shm.get_data()

    nb_act = m2c.shape[0]
    n_wfs_modes = wfs_modes_shm.get_data().shape[0]

    # Pre-generate sinusoidal mode disturbance signals
    t = np.arange(n_steps, dtype=np.float32) / fs
    modal_sinusoids = np.zeros((len(mode_ids), n_steps), dtype=np.float32)

    for idx, (amp, freq) in enumerate(zip(amplitudes, frequencies)):
        modal_sinusoids[idx, :] = amp * np.sin(2.0 * np.pi * freq * t)

    # Convert modal excitations into actuator commands
    actuator_dist = m2c[:, mode_ids] @ modal_sinusoids

    # Buffers to record telemetry over n_steps
    dm_tot_history = np.zeros((nb_act, n_steps), dtype=np.float32)
    wfs_modes_history = np.zeros((n_wfs_modes, n_steps), dtype=np.float32)

    for _ in range(n_reps):
        # Acquisition loop
        try:
            for i in range(n_steps):
                # Write frame to DM Channel 3
                dm_dist_shm.set_data(actuator_dist[:, i : i + 1])

                # Read SHM_DM1_CMD and SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN
                dm_tot_history[:, i] = dm_cmd_shm.get_data(
                    check=True, semNb=sem
                ).flatten()
                wfs_modes_history[:, i] = wfs_modes_shm.get_data(
                    check=True, semNb=sem
                ).flatten()
        finally:
            # Reset DM channel 3 to zero after acquisition
            dm_dist_shm.set_data(np.zeros((nb_act, 1), dtype=np.float32))

        # Project DM total command vectors into modal space using SHM_DM1_C2M
        dm_modes_history = c2m @ dm_tot_history

        # Demodulate amplitudes for each active mode
        ratios = np.zeros(len(mode_ids), dtype=np.float32)

        for idx, (m_id, freq) in enumerate(zip(mode_ids, frequencies)):
            cmd_amp = demodulated_amplitude(dm_modes_history[m_id, :], freq, fs)
            meas_amp = demodulated_amplitude(wfs_modes_history[m_id, :], freq, fs)

            ratios[idx] = meas_amp / cmd_amp if cmd_amp != 0 else np.nan

        print("\nMeasured / Commanded Mode Ratios:")
        for m_id, freq, ratio in zip(mode_ids, frequencies, ratios):
            print(f"  Mode {m_id:3d} @ {freq:6.1f} Hz : {ratio:.4f}")

    return ratios


def _parse_list_or_element(target_type):
    """Returns a parsing function that converts inputs to a list of target_type."""
    def parser_func(value):
        try:
            parsed = ast.literal_eval(value)
            # Convert a single element into a single-item list
            if isinstance(parsed, (int, float)):
                items = [parsed]
            elif isinstance(parsed, list):
                items = parsed
            else:
                raise argparse.ArgumentTypeError(f"Expected a number or a list, got: {value}")
            # Cast and strictly validate the elements to the target type
            return [target_type(item) for item in items]
        except (ValueError, SyntaxError) as e:
            raise argparse.ArgumentTypeError(f"Invalid format or type for value '{value}': {e}")
    return parser_func

if __name__ == "__main__":
    args = parse_args()
    modulate_and_demodulate_modes(mode_ids=args.modes,amplitudes=args.amps,
                                  frequencies=args.freqs,n_reps=10,n_steps=3000)
