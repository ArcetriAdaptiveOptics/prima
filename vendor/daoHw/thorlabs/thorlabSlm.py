#!/usr/bin/env python3
"""
SLM Display — 60 Hz VSync-locked, reads from shared memory
Display : 1920x1200 on DP-1-2 (DISPLAY_IDX = 1)
SHM     : /tmp/sslm.im.shm  →  numpy array (1200, 1920) uint8

Requirements:
    pip install pygame PyOpenGL numpy

Run:
    DISPLAY=:0 python slm_display.py
    DISPLAY=:0 python slm_display.py --measure    # just measure FPS, no SHM
"""

import sys
import time
import argparse

import dao
import numpy as np
import pygame
from pygame.locals import OPENGL, DOUBLEBUF, FULLSCREEN, NOFRAME, QUIT, KEYDOWN, K_ESCAPE
from OpenGL.GL import (
    glGenTextures, glBindTexture, glTexParameteri, glTexImage2D, glTexSubImage2D,
    glEnable, glDisable, glClear, glBegin, glEnd, glTexCoord2f, glVertex2f,
    glMatrixMode, glLoadIdentity, glViewport, glClearColor, glFinish,
    GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_NEAREST, GL_CLAMP_TO_EDGE,
    GL_RED, GL_UNSIGNED_BYTE, GL_COLOR_BUFFER_BIT, GL_QUADS,
    GL_PROJECTION, GL_MODELVIEW,
)

# ── Config (overridden by CLI args) ───────────────────────────────────────────
SLM_WIDTH   = 1920
SLM_HEIGHT  = 1200
DISPLAY_IDX = 1
SHM_PATH    = '/tmp/sslm.im.shm'
# ──────────────────────────────────────────────────────────────────────────────


def init_display():
    pygame.init()

    n = pygame.display.get_num_displays()
    print(f"Detected {n} display(s)")
    if DISPLAY_IDX >= n:
        print(f"ERROR: display index {DISPLAY_IDX} not available (found {n})")
        sys.exit(1)

    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)
    pygame.display.gl_set_attribute(pygame.GL_SWAP_CONTROL, 1)   # VSync ON

    pygame.display.set_mode(
        (SLM_WIDTH, SLM_HEIGHT),
        OPENGL | DOUBLEBUF | FULLSCREEN | NOFRAME,
        display=DISPLAY_IDX,
    )
    pygame.display.set_caption("SLM")

    # Orthographic identity — NDC coords [-1,1]
    glMatrixMode(GL_PROJECTION); glLoadIdentity()
    glMatrixMode(GL_MODELVIEW);  glLoadIdentity()
    glViewport(0, 0, SLM_WIDTH, SLM_HEIGHT)
    glClearColor(0, 0, 0, 1)


def alloc_texture():
    """Allocate a single GPU texture for the SLM (grayscale, no data yet)."""
    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    # Allocate storage on GPU — no pixel data yet
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RED,
                 SLM_WIDTH, SLM_HEIGHT, 0,
                 GL_RED, GL_UNSIGNED_BYTE, None)
    glBindTexture(GL_TEXTURE_2D, 0)
    return tex_id


def push_frame(tex_id, array):
    """Upload a (1200, 1920) uint8 numpy array to the GPU texture."""
    # Ensure C-contiguous and correct dtype
    data = np.ascontiguousarray(np.flipud(array), dtype=np.uint8)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexSubImage2D(                        # reuse allocation — fast path
        GL_TEXTURE_2D, 0, 0, 0,
        SLM_WIDTH, SLM_HEIGHT,
        GL_RED, GL_UNSIGNED_BYTE,
        data,
    )


def draw(tex_id):
    """Blit texture fullscreen."""
    glClear(GL_COLOR_BUFFER_BIT)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex2f(-1, -1)
    glTexCoord2f(1, 0); glVertex2f( 1, -1)
    glTexCoord2f(1, 1); glVertex2f( 1,  1)
    glTexCoord2f(0, 1); glVertex2f(-1,  1)
    glEnd()
    glDisable(GL_TEXTURE_2D)


def measure_fps(n_frames=120):
    """Measure real VSync frame rate — no SHM needed."""
    print(f"Measuring VSync rate over {n_frames} frames ...")
    intervals = []
    for _ in range(n_frames):
        t = time.perf_counter()
        glClear(GL_COLOR_BUFFER_BIT)
        pygame.display.flip()
        intervals.append(time.perf_counter() - t)

    intervals = intervals[10:]   # discard warmup
    avg = sum(intervals) / len(intervals)
    std = float(np.std(intervals)) * 1000
    print(f"  Mean interval : {avg*1000:.3f} ms  →  {1/avg:.2f} Hz")
    print(f"  Jitter (std)  : {std:.3f} ms")
    print(f"  Min / Max     : {min(intervals)*1000:.3f} / {max(intervals)*1000:.3f} ms")


def run_shm():
    slm = dao.shm(SHM_PATH)
    print(f"Connected to SHM: {SHM_PATH}")

    tex_id  = alloc_texture()
    frame   = 0
    t_start = time.perf_counter()
    t_report = t_start

    print("Running — press ESC to quit")
    running = True
    while running:

        # ── Events ────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                running = False

        # ── Block until writer pushes a new frame ─────────────────────────
        pattern = slm.get_data(check=True)   # (1200, 1920) uint8

        # ── CPU → GPU upload ──────────────────────────────────────────────
        push_frame(tex_id, pattern)

        # ── Draw & present — flip() blocks on VSync ───────────────────────
        draw(tex_id)
        glFinish()
        pygame.display.flip()   # ← this is the 60 Hz clock

        frame += 1

        # ── FPS report every 5 s ──────────────────────────────────────────
        now = time.perf_counter()
        if now - t_report >= 5.0:
            fps = frame / (now - t_start)
            print(f"  frame {frame:6d}  |  {fps:.2f} Hz")
            t_report = now

    pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SLM display — VSync-locked 60 Hz")
    parser.add_argument("--width",   type=int,   default=1920,               help="SLM width  (default: 1920)")
    parser.add_argument("--height",  type=int,   default=1200,               help="SLM height (default: 1200)")
    parser.add_argument("--display", type=int,   default=1,                  help="Display index (default: 1)")
    parser.add_argument("--shm",     type=str,   default="/tmp/sslm.im.shm", help="Shared memory path (default: /tmp/sslm.im.shm)")
    parser.add_argument("--measure", action="store_true",                     help="Measure VSync frame rate only (no SHM required)")
    args = parser.parse_args()

    # Override globals with CLI args
    SLM_WIDTH   = args.width
    SLM_HEIGHT  = args.height
    DISPLAY_IDX = args.display
    SHM_PATH    = args.shm

    init_display()

    if args.measure:
        measure_fps()
        pygame.quit()
    else:
        run_shm()