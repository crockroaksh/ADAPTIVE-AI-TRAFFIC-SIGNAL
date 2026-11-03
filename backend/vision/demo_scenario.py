"""Deterministic 60-second demo scenario used only by the supplied demo_*.mp4 clips.

Real user uploads still go through YOLO.  The scripted mode exists so a classroom/project
presentation can have video motion, ambulance priority, and signal outputs that are
perfectly synchronized second-by-second.
"""
from pathlib import Path

LANES = ["North", "South", "East", "West"]
DURATION_SECONDS = 60
SEGMENT_SECONDS = 1.0


def is_demo_upload(filenames):
    if not filenames:
        return False
    provided = {k: (v or "").lower() for k, v in filenames.items()}
    return bool(provided) and all(name.startswith("demo_") for name in provided.values())


def signal_at(t):
    """Exact signal plan for the demo. East is GREEN for 20 seconds (19..38 inclusive)."""
    t = int(t)
    sig = {lane: "RED" for lane in LANES}
    phase = "GREEN"
    selected = "North"
    transition_from = None
    transition_target = None
    reason = "continue_green"

    if 0 <= t <= 14:
        sig["North"] = "GREEN"; selected = "North"
        reason = "initial" if t == 0 else "continue_green"
    elif 15 <= t <= 17:
        sig["North"] = "YELLOW"; phase = "YELLOW"; selected = "East"
        transition_from, transition_target, reason = "North", "East", "ambulance_priority"
    elif t == 18:
        phase = "ALL_RED"; selected = "East"
        transition_from, transition_target, reason = "North", "East", "ambulance_priority"
    elif 19 <= t <= 38:
        sig["East"] = "GREEN"; selected = "East"; reason = "ambulance_priority" if t <= 30 else "continue_green"
    elif 39 <= t <= 41:
        sig["East"] = "YELLOW"; phase = "YELLOW"; selected = "South"
        transition_from, transition_target, reason = "East", "South", "traffic_cleared"
    elif t == 42:
        phase = "ALL_RED"; selected = "South"
        transition_from, transition_target, reason = "East", "South", "traffic_cleared"
    elif 43 <= t <= 54:
        sig["South"] = "GREEN"; selected = "South"; reason = "continue_green"
    elif 55 <= t <= 57:
        sig["South"] = "YELLOW"; phase = "YELLOW"; selected = "West"
        transition_from, transition_target, reason = "South", "West", "max_green_exceeded"
    elif t == 58:
        phase = "ALL_RED"; selected = "West"
        transition_from, transition_target, reason = "South", "West", "max_green_exceeded"
    else:
        sig["West"] = "GREEN"; selected = "West"; reason = "continue_green"

    return sig, {
        "selected_lane": selected,
        "green_elapsed_seconds": _green_elapsed(t),
        "reason": reason,
        "min_green_seconds": 15,
        "max_green_seconds": 60,
        "max_wait_seconds": 90,
        "clear_threshold_vehicles": 2,
        "consecutive_clear_required": 2,
        "consecutive_clear_count": 0,
        "emergency_active": 16 <= t <= 30,
        "emergency_lane": "East" if 16 <= t <= 30 else None,
        "transition_state": phase,
        "transition_from": transition_from,
        "transition_target": transition_target,
        "demo_mode": True,
    }


def _green_elapsed(t):
    if 0 <= t <= 14: return float(t)
    if 19 <= t <= 38: return float(t - 19)
    if 43 <= t <= 54: return float(t - 43)
    if t >= 59: return float(t - 59)
    return 0.0


def counts_at(t):
    """Visible approaching/queued vehicles per lane; values mirror the generated clips."""
    t = int(t)
    # North starts busiest, drains while green, then slowly rebuilds.
    north = max(1, 9 - t // 2) if t <= 14 else min(6, 2 + (t - 15) // 10)
    # East builds a queue before emergency green, includes ambulance, then drains.
    if t < 8: east = 3
    elif t < 19: east = min(10, 4 + (t - 8) // 2)
    elif t <= 38: east = max(1, 10 - (t - 19) // 2)
    else: east = min(5, 1 + (t - 39) // 8)
    # South becomes the next busiest after East clears.
    south = min(9, 2 + t // 7) if t < 43 else max(2, 9 - (t - 43) // 2)
    # West stays moderate and gets the final green.
    west = min(7, 2 + t // 12) if t < 59 else 5
    return {"North": int(north), "South": int(south), "East": int(east), "West": int(west)}


def ambulance_at(t, lane):
    # Raw visibility begins at 15s; confirmation shown from 16s through 30s.
    if lane != "East":
        return False, False, 0.0
    raw = 15 <= int(t) <= 28
    confirmed = 16 <= int(t) <= 30
    conf = 0.94 if raw else 0.0
    return raw, confirmed, conf


def build_decision(t):
    sig, controller = signal_at(t)
    counts = counts_at(t)
    out = {}
    for lane in LANES:
        raw, confirmed, conf = ambulance_at(t, lane)
        out[lane] = {
            "signal": sig[lane],
            "vehicle_count": counts[lane],
            "waiting_time_seconds": 0.0 if sig[lane] == "GREEN" else float(t),
            "ambulance_detected": confirmed,
            "ambulance_raw_detected": raw,
            "ambulance_confidence": conf,
        }
    out["_controller"] = controller
    return out


def process_demo_videos(video_paths, publish=None, esp32_push=None):
    timeline = []
    totals = {lane: 0 for lane in LANES}
    for t in range(DURATION_SECONDS):
        decisions = build_decision(t)
        counts = {lane: decisions[lane]["vehicle_count"] for lane in LANES}
        for lane in LANES:
            totals[lane] += counts[lane]
        event = {
            "type": "decision",
            "decisions": decisions,
            "lane_counts": counts,
            "raw_yolo_detections": dict(counts),
            "segment_index": "instant" if t == 0 else t - 1,
            "processing_elapsed_seconds": 0.0,
            "demo_mode": True,
        }
        timeline.append(event)
        if publish:
            publish(event)
        if esp32_push:
            try:
                event["esp32_push"] = esp32_push(decisions)
            except Exception as exc:
                event["esp32_push"] = {"status": "failed", "error": str(exc)}

    final = timeline[-1]["decisions"]
    return {
        "lane_counts": totals,
        "raw_yolo_detections": dict(totals),
        "signal_decisions": final,
        "segment_decisions": timeline,
        "frame_data": [
            {"frame": i, "time_sec": i, **e["lane_counts"], "total": sum(e["lane_counts"].values())}
            for i, e in enumerate(timeline)
        ],
        "processed_video_urls": {},
        "processed_video_url": "",
        "total_vehicles": sum(totals.values()),
        "segment_seconds": SEGMENT_SECONDS,
        "lanes_processed": [l for l in LANES if video_paths.get(l)],
        "processing_time_seconds": 0.0,
        "demo_mode": True,
        "demo_note": "Scripted synchronized demo metadata; real uploads use YOLO.",
    }
