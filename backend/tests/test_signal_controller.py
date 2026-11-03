"""SignalController tests -- no torch / YOLO required."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "signal_controller", os.path.join(os.path.dirname(__file__), "..", "vision", "signal_controller.py"))
sc = importlib.util.module_from_spec(spec); spec.loader.exec_module(sc)
SignalController = sc.SignalController

LANES = ["North", "South", "East", "West"]

def make(**kw):
    d = dict(min_green_seconds=5, max_green_seconds=30, max_wait_seconds=40,
             yellow_seconds=2, all_red_seconds=1, confirm_frames=2, confirm_window=3,
             emergency_min_green_seconds=4, emergency_lost_timeout_seconds=3,
             emergency_max_green_seconds=20, emergency_cooldown_seconds=5)
    d.update(kw)
    return SignalController(**d)

def amb(*lanes, conf=0.9):
    return {l: {"detected": True, "confidence": conf} for l in lanes}

def signals(out):
    return {l: out[l]["signal"] for l in LANES}

def greens(out):
    return [l for l in LANES if out[l]["signal"] == "GREEN"]

def run(c, counts, seconds, ambulance=None, dt=1.0):
    out = None
    for _ in range(int(seconds / dt)):
        out = c.decide(counts, dt, ambulance)
        assert len(greens(out)) <= 1, "conflicting greens!"
    return out

def test_a_normal_busiest_gets_first_green():
    c = make()
    out = c.decide({"North": 12, "South": 9, "East": 38, "West": 20}, 0)
    assert greens(out) == ["East"]
    assert out["_controller"]["emergency_active"] is False

def test_b_ambulance_overrides_density():
    c = make()
    counts = {"North": 12, "South": 9, "East": 38, "West": 20}
    out = None
    for _ in range(3):
        out = c.decide(counts, 1.0, amb("South"))
    # first call grants initial green; emergency confirmed on 2nd call
    out = run(c, counts, 6, amb("South"))
    assert greens(out) == ["South"]
    assert out["_controller"]["reason"] in ("ambulance_priority",)
    assert out["_controller"]["emergency_lane"] == "South"
    assert out["South"]["ambulance_detected"] is True

def test_b2_first_decision_with_ambulance():
    c = make(confirm_frames=1, confirm_window=1)
    out = c.decide({"North": 1, "East": 40}, 0, amb("North"))
    assert greens(out) == ["North"]

def test_c_safe_transition_yellow_allred_green():
    c = make()
    counts = {"North": 5, "South": 5, "East": 40, "West": 5}
    out = c.decide(counts, 0)
    assert greens(out) == ["East"]
    run(c, counts, 2)
    seen = []
    for _ in range(8):
        out = c.decide(counts, 1.0, amb("North"))
        seen.append(signals(out))
        assert len(greens(out)) <= 1
    # sequence for East must be GREEN -> YELLOW -> RED(all) -> ... and North GREEN last
    east = [s["East"] for s in seen]
    assert "YELLOW" in east
    first_y = east.index("YELLOW")
    # ALL_RED phase: nobody green or yellow
    assert any(all(v == "RED" for v in s.values()) for s in seen[first_y:])
    # North must never be green before East has been yellow
    north_green_idx = next(i for i, s in enumerate(seen) if s["North"] == "GREEN")
    assert north_green_idx > first_y
    assert out["_controller"]["emergency_lane"] == "North"
    assert signals(out)["East"] == "RED"

def test_d_emergency_releases_and_normal_resumes():
    c = make()
    counts = {"North": 5, "South": 5, "East": 40, "West": 5}
    c.decide(counts, 0)
    run(c, counts, 8, amb("North"))
    assert c.emergency_active and c.current_green == "North"
    out = run(c, counts, 10)  # ambulance gone
    assert out["_controller"]["emergency_active"] is False
    assert out["_controller"]["emergency_lane"] is None
    # normal control: North has 5 vehicles (not clear) but East is busiest;
    # eventually normal rules rotate (max green 30s) -- just verify normal reasons occur
    out = run(c, counts, 40)
    assert out["_controller"]["reason"] in ("continue_green", "max_green_exceeded", "traffic_cleared",
                                             "transition_yellow", "transition_all_red", "starvation_relief")

def test_d2_emergency_max_timeout_when_detection_never_stops():
    c = make()
    counts = {"North": 5, "South": 5, "East": 40, "West": 5}
    c.decide(counts, 0)
    run(c, counts, 40, amb("North"))   # permanently "detected"
    # Must have released at least once via timeout (cooldown means it can retrigger later but not stay forever stuck)
    assert c.cooldown_until["North"] > 0

def test_e_multiple_ambulances_deterministic_no_oscillation():
    c = make()
    counts = {"North": 5, "South": 5, "East": 5, "West": 30}
    c.decide(counts, 0)
    # North confirmed first, West later
    run(c, counts, 2, amb("North"))
    changes, last = 0, None
    for i in range(12):
        out = c.decide(counts, 1.0, amb("North", "West"))
        lane = out["_controller"]["emergency_lane"]
        if lane != last:
            changes += 1; last = lane
    assert last == "North"       # first confirmed keeps priority
    assert changes == 1          # never flipped to West mid-emergency
    # simultaneous: tie-break by confidence
    c2 = make(confirm_frames=1, confirm_window=1)
    c2.decide(counts, 0)
    both = {"North": {"detected": True, "confidence": 0.7}, "West": {"detected": True, "confidence": 0.95}}
    out = c2.decide(counts, 1.0, both)
    assert out["_controller"]["emergency_lane"] == "West"

def test_single_weak_detection_ignored():
    c = make(confirm_frames=3, confirm_window=5)
    counts = {"North": 5, "South": 5, "East": 40, "West": 5}
    c.decide(counts, 0)
    out = c.decide(counts, 1.0, amb("North"))
    out = c.decide(counts, 1.0)
    assert out["_controller"]["emergency_active"] is False
    assert greens(out) == ["East"]

def test_f_no_ambulance_traffic_cleared():
    c = make()
    counts = {"North": 30, "South": 0, "East": 10, "West": 0}
    c.decide(counts, 0)
    assert c.current_green == "North"
    counts = {"North": 0, "South": 0, "East": 10, "West": 0}
    out = run(c, counts, 12)
    assert greens(out) == ["East"] and out["_controller"]["emergency_active"] is False

def test_f_no_ambulance_max_green():
    c = make(min_green_seconds=100)
    counts = {"North": 30, "South": 0, "East": 10, "West": 0}
    c.decide(counts, 0)
    out = run(c, counts, 40)
    assert "North" not in greens(out)

def test_f_starvation_relief():
    c = make(max_green_seconds=1000, min_green_seconds=1000, max_wait_seconds=10)
    counts = {"North": 30, "South": 3, "East": 0, "West": 0}
    c.decide(counts, 0)
    out = run(c, counts, 20)
    assert greens(out) == ["South"]

def test_zero_transition_mode_switches_instantly():
    c = make(yellow_seconds=0, all_red_seconds=0, confirm_frames=1, confirm_window=1)
    counts = {"North": 5, "South": 5, "East": 40, "West": 5}
    c.decide(counts, 0)
    out = c.decide(counts, 1.0, amb("North"))
    assert greens(out) == ["North"]
