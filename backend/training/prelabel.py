"""Pre-label frames with the stock COCO YOLO to save labeling time.

It writes YOLO-format .txt files with ONE class per vehicle type. You must then
open them in a labeling tool and DELETE every box on a vehicle that is not
front-facing (rear / side-on / driving away). The stock model cannot tell front
from rear, so this is only a head start, not the final labels.

    python training/prelabel.py --images dataset/raw --out dataset/labels_draft
Classes written: 0 car_front, 1 motorcycle_front, 2 bus_front, 3 truck_front
"""
import argparse, os
from ultralytics import YOLO

ap = argparse.ArgumentParser()
ap.add_argument("--images", required=True); ap.add_argument("--out", default="dataset/labels_draft")
ap.add_argument("--conf", type=float, default=0.30)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
COCO_TO_OURS = {2: 0, 3: 1, 5: 2, 7: 3}
model = YOLO("yolov8s.pt")
for r in model.predict(a.images, conf=a.conf, stream=True, verbose=False):
    lines = []
    h, w = r.orig_shape
    for x1, y1, x2, y2, c, k in r.boxes.data.cpu().numpy():
        if int(k) in COCO_TO_OURS:
            cx, cy, bw, bh = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h, (x2 - x1) / w, (y2 - y1) / h
            lines.append(f"{COCO_TO_OURS[int(k)]} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    open(os.path.join(a.out, os.path.splitext(os.path.basename(r.path))[0] + ".txt"), "w").write("\n".join(lines))
print("done. Now review/edit the labels and remove non-front-facing vehicles.")
