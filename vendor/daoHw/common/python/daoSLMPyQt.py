#!/usr/bin/env python3
#!/usr/bin/env python3
import sys
import time
import numpy as np
import argparse
from PyQt5.QtWidgets import QApplication, QLabel, QWidget
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
import screeninfo
import dao


def to_rgb(image):
    if image.ndim == 2:
        return np.stack((image,) * 3, axis=-1)
    return image

def numpy_to_qimage(img):
    h, w, ch = img.shape
    bytes_per_line = ch * w
    return QImage(img.data, w, h, bytes_per_line, QImage.Format_RGB888)

class FullscreenDisplay(QWidget):
    def __init__(self, screen_geometry, shm_path, update_interval):
        super().__init__()
        self.setGeometry(screen_geometry.x, screen_geometry.y,
                         screen_geometry.width, screen_geometry.height)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setCursor(Qt.BlankCursor)

        self.label = QLabel(self)
        self.label.setGeometry(0, 0, screen_geometry.width, screen_geometry.height)
        self.label.setAlignment(Qt.AlignCenter)

        self.image_shm = dao.shm(shm_path)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_image)
        self.timer.start(update_interval)

    def update_image(self):
        try:
            image = self.image_shm.get_data()
            image = np.rot90(image, -1)
            image = to_rgb(image)
            qimg = numpy_to_qimage(image)
            pixmap = QPixmap.fromImage(qimg)
            self.label.setPixmap(pixmap)
        except Exception as e:
            print("Error displaying image:", e)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--monitor", type=int, default=0, help="The monitor to output to.")
    parser.add_argument("-s", "--shm", type=str, default="/tmp/image.im.shm", help="shm file to get image from")
    parser.add_argument("-u", "--update", type=int, default=100, help="milliseconds between updates")
    args = parser.parse_args()

    screen_id = args.monitor
    screen = screeninfo.get_monitors()[screen_id]

    app = QApplication(sys.argv)
    display = FullscreenDisplay(screen, args.shm, args.update)
    display.showFullScreen()
    sys.exit(app.exec_())
