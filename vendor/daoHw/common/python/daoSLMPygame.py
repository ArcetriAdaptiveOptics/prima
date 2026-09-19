#!/usr/bin/env python3
import os
import numpy as np
import pygame
import screeninfo
import dao
import argparse
import time

def Create_Image(width, height, is_color=False):
    if is_color:
        image = np.ones((height, width, 3), dtype=np.uint8) * 255
    else:
        image = np.random.randint(0, 255, (height, width)).astype(np.uint8)
    return image

def to_rgb(image):
    """Ensure grayscale image is converted to RGB (3-channel)."""
    if image.ndim == 2:
        return np.stack((image,) * 3, axis=-1)
    return image

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--monitor", type=int, default=0, help="The monitor to output to. (Default: 0)")
    parser.add_argument("-s", "--shm", type=str, default="/tmp/image.im.shm", help="shm file to get image from")
    parser.add_argument("-u", "--update", type=int, default=100, help="milliseconds between updates")
    args = parser.parse_args()

    screen_id = args.monitor

    # Get monitor info
    screen = screeninfo.get_monitors()[screen_id]
    print(screen)

    width, height = screen.width, screen.height

    # Set environment for pygame to open the window on the correct monitor
    os.environ['SDL_VIDEO_WINDOW_POS'] = f"{screen.x},{screen.y}"

    # Initialize pygame
    pygame.init()

    # Create fullscreen window
    flags = pygame.NOFRAME | pygame.HWSURFACE | pygame.DOUBLEBUF
    #flags = pygame.NOFRAME | pygame.FULLSCREEN 
    screen_surface = pygame.display.set_mode((width, height), flags)
    pygame.display.set_caption("projector")

    # Access shared memory image
    image_shm = dao.shm(args.shm)

    try:
        clock = pygame.time.Clock()
        running = True
        while running:
            try:
                image = image_shm.get_data()
                image = to_rgb(image)

                surface = pygame.surfarray.make_surface(image.swapaxes(0, 1))
                screen_surface.blit(surface, (0, 0))
            except Exception as e:
                print("Frame skipped due to error:", e)
                screen_surface.fill((0, 0, 0))
            pygame.display.flip()

            # Handle events (e.g. key press to quit)
            #for event in pygame.event.get():
            #    if event.type == pygame.QUIT or (
            #        event.type == pygame.KEYDOWN and event.key == pygame.K_q
            #    ):
            #        running = False

            # If you don't want full event handling, at least this:
            pygame.event.pump()

            # Limit frame rate
            clock.tick(1000 // args.update)

    except KeyboardInterrupt:
        pass
    finally:
        print("Exiting.")
        pygame.quit()
