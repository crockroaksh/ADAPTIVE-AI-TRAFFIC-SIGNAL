# Training a front-facing vehicle detector

Goal: count only vehicles whose FRONT faces the camera (approaching the stop line).
Vehicles driving away show their rear and are not detected, so they don't inflate the count.

Run these on a machine with a GPU (free Google Colab T4 is enough; ~30–60 min training).

## 1. Get footage (varied!)
Use real Indian junction footage plus your AI-generated clips. Include day/dusk, light/heavy traffic,
rain/haze if possible. Diversity matters more than quantity. Keep the AI-generated clips to a minority:
a model trained only on generated video may not transfer to real cameras.

## 2. Extract frames (about 1 frame per second)
    python training/extract_frames.py --videos my_videos --out dataset/raw --every 1.0
Aim for roughly 800–1500 frames. Nearby frames are very similar, so use several different videos.

## 3. Pre-label with the stock model (saves time)
    python training/prelabel.py --images dataset/raw --out dataset/labels_draft

## 4. Review labels in a tool (CVAT, Label Studio or Roboflow; import the YOLO txt files)
Classes: 0 car_front, 1 motorcycle_front, 2 bus_front, 3 truck_front
(auto-rickshaws: label as car_front, or add a class and edit `names` in train_front_vehicles.py).

Rules — apply them consistently:
- KEEP a box only if the vehicle is **approaching**: you can see its front (headlight/grille/windscreen;
  for a motorcycle, the headlight and the rider facing you).
- DELETE boxes on vehicles driving away (rear visible), side-on/crossing, or too tiny to tell.
- Partly hidden vehicles: keep if you'd judge the front is ≥ ~40% visible.
- Box the whole vehicle tightly.
- Keep frames that contain only rear-facing traffic as **negatives** with an empty label file.
  They are essential: they teach the model to ignore rears.
- The prelabel step cannot tell front from rear — you must do this review.

## 5. Split and train
    python training/split_dataset.py --images dataset/raw --labels dataset/labels_draft --out dataset
    python training/train_front_vehicles.py --data dataset --epochs 60
Check `runs/detect/front_vehicles/results.png` and the validation predictions: rears should NOT be detected.

## 6. Use it
Copy `runs/detect/front_vehicles/weights/best.pt` to `backend/models/front_vehicles.pt`, then in `backend/.env`:
    FRONT_VEHICLE_MODEL=models/front_vehicles.pt
    FRONT_VEHICLE_CONFIDENCE=0.40
Restart the backend. The log shows `[FRONT] Loaded ... classes counted: [...]`.
If the file is missing or fails to load, the app logs a warning and falls back to the original detector.

Notes: this applies to Uploaded Videos mode. Make a validation set from *different* videos than you trained
on, otherwise the accuracy you see will be overstated.
