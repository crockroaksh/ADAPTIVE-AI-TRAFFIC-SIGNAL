"""Extract frames from your lane videos for labeling.

    python training/extract_frames.py --videos path/to/videos --out dataset/raw --every 1.0
"""
import argparse, os, cv2

ap = argparse.ArgumentParser()
ap.add_argument("--videos", required=True, help="folder containing .mp4/.avi/.mov files")
ap.add_argument("--out", default="dataset/raw")
ap.add_argument("--every", type=float, default=1.0, help="seconds between saved frames")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
n = 0
for f in sorted(os.listdir(a.videos)):
    if not f.lower().endswith((".mp4", ".avi", ".mov", ".mkv")): continue
    cap = cv2.VideoCapture(os.path.join(a.videos, f))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = max(1, int(round(fps * a.every)))
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok: break
        if i % step == 0:
            cv2.imwrite(os.path.join(a.out, f"{os.path.splitext(f)[0]}_{i:06d}.jpg"), frame); n += 1
        i += 1
    cap.release()
print(f"saved {n} frames to {a.out}")
