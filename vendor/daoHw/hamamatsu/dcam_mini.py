"""
dcam_mini.py — minimal Linux ctypes binding for Hamamatsu's DCAM-API (v4 / SDK4),
enough to open an ORCA camera, set exposure, and grab frames as numpy arrays.

This talks directly to libdcamapi.so (installed by "DCAM-API Lite for Linux") via
ctypes, so it needs nothing beyond numpy — no pyDCAM, no pylablib, no Windows-only
wrappers. It intentionally only covers the small subset of the API needed for a
live-view/snap tool; the full API has hundreds of properties and calls.

Struct/constant layout is taken from Hamamatsu's dcamapi4.h (via its public
DCAM_IDPROP_*, DCAMERR_* and structure definitions). If your camera model needs a
property this file doesn't expose, add its ID from dcamapi4.h / dcamprop.h — the
pattern here (dcamprop_setvalue / dcamprop_getvalue with a DCAM_IDPROP_* constant)
is the same for every property.
"""

import ctypes as C
import numpy as np

# ---------------------------------------------------------------------------
# Low-level types / structs (must match dcamapi4.h field order exactly)
# ---------------------------------------------------------------------------

int32 = C.c_int32
HDCAM = C.c_void_p
HDCAMWAIT = C.c_void_p


class DCAM_TIMESTAMP(C.Structure):
    _fields_ = [("sec", C.c_uint32), ("microsec", C.c_int32)]


class DCAMAPI_INIT(C.Structure):
    _fields_ = [
        ("size", int32),
        ("iDeviceCount", int32),
        ("reserved", int32),
        ("initoptionbytes", int32),
        ("initoption", C.POINTER(int32)),
        ("guid", C.c_void_p),
    ]


class DCAMDEV_OPEN(C.Structure):
    _fields_ = [("size", int32), ("index", int32), ("hdcam", HDCAM)]


class DCAMWAIT_OPEN(C.Structure):
    _fields_ = [
        ("size", int32),
        ("supportevent", int32),
        ("hwait", HDCAMWAIT),
        ("hdcam", HDCAM),
    ]


class DCAMWAIT_START(C.Structure):
    _fields_ = [
        ("size", int32),
        ("eventhappened", int32),
        ("eventmask", int32),
        ("timeout", int32),
    ]


class DCAMBUF_FRAME(C.Structure):
    _fields_ = [
        ("size", int32),
        ("iKind", int32),
        ("option", int32),
        ("iFrame", int32),
        ("buf", C.c_void_p),
        ("rowbytes", int32),
        ("type", C.c_int),
        ("width", int32),
        ("height", int32),
        ("left", int32),
        ("top", int32),
        ("timestamp", DCAM_TIMESTAMP),
        ("framestamp", int32),
        ("camerastamp", int32),
    ]


class DCAMPROP_ATTR(C.Structure):
    """dcamprop.h DCAMPROP_ATTR — field order must match exactly."""
    _fields_ = [
        ("cbSize", int32),
        ("iProp", int32),
        ("option", int32),
        ("iReserved1", int32),
        ("attribute", int32),
        ("iGroup", int32),
        ("iUnit", int32),
        ("attribute2", int32),
        ("valuemin", C.c_double),
        ("valuemax", C.c_double),
        ("valuestep", C.c_double),
        ("valuedefault", C.c_double),
        ("nMaxChannel", int32),
        ("iReserved3", int32),
        ("nMaxView", int32),
        ("iProp_NumberOfElement", int32),
        ("iProp_ArrayBase", int32),
        ("iPropStep_Element", int32),
    ]


# ---------------------------------------------------------------------------
# Constants (subset of dcamapi4.h / dcamprop.h)
# ---------------------------------------------------------------------------

DCAMCAP_START_SEQUENCE = -1
DCAMWAIT_CAPEVENT_FRAMEREADY = 0x0002

# dcamapi4.h DCAMERR
DCAMERR_ABORT = 0x80000003
DCAMERR_TIMEOUT = 0x80000106

DCAM_PIXELTYPE_MONO8 = 0x00000001
DCAM_PIXELTYPE_MONO16 = 0x00000002

