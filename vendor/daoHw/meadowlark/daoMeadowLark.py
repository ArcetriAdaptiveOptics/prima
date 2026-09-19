# /*****************************************************************************
#   DAO project
#   Python meadowlark interface
#   David Barr
#  *****************************************************************************/

# /*==========================================================================*/


import dao
import numpy as np
import sys,os
from ctypes import *
from matplotlib import pyplot as plt
from time import time, sleep

import threading
import argparse

BLINK_C_WRAPPER_PATH = "C:\\Program Files\\Meadowlark Optics\\Blink Plus\\SDK\\Blink_C_wrapper"
BLINK_C_WRAPPER_NAME = "Blink_C_wrapper"
IMAGE_GEN_PATH = "C:\\Program Files\\Meadowlark Optics\\Blink Plus\\SDK\\ImageGen"
IMAGE_GEN_NAME = "ImageGen"
LUT_FILE = "C:\\Program Files\\Meadowlark Optics\\Blink Plus\\LUT Files\\slm7481_at633_30C.LUT"

def reportError(slm_lib):
    error = slm_lib.Get_last_error_message()
    print(f"Error: {error}")
    slm_lib.Delete_SDK()
    exit(1)

def ThreadedContol(slm_lib, board_number, shm_filename, timeout):
    """
    Worker function for each SLM board
    """
    threadId = board_number
    print(f"Thread for SLM ID {board_number} started with shared memory: {shm_filename}")
    board_number = c_uint(board_number)
    timeout_ms = c_uint(timeout)

    ret = slm_lib.Load_LUT_file(board_number, b""+LUT_FILE.encode('utf-8'))
    if ret != 1:
        print(f"Thread {threadId}: Setting the LUT failed: {LUT_FILE}")
        reportError(slm_lib)
    height = c_uint(slm_lib.Get_image_height(board_number))
    width = c_uint(slm_lib.Get_image_width(board_number))
    depth = c_uint(slm_lib.Get_image_depth(board_number))

    print(f"Thread {threadId}: SLM Size: {width.value}x{height.value} Depth: {depth.value}")

    ret = slm_lib.SetWaitForTrigger(board_number, False)
    if ret != 1:
        print(f"Thread {threadId}: Setting the wait for trigger to false failed")
        reportError(slm_lib)

    print(f"Thread {threadId}: Set wait for trigger to false")
    print(f"Thread {threadId}: **** finished initialisation ****")

    print(f"Thread {threadId}: Opening SHM: {shm_filename}")
    shm = dao.shm(shm_filename, logLevel=0)
    if not shm.image.md: # Check if metadata pointer is NULL (i.e. failed to load SHM)
        print(f"Thread {threadId}: Error: failed to load {shm_filename}")
        exit(1)

    print(f"Thread {threadId}: {shm_filename} loaded successfully")

    tmp = shm.get_data()
    if tmp.shape[0] != width.value or tmp.shape[1] != height.value:
        print(f"Thread {threadId}: Error: SHM dimensions do not match SLM dimensions: got {tmp.shape[0]}x{tmp.shape[1]}, expected {width.value}x{height.value}")
        exit(1)
    # compare bitdepth with np.uint8 (8)
    if tmp.dtype != np.uint8:
        print(f"Thread {threadId}: Error: SHM data type does not match SLM data type: got {tmp.dtype}, expected np.uint8")
        exit(1)

    # real-time loop:
    last_frame_id = -1
    frames_missed = 0
    frame_count = 0
    last_frame_time = 0

    try:
        start_time = time()
        print(f"Thread {threadId}: Contents of {shm_filename} now being sent to the SLM on each change...")
        while True:


            # Get current SHM data
            data = shm.get_data(check=True, spin=True)
            frame_id = shm.get_counter()  # Get the current frame counter

            # Check for missed frames
            if last_frame_id != -1 and frame_id > last_frame_id + 1:
                missed = (frame_id - last_frame_id - 1)
                frames_missed += missed
                # 
                # print(f"[SLM] Warning: Missed {missed} frame(s) (last: {last_frame_id}, current: {frame_id})")

            # Track the time between frames to estimate frequency
            frame_count += 1

            # Send image to SLM
            # print(f"[SLM] Frame {frame_count}: Sending image (Frame ID: {frame_id})", end='\r')
            try:
                c_data = np.ascontiguousarray(data)
                ret = slm_lib.Write_image(board_number, c_data.ctypes.data_as(POINTER(c_uint8)), timeout_ms)
            except Exception as e:
                error = slm.slm_lib.Get_last_error_message()
                print(f"Thread {threadId}: [SLM] Error sending image: {e}. SDK Error: {error}")
                break

            # Update last frame info
            last_frame_time = time()
            last_frame_id = frame_id

            # Print diagnostics every 100 frames
            if frame_count % args.disp == 0:
                now = time()
                elapsed_time = now - start_time
                frequency_estimate = args.disp / elapsed_time  # frames per second
                print(f"Thread {threadId}: [SLM] Frame Rate: {frequency_estimate:.2f} Hz, Missed Frames: {frames_missed}, Current Frame ID: {frame_id}")
                frames_missed = 0
                start_time = now

    except Exception as e:
        slm_lib.Delete_SDK()
        print(e)

    return

    

