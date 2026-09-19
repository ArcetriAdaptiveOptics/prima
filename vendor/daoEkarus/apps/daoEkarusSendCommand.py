#!/usr/bin/env python3
#
import dao
import socket
import sys
import time
import numpy as np
from daoEkarusShmNames import *

if __name__ == "__main__":
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        print("Usage daoEkarusSendCommand.py <SHM> <IP> <PORT> <CAMERASHM_optional>")
        exit()
    shm_filename = sys.argv[1]
    ip = sys.argv[2]
    port = int(sys.argv[3])

    frameId = dao.shm(SHM_OCAM_FRAME_ID, np.zeros((1, 1)).astype(np.uint64))
    camera_shm = None
    if len(sys.argv) == 5:
        camera_shm = sys.argv[4]
        print(f"Camera SHM: {camera_shm}")

    print(f"Reading file: {shm_filename}")
    shm = dao.shm(shm_filename)
    a = shm.get_data()
    print(f"shape: {a.shape}")
    print(f"Sending on {ip}:{port}")

    frame = 0
    if camera_shm is not None:
        print(f"Using camera SHM: {camera_shm}")
        camera_shm = dao.shm(camera_shm)
        frame = camera_shm.get_frame_id()
        print(f"Initial frame ID: {frame}")

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    start = time.time()
    count = 0
    tCount = 0
    ToSend = np.zeros((a.shape[0] + 1, 1), dtype=np.float32)
    t1 = time.time()
    try:
        while True:
            # a = shm.get_data(check=True)
            # ToSend[0] = tCount
            t0 = time.time()
            ToSend[:-1] = shm.get_data(check=True)
            t2 = time.time()
            sys.stdout.write("\rtime since last command = %.6f" % (t2 - t1))
            if camera_shm is not None:
                frame = np.float32(camera_shm.get_frame_id())
                ToSend[-1] = frame
            else:
                ToSend[-1] = np.float32(tCount)
            # print(ToSend)
            udp_socket.sendto(ToSend.tobytes(), (ip, port))
            frameId.set_data(np.uint64(ToSend[-1]))
            # sys.stdout.write(", frame ID = %.6f" % (ToSend[-1][0])) # 13/04/2026 added [0] otherwize non-0 dim array
            sys.stdout.write(", frame ID = %.6f" % (ToSend[-1][0])) 


            t1 = time.time()
            # t0=t1
            sys.stdout.write(", send Time = %.6f" % (t1 - t2))
            sys.stdout.flush()
            # udp_socket.sendto(ToSend.tobytes(), (ip, port))
            # count+=1
            tCount += 1
            # if count >= 1000:
            #    count = 0
            #    duration = time.time() - start
            #    print(f"Send {tCount} @ {1000/duration} Hz", end="\r")
            #    start=time.time()
    except KeyboardInterrupt:
        print("Exiting")

    udp_socket.close()
