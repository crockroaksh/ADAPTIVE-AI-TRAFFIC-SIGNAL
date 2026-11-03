"""Split reviewed images+labels into train/val (80/20).

    python training/split_dataset.py --images dataset/raw --labels dataset/labels_draft --out dataset
"""
import argparse, os, random, shutil
ap = argparse.ArgumentParser()
ap.add_argument("--images", required=True); ap.add_argument("--labels", required=True)
ap.add_argument("--out", default="dataset"); ap.add_argument("--val", type=float, default=0.2)
a = ap.parse_args(); random.seed(0)
imgs = sorted(f for f in os.listdir(a.images) if f.lower().endswith((".jpg", ".png")))
random.shuffle(imgs); nv = max(1, int(len(imgs) * a.val))
for i, f in enumerate(imgs):
    sp = "val" if i < nv else "train"
    for sub in ("images", "labels"): os.makedirs(os.path.join(a.out, sub, sp), exist_ok=True)
    shutil.copy(os.path.join(a.images, f), os.path.join(a.out, "images", sp, f))
    lab = os.path.join(a.labels, os.path.splitext(f)[0] + ".txt")
    dst = os.path.join(a.out, "labels", sp, os.path.splitext(f)[0] + ".txt")
    shutil.copy(lab, dst) if os.path.exists(lab) else open(dst, "w").close()
print(f"{len(imgs)-nv} train / {nv} val")
