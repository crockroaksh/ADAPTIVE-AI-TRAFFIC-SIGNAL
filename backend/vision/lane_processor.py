import os
import time
import cv2
from .signal_controller import SignalController, ALL_LANES, VEHICLE_CLASSES, SEGMENT_SECONDS, FIRST_DECISION_IMGSZ, AI_FPS
from .yolo_engine import detect


_FRONT = None


def _front_engine():
    """Optional front-facing counter (counts only approaching vehicles). None = use COCO detector."""
    global _FRONT
    if _FRONT is None:
        try:
            from .front_vehicle_engine import get_front_engine
            _FRONT = get_front_engine() or False
        except Exception as e:
            print(f"[FRONT][WARN] unavailable: {e}")
            _FRONT = False
    return _FRONT or None


def _vehicle_count(dets):
    if _front_engine() is not None:
        return len(dets)   # every detection from the front-facing model is an approaching vehicle
    return sum(1 for d in dets if int(d[5]) in VEHICLE_CLASSES)


def _raw_count(dets):
    return len(dets)


UPLOAD_AMBULANCE_ENABLED = os.environ.get("UPLOAD_AMBULANCE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
# Uploaded-video decisions are ~1 per second, so confirm over fewer calls.
UPLOAD_CONFIRM_FRAMES = int(os.environ.get("UPLOAD_AMBULANCE_CONFIRM_FRAMES", "2"))
UPLOAD_CONFIRM_WINDOW = int(os.environ.get("UPLOAD_AMBULANCE_CONFIRM_WINDOW", "3"))


def _load_ambulance_engine():
    """Returns the shared AmbulanceEngine, or None (with a clear log) if it cannot load.
    Uploaded-video mode keeps working without the ambulance model."""
    if not UPLOAD_AMBULANCE_ENABLED:
        print("[AMBULANCE] disabled for uploaded videos (UPLOAD_AMBULANCE_ENABLED=false)")
        return None
    try:
        from .ambulance_engine import AmbulanceEngine
        return AmbulanceEngine.get()
    except Exception as e:
        print(f"[AMBULANCE][WARN] ambulance model unavailable, continuing without emergency detection: {e}")
        return None


def process_multi_lane_videos(video_paths, publish=None, esp32_push=None, filenames=None):
    # The bundled demo_*.mp4 clips use deterministic metadata so the presentation
    # is exactly synchronized. Every other upload continues through real YOLO.
    from .demo_scenario import is_demo_upload, process_demo_videos
    if is_demo_upload(filenames):
        print("[DEMO] Using scripted synchronized 60-second scenario")
        return process_demo_videos(video_paths, publish=publish, esp32_push=esp32_push)
    lanes = [l for l in ALL_LANES if video_paths.get(l)]
    if not lanes:
        raise ValueError("No lane videos provided")
    caps = {}
    meta = {}
    for lane in lanes:
        cap = cv2.VideoCapture(video_paths[lane])
        if not cap.isOpened():
            raise RuntimeError(f"Could not open {lane} video: {video_paths[lane]}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        print(f"[VIDEO:{lane}] opened=True fps={fps:.2f} frames={frames} duration={(frames/fps if fps else 0):.2f}s size={w}x{h}")
        caps[lane] = cap
        meta[lane] = {"fps": fps, "frames": frames, "w": w, "h": h}

    controller = SignalController(lanes=ALL_LANES,
                                  confirm_frames=UPLOAD_CONFIRM_FRAMES, confirm_window=UPLOAD_CONFIRM_WINDOW)
    amb_engine = _load_ambulance_engine()
    amb_enabled = amb_engine is not None
    first = True
    done = {l: False for l in lanes}
    segment_index = 0
    totals = {l: 0 for l in ALL_LANES}
    raw_totals = {l: 0 for l in ALL_LANES}
    timeline = []
    t0 = time.time()

    def emit(decisions, counts, raw, elapsed, segment_label):
        event = {
            "type": "decision",
            "decisions": decisions,
            "lane_counts": counts,
            "raw_yolo_detections": raw,
            "segment_index": segment_label,
            "processing_elapsed_seconds": round(time.time()-t0, 2),
        }
        timeline.append(event)
        if publish:
            publish(event)
        if esp32_push:
            try:
                event["esp32_push"] = esp32_push(decisions)
            except Exception as e:
                event["esp32_push"] = {"status":"failed","error":str(e)}
        return event

    # Instant decision: one frame per active lane in one batched YOLO call.
    frames, order = [], []
    for lane in lanes:
        ret, frame = caps[lane].read()
        if ret:
            frames.append(frame)
            order.append(lane)
        else:
            done[lane] = True
    if frames:
        front = _front_engine()
        if front is not None:
            results = None
            front_dets = front.detect_batch(frames, imgsz=FIRST_DECISION_IMGSZ)
        else:
            from .yolo_engine import model, DEVICE, CONF
            results = model.predict(frames, device=DEVICE, conf=CONF, imgsz=FIRST_DECISION_IMGSZ, verbose=False)
        counts = {l:0 for l in ALL_LANES}; raw = {l:0 for l in ALL_LANES}
        per_lane = front_dets if results is None else [
            (r.boxes.data.cpu().numpy() if r.boxes is not None else []) for r in results]
        for lane, dets in zip(order, per_lane):
            raw[lane] = _raw_count(dets); counts[lane] = _vehicle_count(dets)
        for l in ALL_LANES:
            totals[l] += counts[l]; raw_totals[l] += raw[l]
        amb = {}
        if amb_enabled:
            try:
                for lane, dets in zip(order, amb_engine.detect_batch(frames)):
                    amb[lane] = {"detected": bool(dets), "confidence": max((d["confidence"] for d in dets), default=0.0)}
            except Exception as e:
                print(f"[AMBULANCE][WARN] inference failed: {e}")
        decisions = controller.decide(counts, 0.0, amb)
        emit(decisions, counts, raw, 0.0, "instant")
        print(f"[AI] instant raw={raw} vehicles={counts} GREEN={decisions['_controller']['selected_lane']}")

    while not all(done.values()):
        seg_seconds = SEGMENT_SECONDS
        counts = {l:0 for l in ALL_LANES}; raw = {l:0 for l in ALL_LANES}
        amb = {l: {"detected": False, "confidence": 0.0} for l in ALL_LANES}
        # Sample approximately AI_FPS frames per second, but always read the
        # whole source segment so playback-time progression is preserved.
        for lane in lanes:
            if done[lane]: continue
            cap = caps[lane]; fps = meta[lane]["fps"]
            frames_to_read = max(1, int(round(fps * seg_seconds)))
            stride = max(1, int(round(fps / max(AI_FPS, 1))))
            for i in range(frames_to_read):
                ret, frame = cap.read()
                if not ret:
                    done[lane] = True
                    break
                if i % stride == 0:
                    _f = _front_engine()
                    dets = _f.detect(frame) if _f is not None else detect(frame)
                    raw[lane] += _raw_count(dets)
                    counts[lane] += _vehicle_count(dets)
                    if amb_enabled:
                        try:
                            a = amb_engine.detect_batch([frame])[0]
                            if a:
                                amb[lane]["detected"] = True
                                amb[lane]["confidence"] = max(amb[lane]["confidence"], max(d["confidence"] for d in a))
                        except Exception as e:
                            print(f"[AMBULANCE][WARN] inference failed: {e}")
        for l in ALL_LANES:
            totals[l] += counts[l]; raw_totals[l] += raw[l]
        decisions = controller.decide(counts, seg_seconds, amb)
        emit(decisions, counts, raw, seg_seconds, segment_index)
        c = decisions["_controller"]
        print(f"[AI] segment={segment_index} raw={raw} vehicles={counts} GREEN={c['selected_lane']} reason={c['reason']} held={c['green_elapsed_seconds']}s")
        segment_index += 1

    for cap in caps.values(): cap.release()
    final = timeline[-1]["decisions"] if timeline else controller.decide({l:0 for l in ALL_LANES}, 0)
    return {
        "lane_counts": totals,
        "raw_yolo_detections": raw_totals,
        "signal_decisions": final,
        "segment_decisions": timeline,
        "frame_data": [{"frame": i, "time_sec": i*SEGMENT_SECONDS, **e["lane_counts"], "total": sum(e["lane_counts"].values())} for i,e in enumerate(timeline)],
        "processed_video_urls": {},
        "processed_video_url": "",
        "total_vehicles": sum(totals.values()),
        "segment_seconds": SEGMENT_SECONDS,
        "lanes_processed": lanes,
        "processing_time_seconds": round(time.time()-t0,2),
    }
