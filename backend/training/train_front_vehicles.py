"""Train the front-facing vehicle detector.

Expected folder layout (YOLO format) after you finish labeling:

    dataset/
      images/train/*.jpg   images/val/*.jpg
      labels/train/*.txt   labels/val/*.txt

An image with NO vehicle fronts (e.g. only vehicles driving away) should have an
EMPTY .txt file (or none): those "negative" images teach the model to ignore rears.

    python training/train_front_vehicles.py --data dataset --epochs 60
Result: runs/detect/front_vehicles/weights/best.pt -> copy to backend/models/front_vehicles.pt
"""
import argparse, os, yaml
from ultralytics import YOLO

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="dataset"); ap.add_argument("--epochs", type=int, default=60)
ap.add_argument("--imgsz", type=int, default=640); ap.add_argument("--base", default="yolov8s.pt")
ap.add_argument("--batch", type=int, default=16)
a = ap.parse_args()
root = os.path.abspath(a.data)
cfg = {"path": root, "train": "images/train", "val": "images/val",
       "names": {0: "car_front", 1: "motorcycle_front", 2: "bus_front", 3: "truck_front"}}
with open(os.path.join(root, "data.yaml"), "w") as f: yaml.safe_dump(cfg, f)
YOLO(a.base).train(data=os.path.join(root, "data.yaml"), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch,
                   name="front_vehicles", patience=20, degrees=0, flipud=0.0, fliplr=0.5)