DCAM_IDPROP_EXPOSURETIME = 0x001F0110
DCAM_IDPROP_SUBARRAYHPOS = 0x00402110
DCAM_IDPROP_SUBARRAYHSIZE = 0x00402120
DCAM_IDPROP_SUBARRAYVPOS = 0x00402130
DCAM_IDPROP_SUBARRAYVSIZE = 0x00402140
DCAM_IDPROP_SUBARRAYMODE = 0x00402150
DCAM_IDPROP_IMAGE_WIDTH = 0x00420210
DCAM_IDPROP_IMAGE_HEIGHT = 0x00420220
DCAM_IDPROP_IMAGE_PIXELTYPE = 0x00420270

# Readout speed / scan mode. Scientific sCMOS ORCA models have no analog gain;
# READOUTSPEED is the knob that trades frame rate for read noise. The valid
# values are an enum that depends on the model, e.g. ORCA-Fusion:
#   1 = ULTRAQUIET (lowest noise, slow), 2 = STANDARD
# ORCA-Flash4.0 V3: 1 = SLOWEST, 2 = FASTEST. Query get_property_range() for
# the actual [min, max] this camera accepts.
DCAM_IDPROP_READOUTSPEED = 0x00400110
DCAMPROP_READOUTSPEED__SLOWEST = 1
DCAMPROP_READOUTSPEED__FASTEST = 0x7FFFFFFF

DCAM_IDPROP_SUBARRAYMODE__OFF = 1
DCAM_IDPROP_SUBARRAYMODE__ON = 2

# Common install/search locations for libdcamapi.so. `ctypes.CDLL("libdcamapi.so")`
# alone works if the installer ran ldconfig (the usual case for the .deb/.rpm from
# Hamamatsu); the extra paths are a fallback for a manual/non-standard install.
_CANDIDATE_LIB_NAMES = [
    "libdcamapi.so",
    "dcamapi",
    "/usr/local/lib/libdcamapi.so",
    "/usr/lib/libdcamapi.so",
    "/usr/lib/x86_64-linux-gnu/libdcamapi.so",
    "/opt/hamamatsu/dcamsdk4/lib/libdcamapi.so",
]


class DCAMError(Exception):
    """Raised on any non-zero-or-positive DCAM-API return code."""


def _find_lib():
    tried = []
    for name in _CANDIDATE_LIB_NAMES:
        try:
            return C.CDLL(name)
        except OSError as e:
            tried.append(f"{name}: {e}")
    raise OSError(
        "Could not load libdcamapi.so from any of the usual locations.\n"
        "Run `ldconfig -p | grep -i dcam` (or `find / -name 'libdcamapi*' 2>/dev/null`) "
        "to locate it, then pass the exact path as DCAMCamera(lib_path=...).\n"
        "Tried:\n  " + "\n  ".join(tried)
    )


def _check(err, name):
    if err < 0:
        raise DCAMError(f"{name} failed (DCAM error code 0x{err & 0xFFFFFFFF:08X})")
    return err


