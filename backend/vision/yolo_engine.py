import os
import time
import numpy as np
import torch
from ultralytics import YOLO

MODEL_NAME = os.getenv("YOLO_MODEL", "yolov8n.pt")

# Device priority: CUDA (NVIDIA) > MPS (Apple Silicon GPU) > CPU.
# Without this, torch.cuda.is_available() is always False on a Mac, so an
# M1/M2/M3 machine would silently fall through to CPU-only inference even
# though its GPU (MPS) is available and often meaningfully faster.
if torch.cuda.is_available():
    DEVICE = "cuda:0"
elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
    DEVICE = "mps"
else:
    DEVICE = "cpu"

CONF = float(os.getenv("YOLO_CONFIDENCE", "0.30"))

print(f"[YOLO] Loading {MODEL_NAME} on {DEVICE}...")
model = YOLO(MODEL_NAME)
try:
    t = time.time()
    model.predict(np.zeros((640, 640, 3), dtype=np.uint8), device=DEVICE, conf=CONF, verbose=False)
    print(f"[YOLO] Warm-up complete in {time.time()-t:.2f}s on {DEVICE}")
except Exception as e:
    # MPS in particular has had intermittent op-support gaps in some
    # PyTorch/Ultralytics version combinations. If the device we picked
    # can't actually run inference, fall back to CPU rather than leaving
    # DEVICE set to something that will fail on every real request too.
    if DEVICE != "cpu":
        print(f"[YOLO] Warm-up failed on {DEVICE} ({e}); falling back to CPU.")
        DEVICE = "cpu"
        try:
            t = time.time()
            model.predict(np.zeros((640, 640, 3), dtype=np.uint8), device=DEVICE, conf=CONF, verbose=False)
            print(f"[YOLO] Warm-up complete in {time.time()-t:.2f}s on {DEVICE}")
        except Exception as e2:
            print(f"[YOLO] Warm-up warning (CPU fallback also failed): {e2}")
    else:
        print(f"[YOLO] Warm-up warning: {e}")

VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

def detect(frame, imgsz=None):
    kwargs = {"device": DEVICE, "conf": CONF, "verbose": False}
    if imgsz:
        kwargs["imgsz"] = imgsz
    result = model.predict(frame, **kwargs)[0]
    return result.boxes.data.cpu().numpy() if result.boxes is not None else np.empty((0, 6))