if __name__=='__main__':
    parser = argparse.ArgumentParser(description="Send SHM image data to Meadowlark SLM")
    parser.add_argument("--shm", dest="shm_filename", nargs='+', required=True, help="Shared memory names to read from (space-separated)")
    parser.add_argument("--slm-ids", dest="slm_id", nargs='+', type=int, default=[1], help="SLM board numbers (space-separated, default: 1)")
    parser.add_argument("--timeout", dest="timeout", type=int, default=5000, help="Timeout for SLM operations in ms (default: 5000ms)")
    parser.add_argument("--display", dest="disp", type=int, default=100, help="number of frames between displaying info to screen (default: 100)")
    args = parser.parse_args()
    print("=" * 50)
    print(f"{sys.argv[0]}")
    print("=" * 50)
    print(f"Shared Memory Files: {args.shm_filename}")
    print(f"SLM IDs: {args.slm_id}")
    print(f"Timeout: {args.timeout} ms")
    print(f"Display Interval: {args.disp} frames")
    print("=" * 50, end='\n')

    # Sanity check: ensure shm files and slm IDs have matching counts
    if len(args.shm_filename) != len(args.slm_id):
        print(f"ERROR: Number of shared memory files ({len(args.shm_filename)}) does not match number of SLM IDs ({len(args.slm_id)})")
        print(f"SHM files: {args.shm_filename}")
        print(f"SLM IDs: {args.slm_id}")
        parser.error("Mismatch between number of shared memory files and SLM IDs")
        exit(-1)

    errors = []
    for shm_filename in args.shm_filename:
        if not os.path.exists(shm_filename):
            errors.append(f"Error: Shared memory file '{shm_filename}' does not exist")

    cdll.LoadLibrary(BLINK_C_WRAPPER_PATH)
    slm_lib = CDLL(BLINK_C_WRAPPER_NAME)

    cdll.LoadLibrary(IMAGE_GEN_PATH)
    image_lib = CDLL(IMAGE_GEN_NAME)

    # Basic parameters for calling Create_SDK
    num_boards_found = c_uint(0)
    constructed_okay = c_uint(-1)

    # Call the Create_SDK constructor
    # Returns a handle that's passed to subsequent SDK calls
    slm_lib.Create_SDK(byref(num_boards_found), byref(constructed_okay))

    if constructed_okay.value == 0:
        print("Error: Blink SDK failed to initialise")
        reportError(slm_lib)
    
    print(f"Initalised blink")

    print(f"Found {num_boards_found.value} boards")


    # Check all requested SLM IDs
    for slm_id in args.slm_id:
        if num_boards_found.value < slm_id:
            errors.append(f"Error: board {slm_id} not found {num_boards_found.value} boards available")
            errors.append(f"       please select a value between 1 and {num_boards_found.value}")
        elif slm_id < 1:
            errors.append(f"Error: id requested {slm_id} is invalid")
            errors.append(f"       please select a value between 1 and {num_boards_found.value}")

    # Check if any boards were found at all
    if num_boards_found.value < 0:
        errors.append("Error: no boards found")

    # Report all errors if any exist
    if errors:
        for error in errors:
            print(error)
        reportError(slm_lib)

    threads = []
    # Create threads for each SLM ID and corresponding shared memory file
    for slm_id, shm_filename in zip(args.slm_id, args.shm_filename):
        thread = threading.Thread(
            target=ThreadedContol, 
            args=(slm_lib, slm_id, shm_filename, args.timeout),
            name=f"SLM-{slm_id}"
        )
        thread.daemon = True  # Dies when main thread dies
        threads.append(thread)
        thread.start()
        print(f"Started thread for SLM ID {slm_id}")

    print(f"All {len(threads)} threads started")

    # Keep main thread alive (you might want to replace this with your main logic)
    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        print("\nShutting down...")

    

    