class DCAMCamera:
    """Thin wrapper around one DCAM-API camera handle.

    Typical use:
        with DCAMCamera(index=0) as cam:
            cam.set_exposure(0.05)
            cam.start(nbuf=10)
            frame = cam.get_frame()   # numpy array, uint16 or uint8
            cam.stop()
    """

    def __init__(self, index=0, lib_path=None):
        self.lib = C.CDLL(lib_path) if lib_path else _find_lib()
        self._setup_prototypes()
        self.index = index
        self.hdcam = None
        self.hwait = None
        self._streaming = False

    # -- low-level plumbing --------------------------------------------------

    def _setup_prototypes(self):
        lib = self.lib

        lib.dcamapi_init.argtypes = [C.POINTER(DCAMAPI_INIT)]
        lib.dcamapi_init.restype = C.c_int32
        lib.dcamapi_uninit.argtypes = []
        lib.dcamapi_uninit.restype = C.c_int32

        lib.dcamdev_open.argtypes = [C.POINTER(DCAMDEV_OPEN)]
        lib.dcamdev_open.restype = C.c_int32
        lib.dcamdev_close.argtypes = [HDCAM]
        lib.dcamdev_close.restype = C.c_int32

        lib.dcamprop_getvalue.argtypes = [HDCAM, int32, C.POINTER(C.c_double)]
        lib.dcamprop_getvalue.restype = C.c_int32
        lib.dcamprop_setvalue.argtypes = [HDCAM, int32, C.c_double]
        lib.dcamprop_setvalue.restype = C.c_int32

        lib.dcambuf_alloc.argtypes = [HDCAM, int32]
        lib.dcambuf_alloc.restype = C.c_int32
        lib.dcambuf_release.argtypes = [HDCAM, int32]
        lib.dcambuf_release.restype = C.c_int32

        lib.dcamcap_start.argtypes = [HDCAM, int32]
        lib.dcamcap_start.restype = C.c_int32
        lib.dcamcap_stop.argtypes = [HDCAM]
        lib.dcamcap_stop.restype = C.c_int32

        lib.dcamwait_open.argtypes = [C.POINTER(DCAMWAIT_OPEN)]
        lib.dcamwait_open.restype = C.c_int32
        lib.dcamwait_close.argtypes = [HDCAMWAIT]
        lib.dcamwait_close.restype = C.c_int32
        lib.dcamwait_start.argtypes = [HDCAMWAIT, C.POINTER(DCAMWAIT_START)]
        lib.dcamwait_start.restype = C.c_int32
        lib.dcamwait_abort.argtypes = [HDCAMWAIT]
        lib.dcamwait_abort.restype = C.c_int32

        lib.dcambuf_lockframe.argtypes = [HDCAM, C.POINTER(DCAMBUF_FRAME)]
        lib.dcambuf_lockframe.restype = C.c_int32

    # -- lifecycle -------------------------------------------------------

    def open(self):
        init = DCAMAPI_INIT(size=C.sizeof(DCAMAPI_INIT))
        _check(self.lib.dcamapi_init(C.byref(init)), "dcamapi_init")
        if init.iDeviceCount <= 0:
            raise DCAMError(
                "dcamapi_init succeeded but found 0 cameras — check the camera is "
                "powered, cabled, and visible (e.g. `lsusb` for a USB3 model), and "
                "that this process has permission to access it."
            )

        devopen = DCAMDEV_OPEN(size=C.sizeof(DCAMDEV_OPEN), index=self.index)
        _check(self.lib.dcamdev_open(C.byref(devopen)), "dcamdev_open")
        self.hdcam = devopen.hdcam

        waitopen = DCAMWAIT_OPEN(size=C.sizeof(DCAMWAIT_OPEN), hdcam=self.hdcam)
        _check(self.lib.dcamwait_open(C.byref(waitopen)), "dcamwait_open")
        self.hwait = waitopen.hwait
        return self

    def abort_wait(self):
        """Unblock a thread sitting in get_frame()/dcamwait_start immediately.

        Safe to call from another thread (that is the point). No-op if the wait
        handle is already gone."""
        h = self.hwait
        if h:
            try:
                self.lib.dcamwait_abort(h)
            except Exception:
                pass

    def close(self):
        """Full, ordered teardown. Idempotent and best-effort: every step is
        attempted even if an earlier one fails, so a half-open camera (e.g. a
        SIGINT during open()) is still released and dcamapi_uninit() still runs.
        """
        # 1. make sure nothing is still blocked waiting for a frame
        self.abort_wait()

        # 2. stop the capture / free the ring buffers
        if self._streaming:
            try:
                self.stop()
            except Exception as e:
                print(f"[dcam] stop during close failed: {e}")
            self._streaming = False

        # 3. close the wait handle
        if self.hwait:
            try:
                self.lib.dcamwait_close(self.hwait)
            except Exception as e:
                print(f"[dcam] dcamwait_close failed: {e}")
            self.hwait = None

        # 4. close the device handle
        if self.hdcam:
            try:
                self.lib.dcamdev_close(self.hdcam)
            except Exception as e:
                print(f"[dcam] dcamdev_close failed: {e}")
            self.hdcam = None

        # 5. release the API / USB interface
        try:
            self.lib.dcamapi_uninit()
        except Exception as e:
            print(f"[dcam] dcamapi_uninit failed: {e}")

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # -- properties --------------------------------------------------------

    def set_exposure(self, seconds):
        _check(
            self.lib.dcamprop_setvalue(self.hdcam, DCAM_IDPROP_EXPOSURETIME, C.c_double(seconds)),
            "set exposure time",
        )

    def get_exposure(self):
        val = C.c_double()
        _check(
            self.lib.dcamprop_getvalue(self.hdcam, DCAM_IDPROP_EXPOSURETIME, C.byref(val)),
            "get exposure time",
        )
        return val.value

    def get_property(self, prop_id):
        val = C.c_double()
        _check(self.lib.dcamprop_getvalue(self.hdcam, prop_id, C.byref(val)), f"get property 0x{prop_id:08X}")
        return val.value

    def set_property(self, prop_id, value):
        _check(self.lib.dcamprop_setvalue(self.hdcam, prop_id, C.c_double(value)), f"set property 0x{prop_id:08X}")

    def try_get_property(self, prop_id):
        """get_property but returns None instead of raising if unsupported."""
        try:
            return self.get_property(prop_id)
        except DCAMError:
            return None

    def get_property_range(self, prop_id):
        """Return (valuemin, valuemax, valuestep) for a property, via
        dcamprop_getattr. Raises DCAMError if the property is not supported."""
        attr = DCAMPROP_ATTR(cbSize=C.sizeof(DCAMPROP_ATTR), iProp=int32(prop_id))
        self.lib.dcamprop_getattr.argtypes = [HDCAM, C.POINTER(DCAMPROP_ATTR)]
        self.lib.dcamprop_getattr.restype = C.c_int32
        _check(self.lib.dcamprop_getattr(self.hdcam, C.byref(attr)),
               f"get attr 0x{prop_id:08X}")
        return attr.valuemin, attr.valuemax, attr.valuestep

    # -- readout speed ---------------------------------------------------

    def set_readout_speed(self, value):
        """Set READOUTSPEED (integer enum). Raises DCAMError if unsupported."""
        self.set_property(DCAM_IDPROP_READOUTSPEED, float(int(value)))

    def get_readout_speed(self):
        return self.get_property(DCAM_IDPROP_READOUTSPEED)

    # -- streaming -----------------------------------------------------------

    def start(self, nbuf=10):
        """Allocate `nbuf` ring buffers and start continuous (sequence) capture."""
        _check(self.lib.dcambuf_alloc(self.hdcam, int32(nbuf)), "dcambuf_alloc")
        _check(self.lib.dcamcap_start(self.hdcam, DCAMCAP_START_SEQUENCE), "dcamcap_start")
        self._streaming = True

    def stop(self):
        if not self.hdcam:
            self._streaming = False
            return
        try:
            self.lib.dcamcap_stop(self.hdcam)
        finally:
            self.lib.dcambuf_release(self.hdcam, 0)
            self._streaming = False

    def get_frame(self, timeout_ms=5000):
        """Block until the next frame is ready and return it as a numpy array
        (uint16 for MONO16 sensors, uint8 for MONO8), shape (height, width)."""
        wait = DCAMWAIT_START(
            size=C.sizeof(DCAMWAIT_START),
            eventmask=DCAMWAIT_CAPEVENT_FRAMEREADY,
            timeout=timeout_ms,
        )
        _check(self.lib.dcamwait_start(self.hwait, C.byref(wait)), "dcamwait_start")

        frame = DCAMBUF_FRAME(size=C.sizeof(DCAMBUF_FRAME), iFrame=-1)  # -1 = most recent frame
        _check(self.lib.dcambuf_lockframe(self.hdcam, C.byref(frame)), "dcambuf_lockframe")

        if frame.type == DCAM_PIXELTYPE_MONO16:
            dtype = np.uint16
        elif frame.type == DCAM_PIXELTYPE_MONO8:
            dtype = np.uint8
        else:
            raise DCAMError(f"Unsupported pixel type 0x{frame.type:X} — extend get_frame() to handle it")

        itemsize = np.dtype(dtype).itemsize
        height, width, rowbytes = frame.height, frame.width, frame.rowbytes
        if not frame.buf:
            raise DCAMError("dcambuf_lockframe returned a null buffer pointer")

        # frame.buf is a plain integer address (ctypes auto-converts a c_void_p field
        # to int/None on read). It points into the driver's own ring buffer, so copy
        # the data out immediately — it will be overwritten by the next frame.
        raw = (C.c_uint8 * (rowbytes * height)).from_address(frame.buf)
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(height, rowbytes)
        arr = arr[:, : width * itemsize].view(dtype).reshape(height, width)
        return arr.copy()
