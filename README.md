# TRAFFIC--main — Real-Time Adaptive Traffic Signal AI

This version runs YOLOv8 locally from the FastAPI backend. Colab/ngrok is no longer part of the live processing path. Uploaded videos simulate live traffic cameras: the browser plays them immediately while the backend processes frames in the background and streams signal decisions over SSE.

## Architecture

Browser video + upload → FastAPI session → local YOLOv8 → SignalController → SSE → React + ESP32

## Backend

1. Create a Python virtual environment.
2. Install the requirements.
3. Install a PyTorch build appropriate for your machine. For an NVIDIA GPU, use the official CUDA-enabled PyTorch wheel matching your driver.
4. Copy `backend/.env.example` to `backend/.env` and fill in ESP32/Supabase values if needed.
5. From `backend/`: `uvicorn main:app --reload --host 0.0.0.0 --port 8000`

Check `http://localhost:8000/gpu-status`. An RTX 3050 should report `cuda:0` when the installed PyTorch build has CUDA support.

## Frontend

From `frontend/`: `npm install` then `npm run dev`. Copy `.env.example` to `.env` if needed; local development uses `VITE_API_URL=http://localhost:8000`.

## Live behavior

The upload endpoint returns a session as soon as the files are saved. The frontend immediately plays the selected local files using `URL.createObjectURL`. The backend runs YOLO in a background thread and emits multiple `decision` SSE events while the videos are being processed.

The first decision is intentionally produced from one sampled frame per uploaded lane, in one batched YOLO inference, to minimize initial latency. Subsequent updates use approximately `AI_FPS` samples per second and `SEGMENT_SECONDS` of source-video progression.

## Signal controller

The controller keeps the existing rules:
- starvation relief
- minimum green time
- early switch when the green lane is effectively clear (`CLEAR_THRESHOLD_VEHICLES`)
- maximum green safety cap

## Random test videos

Random road videos are useful for testing YOLO and the live pipeline, but they are not meaningful four-way intersection footage. The multi-lane UI assumes each uploaded file is the camera for its named approach. Use actual North/South/East/West approach-camera footage to validate lane-level traffic control.

## Secrets

The distributed project intentionally contains placeholders instead of real API keys, ngrok tokens, or Wi-Fi passwords. Restore your own local values in `.env` and the ESP32 sketch before deployment.


---

# Ambulance priority

## The ambulance model (inspected, not assumed)
`backend/models/ambulance_best.pt` is a standard Ultralytics YOLOv8n detection checkpoint (trained with ultralytics 8.4.x, imgsz 640) and loads with `YOLO(path)`. It has **six classes**: `0 Auto, 1 Bus, 2 Car, 3 Rikshaw, 4 Truck, 5 ambulance`. Only the class named `ambulance` triggers emergency logic; the id is resolved from `model.names` at load. Default confidence 0.50 (`AMBULANCE_CONFIDENCE`; try 0.35 if it misses ambulances in your clips).

## Controller behaviour
Priority: 0 ambulance → 1 starvation → 2 traffic cleared → 3 max green → continue. Every change of green goes through YELLOW (`YELLOW_SECONDS`) → ALL RED (`ALL_RED_SECONDS`) → GREEN. Emergency is held until the ambulance has been unseen for `EMERGENCY_LOST_TIMEOUT_SECONDS` (after `EMERGENCY_MIN_GREEN_SECONDS`), with a hard cap `EMERGENCY_MAX_GREEN_SECONDS` and a cooldown after release. Multiple ambulances: the active emergency lane keeps priority; otherwise earliest confirmation wins, then confidence, then waiting time, then lane order. Extra output fields: `ambulance_detected`, `ambulance_raw_detected`, `ambulance_confidence` per lane; `emergency_active`, `emergency_lane`, `transition_state` in `_controller`.

Run the controller tests (no GPU needed): `cd backend && python -m pytest tests -q`.

## Uploaded Videos mode now includes ambulance priority
The ambulance model runs on the sampled frames of each lane video; an ambulance seen in 2 of the last 3 one-second segments triggers emergency priority (yellow → all-red → green, held until it disappears). If the model can't load, the mode still works without emergency detection and logs a warning. Disable with `UPLOAD_AMBULANCE_ENABLED=false`. For a demo, upload a clip that contains an ambulance in one lane.

## Synchronized playback (signal timing matches the video)
On the Live page the four uploaded videos play from one shared clock, and every signal light, vehicle count and ambulance status shown is the controller's decision for the *current video time* (a decision made after watching second N takes effect at second N+1; the first "instant" decision applies at t=0). If playback gets ahead of the AI, all four videos pause automatically ("waiting for AI…") and resume when the analysis catches up. A signal timeline under the videos shows each lane's red/yellow/green history and where ambulance priority was confirmed; click it to seek. Use four videos of equal length for the cleanest alignment — shorter ones freeze on their last frame.

## Synchronized 60-second presentation demo

A deterministic four-lane demo is included in `demo_videos/`. Run `python demo_videos/generate_demo_videos.py` to regenerate the MP4s, then upload `demo_north.mp4`, `demo_south.mp4`, `demo_east.mp4`, and `demo_west.mp4` to their matching lanes.

The bundled clips show incoming/front-facing traffic only. The East clip contains an ambulance. For these `demo_*.mp4` files only, the backend uses `backend/vision/demo_scenario.py` so the visual traffic, ambulance state, vehicle counts, and signal timeline remain exactly synchronized. East is green from t=19s through t=38s (20 seconds). Normal uploaded videos continue to use YOLO and the adaptive `SignalController` unchanged.
