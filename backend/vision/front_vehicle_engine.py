"""
Front-facing vehicle counter (optional).

Counts only vehicles whose FRONT is visible to the camera, i.e. traffic that is
approaching the stop line. Vehicles driving away show their rear and are not
detected, so they never inflate a lane's count.

This needs a model YOU train (see backend/training/README.md). Enable it by
pointing FRONT_VEHICLE_MODEL at the weights, e.g.

    FRONT_VEHICLE_MODEL=models/front_vehicles.pt

If the variable is unset, the original COCO vehicle detector is used unchanged.
If it is set but the file is missing/unloadable, the app logs a warning and falls
back to the original detector rather than failing.

Every class in the model is treated as "a vehicle front" unless
FRONT_VEHICLE_CLASSES (comma-separated names) is set.
"""
import os
import threading
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONT_CONF = float(os.getenv("FRONT_VEHICLE_CONFIDENCE", "0.40"))
FRONT_IMGSZ = int(os.getenv("FRONT_VEHICLE_IMGSZ", "640"))


class FrontVehicleEngine:
    def __init__(self, path):
        from ultralytics import YOLO
        from .yolo_engine import DEVICE
        self.device = DEVICE
        self.model = YOLO(str(path))
        names = dict(self.model.names)
        wanted = [c.strip().lower() for c in os.getenv("FRONT_VEHICLE_CLASSES", "").split(",") if c.strip()]
        self.class_ids = [i for i, n in names.items() if not wanted or str(n).lower() in wanted]
        if not self.class_ids:
            raise RuntimeError(f"No classes of {names} match FRONT_VEHICLE_CLASSES={wanted}")
        self.lock = threading.Lock()
        print(f"[FRONT] Loaded {path} on {self.device}; classes counted: {[names[i] for i in self.class_ids]} conf>={FRONT_CONF}")

    def detect_batch(self, frames, imgsz=None):
        """-> list of (N,6) arrays [x1,y1,x2,y2,conf,cls], filtered to counted classes."""
        with self.lock:
            results = self.model.predict(frames, device=self.device, conf=FRONT_CONF,
                                         imgsz=imgsz or FRONT_IMGSZ, verbose=False)
        out = []
        for r in results:
            d = r.boxes.data.cpu().numpy() if r.boxes is not None else np.empty((0, 6))
            out.append(d[np.isin(d[:, 5].astype(int), self.class_ids)] if len(d) else d)
        return out

    def detect(self, frame):
        return self.detect_batch([frame])[0]


_ENGINE = None
_TRIED = False


def get_front_engine():
    """Shared instance, or None when not configured / not loadable."""
    global _ENGINE, _TRIED
    if _TRIED:
        return _ENGINE
    _TRIED = True
    spec = os.getenv("FRONT_VEHICLE_MODEL", "").strip()
    if not spec:
        return None
    p = Path(spec)
    p = p if p.is_absolute() else BACKEND_DIR / p
    if not p.exists():
        print(f"[FRONT][WARN] FRONT_VEHICLE_MODEL not found at {p}; using the original vehicle detector")
        return None
    try:
        _ENGINE = FrontVehicleEngine(p)
    except Exception as e:
        print(f"[FRONT][WARN] could not load front-vehicle model ({e}); using the original vehicle detector")
    return _ENGINE
