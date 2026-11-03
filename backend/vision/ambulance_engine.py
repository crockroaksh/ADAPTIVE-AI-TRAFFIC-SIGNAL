"""
Ambulance detector.

The supplied checkpoint (models/ambulance_best.pt) is a standard Ultralytics
YOLOv8n DetectionModel (trained with ultralytics 8.4.x, imgsz 640). It loads
directly with ``YOLO(path)``. It is a 6-class model, NOT single-class:

    0: Auto   1: Bus   2: Car   3: Rikshaw   4: Truck   5: ambulance

so only detections whose class NAME is "ambulance" count. The class id is
resolved from ``model.names`` at load time (never hard-coded), and loading
fails loudly if no such class exists.

The model is loaded once; ``detect_batch`` runs all lane frames in one call.
"""
import os
import threading
import time
from pathlib import Path

import numpy as np

from .yolo_engine import DEVICE  # reuse CUDA > MPS > CPU selection

BACKEND_DIR = Path(__file__).resolve().parent.parent
AMBULANCE_MODEL = os.getenv("AMBULANCE_MODEL", "models/ambulance_best.pt")
AMBULANCE_CONFIDENCE = float(os.getenv("AMBULANCE_CONFIDENCE", "0.50"))
AMBULANCE_IMGSZ = int(os.getenv("AMBULANCE_IMGSZ", "640"))
AMBULANCE_CLASS_NAME = os.getenv("AMBULANCE_CLASS_NAME", "ambulance").lower()


def _resolve(path_str):
    p = Path(path_str)
    return p if p.is_absolute() else BACKEND_DIR / p


class AmbulanceEngine:
    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        from ultralytics import YOLO
        path = _resolve(AMBULANCE_MODEL)
        if not path.exists():
            raise FileNotFoundError(
                f"Ambulance model not found at {path}. Place your trained weights there "
                f"or set AMBULANCE_MODEL (relative to backend/ or absolute).")
        print(f"[AMBULANCE] Loading {path} on {DEVICE}...")
        self.model = YOLO(str(path))
        self.device = DEVICE
        self.names = dict(self.model.names)
        self.class_ids = [i for i, n in self.names.items() if str(n).lower() == AMBULANCE_CLASS_NAME]
        if not self.class_ids:
            raise RuntimeError(
                f"Model classes {self.names} contain no '{AMBULANCE_CLASS_NAME}' class "
                f"(set AMBULANCE_CLASS_NAME if your label differs).")
        self.conf = AMBULANCE_CONFIDENCE
        self.lock = threading.Lock()
        print(f"[AMBULANCE] classes={self.names} using ids={self.class_ids} conf>={self.conf}")
        try:
            t = time.time()
            self.model.predict(np.zeros((640, 640, 3), np.uint8), device=self.device, verbose=False)
            print(f"[AMBULANCE] Warm-up complete in {time.time()-t:.2f}s")
        except Exception as e:
            if self.device != "cpu":
                print(f"[AMBULANCE] Warm-up failed on {self.device} ({e}); falling back to CPU")
                self.device = "cpu"

    def detect_batch(self, frames):
        """frames: list of BGR ndarrays -> list of lists of
        {"box":[x1,y1,x2,y2], "confidence":float} (ambulance class only)."""
        if not frames:
            return []
        with self.lock:
            results = self.model.predict(frames, device=self.device, conf=self.conf,
                                         imgsz=AMBULANCE_IMGSZ, verbose=False)
        out = []
        for r in results:
            dets = []
            if r.boxes is not None and len(r.boxes):
                for x1, y1, x2, y2, c, k in r.boxes.data.cpu().numpy():
                    if int(k) in self.class_ids:
                        dets.append({"box": [float(x1), float(y1), float(x2), float(y2)], "confidence": float(c)})
            out.append(dets)
        return out
