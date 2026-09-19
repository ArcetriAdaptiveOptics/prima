#!/usr/bin/env python3
import numpy as np
import cv2
import screeninfo
import dao
import argparse



def Create_Image(X,Y,color=False):
    # create image
    if is_color:
        image = np.ones((height, width, 3), dtype=np.float32)
    else:
        image = np.random.randint(0, 255, (height,width)).astype(np.uint8)

    return image


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--monitor",type=int,default=0,help="The monitor to output to. (Default: 0)")
    parser.add_argument("-s", "--shm",type=str,default=0,help="shm file to get image from (Default: /tmp/image.im.shm)")
    parser.add_argument("-u", "--update",type=int,default=100,help="number of microseconds between updates")
    args = parser.parse_args()

    screen_id = args.monitor

    # get the size of the screen
    screen = screeninfo.get_monitors()[screen_id]
    print(screen)
    width, height = screen.width, screen.height

    image_shm = dao.shm(args.shm)
    image = image_shm.get_data()
    image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    print(image)
    window_name = 'projector'
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(window_name, screen.x, screen.y)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN,
                          cv2.WINDOW_FULLSCREEN)
    #cv2.resizeWindow(window_name, screen.width, screen.height)

    #cv2.imshow(window_name, np.zeros((1200,1920)).astype(np.uint8))
    cv2.imshow(window_name, image)

    try:
        while True:
            image = image_shm.get_data()
            cv2.imshow(window_name, image)
            #cv2.imshow(window_name, np.zeros((1200,1920)).astype(np.uint8))
            # Wait for 1 second
            key = cv2.waitKey(args.update)
            if key == ord('q'):
                raise Exception
    except Exception or KeyboardInterrupt or cv2.error as e:
        print("exiting")
        cv2.destroyAllWindows()