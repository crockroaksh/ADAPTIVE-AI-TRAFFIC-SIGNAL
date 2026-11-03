"""Generate four 60-second MP4 approach-camera demo clips.

All traffic travels toward the camera/stop line only; no outgoing/rear-view stream is drawn.
The movement is synchronized with backend/vision/demo_scenario.py.
"""
from pathlib import Path
import math
import cv2
import numpy as np
import sys

ROOT = Path(__file__).resolve().parents[1]
import importlib.util
_scenario_path = ROOT / 'backend' / 'vision' / 'demo_scenario.py'
_spec = importlib.util.spec_from_file_location('demo_scenario_standalone', _scenario_path)
_scenario = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scenario)
LANES = _scenario.LANES
DURATION_SECONDS = _scenario.DURATION_SECONDS
counts_at = _scenario.counts_at
signal_at = _scenario.signal_at
ambulance_at = _scenario.ambulance_at

W, H = 640, 360
FPS = 10
STOP_Y = 292
ROAD_LEFT, ROAD_RIGHT = 145, 495
LANE_X = [220, 320, 420]
OUT = Path(__file__).resolve().parent

# BGR colors, intentionally simple/high-contrast.
CAR_COLORS = [(235,235,235), (60,170,250), (80,220,120), (220,120,80), (190,100,220)]


def draw_scene(lane, frame_idx):
    t = frame_idx / FPS
    ti = min(DURATION_SECONDS - 1, int(t))
    signals, _ = signal_at(ti)
    signal = signals[lane]
    count = counts_at(ti)[lane]

    img = np.full((H, W, 3), (42, 58, 48), dtype=np.uint8)
    # roadside
    cv2.rectangle(img, (0, 0), (ROAD_LEFT, H), (48, 85, 50), -1)
    cv2.rectangle(img, (ROAD_RIGHT, 0), (W, H), (48, 85, 50), -1)
    # perspective road polygon
    pts = np.array([[270, 0], [370, 0], [ROAD_RIGHT, H], [ROAD_LEFT, H]], np.int32)
    cv2.fillPoly(img, [pts], (55, 55, 60))
    # lane separators
    for x0 in (295, 345):
        cv2.line(img, (320 + (x0-320)//4, 0), (x0, H), (185,185,185), 2)
    # stop line
    cv2.line(img, (165, STOP_Y+25), (475, STOP_Y+25), (245,245,245), 5)

    # title/incoming-only marker
    cv2.rectangle(img, (10, 10), (238, 62), (15,15,18), -1)
    cv2.putText(img, f'{lane.upper()} APPROACH', (20, 32), cv2.FONT_HERSHEY_SIMPLEX, .62, (255,255,255), 2)
    cv2.putText(img, 'INCOMING TRAFFIC ONLY', (20, 52), cv2.FONT_HERSHEY_SIMPLEX, .42, (170,220,255), 1)
    cv2.putText(img, f'{t:05.1f}s', (548, 25), cv2.FONT_HERSHEY_SIMPLEX, .48, (255,255,255), 1)

    # signal indicator embedded for easy visual validation
    colors = {'RED': (50,50,230), 'YELLOW': (0,220,240), 'GREEN': (60,220,60)}
    cv2.circle(img, (604, 58), 14, colors[signal], -1)
    cv2.putText(img, signal, (535, 91), cv2.FONT_HERSHEY_SIMPLEX, .48, colors[signal], 2)

    # Vehicles approach from horizon (top) toward camera (bottom). Under red/yellow
    # they queue before the stop line; on green they continue through the frame bottom.
    green = signal == 'GREEN'
    phase = t % 8.0
    positions = []
    for i in range(count):
        spawn = (i * 0.85 + (hash(lane) & 7) * 0.07) % 8.0
        progress = ((phase - spawn) % 8.0) / 8.0
        y = 40 + progress * 380
        if not green:
            queue_slot = i // 3
            y = min(y, STOP_Y - queue_slot * 34)
        positions.append((y, i))
    positions.sort()  # far cars first

    raw_amb, _, _ = ambulance_at(ti, lane)
    amb_drawn = False
    for y, i in positions:
        lane_idx = i % 3
        # perspective: farther cars smaller
        scale = max(.45, min(1.2, y / 280))
        ww, hh = int(28*scale), int(46*scale)
        x = LANE_X[lane_idx]
        # perspective pull toward center near horizon
        x = int(320 + (x-320) * max(.35, min(1.0, y/H)))
        yy = int(y)
        if yy < -hh or yy > H+hh: continue
        is_amb = raw_amb and not amb_drawn and i == 0
        if is_amb:
            color = (245,245,245)
            amb_drawn = True
        else:
            color = CAR_COLORS[i % len(CAR_COLORS)]
        cv2.rectangle(img, (x-ww//2, yy-hh//2), (x+ww//2, yy+hh//2), color, -1)
        # windshield/front-facing look: dark upper window + headlights; no rear lamps
        cv2.rectangle(img, (x-ww//2+4, yy-hh//2+5), (x+ww//2-4, yy-hh//2+14), (45,65,80), -1)
        cv2.circle(img, (x-ww//3, yy+hh//2-5), max(1, ww//10), (235,245,255), -1)
        cv2.circle(img, (x+ww//3, yy+hh//2-5), max(1, ww//10), (235,245,255), -1)
        if is_amb:
            cv2.rectangle(img, (x-ww//3, yy-3), (x+ww//3, yy+4), (230,60,60), -1)
            cv2.rectangle(img, (x-2, yy-9), (x+2, yy+10), (230,60,60), -1)
            cv2.rectangle(img, (x-ww//3, yy-hh//2+1), (x-2, yy-hh//2+5), (255,0,0), -1)
            cv2.rectangle(img, (x+2, yy-hh//2+1), (x+ww//3, yy-hh//2+5), (0,0,255), -1)
            cv2.putText(img, 'AMB', (x-ww//2, yy+2), cv2.FONT_HERSHEY_SIMPLEX, max(.24,.33*scale), (40,40,40), 1)

    if raw_amb:
        cv2.rectangle(img, (10, H-42), (260, H-10), (35,35,180), -1)
        cv2.putText(img, 'AMBULANCE APPROACHING', (20, H-20), cv2.FONT_HERSHEY_SIMPLEX, .48, (255,255,255), 2)
    return img


def main():
    for lane in LANES:
        path = OUT / f'demo_{lane.lower()}.mp4'
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), FPS, (W,H))
        if not writer.isOpened():
            raise RuntimeError(f'Could not create {path}')
        for frame_idx in range(DURATION_SECONDS * FPS):
            writer.write(draw_scene(lane, frame_idx))
        writer.release()
        print(path)

if __name__ == '__main__':
    main()
