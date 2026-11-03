import os

ALL_LANES = ["North", "South", "East", "West"]
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
MAX_GREEN_SECONDS = float(os.environ.get("MAX_GREEN_SECONDS", "60"))
MAX_WAIT_SECONDS = float(os.environ.get("MAX_WAIT_SECONDS", "90"))
STARVATION_MIN_VEHICLES = int(os.environ.get("STARVATION_MIN_VEHICLES", "1"))
STARVATION_MAX_VEHICLES = int(os.environ.get("STARVATION_MAX_VEHICLES", "10"))
MIN_GREEN_SECONDS = float(os.environ.get("MIN_GREEN_SECONDS", "15"))
CLEAR_THRESHOLD_VEHICLES = int(os.environ.get("CLEAR_THRESHOLD_VEHICLES", "2"))
# Hysteresis: require this many CONSECUTIVE segments at/below the clear
# threshold before switching -- a single noisy/missed YOLO detection
# should not be enough to flip the signal early.
CONSECUTIVE_CLEAR_REQUIRED = int(os.environ.get("CONSECUTIVE_CLEAR_REQUIRED", "2"))
SEGMENT_SECONDS = float(os.environ.get("SEGMENT_SECONDS", "1"))
FIRST_DECISION_IMGSZ = int(os.environ.get("FIRST_DECISION_IMGSZ", "384"))
YOLO_CONFIDENCE = float(os.environ.get("YOLO_CONFIDENCE", "0.30"))
AI_FPS = float(os.environ.get("AI_FPS", "4"))


# --- Safe transition timing (applies to every green->green change) --------
YELLOW_SECONDS = float(os.environ.get("YELLOW_SECONDS", "3"))
ALL_RED_SECONDS = float(os.environ.get("ALL_RED_SECONDS", "1"))

# --- Emergency (ambulance) priority ---------------------------------------
# A lane is "confirmed" when the ambulance model fired in at least
# AMBULANCE_CONFIRM_FRAMES of the last AMBULANCE_CONFIRM_WINDOW decide() calls.
AMBULANCE_CONFIRM_FRAMES = int(os.environ.get("AMBULANCE_CONFIRM_FRAMES", "3"))
AMBULANCE_CONFIRM_WINDOW = int(os.environ.get("AMBULANCE_CONFIRM_WINDOW", "5"))
# Once the emergency lane is green, hold at least this long...
EMERGENCY_MIN_GREEN_SECONDS = float(os.environ.get("EMERGENCY_MIN_GREEN_SECONDS", "10"))
# ...and release once the ambulance has not been seen for this long.
EMERGENCY_LOST_TIMEOUT_SECONDS = float(os.environ.get("EMERGENCY_LOST_TIMEOUT_SECONDS", "4"))
# Hard cap on emergency green so a stuck/false detection cannot lock the junction.
EMERGENCY_MAX_GREEN_SECONDS = float(os.environ.get("EMERGENCY_MAX_GREEN_SECONDS", "45"))
# After release, ignore that lane briefly so a lingering detection cannot re-trigger.
EMERGENCY_COOLDOWN_SECONDS = float(os.environ.get("EMERGENCY_COOLDOWN_SECONDS", "8"))

class SignalController:
    """
    Stateful signal controller. Rules, in priority order, every decide() call:

      0. EMERGENCY OVERRIDE: a lane with a temporally-confirmed ambulance
         gets green (via YELLOW -> ALL_RED if another lane is green). Priority
         is held until the ambulance has been unseen for
         EMERGENCY_LOST_TIMEOUT_SECONDS (after EMERGENCY_MIN_GREEN_SECONDS),
         or EMERGENCY_MAX_GREEN_SECONDS elapses. While active, normal rules
         are suspended.
      1. STARVATION RELIEF: a red lane waited >= MAX_WAIT_SECONDS with a
         small-but-real count -> gets green.
      2. TRAFFIC CLEARED: current green held >= MIN_GREEN, count <=
         CLEAR_THRESHOLD for CONSECUTIVE_CLEAR_REQUIRED calls, others busy.
      3. MAX GREEN: forced rotation to the busiest other lane.
      Otherwise the current green continues.

    Every change of green lane goes through a safe transition:
        old GREEN -> old YELLOW (YELLOW_SECONDS) -> ALL RED (ALL_RED_SECONDS)
        -> new GREEN
    (set yellow_seconds=all_red_seconds=0 to disable). The first-ever green
    is applied immediately. If an emergency appears mid-transition, the
    transition target is re-pointed at the emergency lane.

    decide(counts, segment_seconds, ambulance=None)
      ambulance: optional {lane: {"detected": bool, "confidence": float}}
      (raw per-frame model output; confirmation happens here).
    """
    def __init__(self, lanes=None,
                 min_green_seconds=MIN_GREEN_SECONDS, max_green_seconds=MAX_GREEN_SECONDS,
                 max_wait_seconds=MAX_WAIT_SECONDS,
                 clear_threshold_vehicles=CLEAR_THRESHOLD_VEHICLES,
                 consecutive_clear_required=CONSECUTIVE_CLEAR_REQUIRED,
                 starvation_min=STARVATION_MIN_VEHICLES, starvation_max=STARVATION_MAX_VEHICLES,
                 yellow_seconds=YELLOW_SECONDS, all_red_seconds=ALL_RED_SECONDS,
                 confirm_frames=AMBULANCE_CONFIRM_FRAMES, confirm_window=AMBULANCE_CONFIRM_WINDOW,
                 emergency_min_green_seconds=EMERGENCY_MIN_GREEN_SECONDS,
                 emergency_lost_timeout_seconds=EMERGENCY_LOST_TIMEOUT_SECONDS,
                 emergency_max_green_seconds=EMERGENCY_MAX_GREEN_SECONDS,
                 emergency_cooldown_seconds=EMERGENCY_COOLDOWN_SECONDS):
        self.lanes = lanes or list(ALL_LANES)
        self.min_green_seconds = min_green_seconds
        self.max_green_seconds = max_green_seconds
        self.max_wait_seconds = max_wait_seconds
        self.clear_threshold_vehicles = clear_threshold_vehicles
        self.consecutive_clear_required = max(1, consecutive_clear_required)
        self.starvation_min = starvation_min
        self.starvation_max = starvation_max
        self.yellow_seconds = max(0.0, yellow_seconds)
        self.all_red_seconds = max(0.0, all_red_seconds)
        self.confirm_frames = max(1, confirm_frames)
        self.confirm_window = max(self.confirm_frames, confirm_window)
        self.emergency_min_green_seconds = emergency_min_green_seconds
        self.emergency_lost_timeout_seconds = emergency_lost_timeout_seconds
        self.emergency_max_green_seconds = emergency_max_green_seconds
        self.emergency_cooldown_seconds = emergency_cooldown_seconds

        self.current_green = None      # lane currently showing GREEN (None during a transition)
        self.green_elapsed = 0.0
        self.waiting_time = {lane: 0.0 for lane in self.lanes}
        self.consecutive_clear_count = 0

        # transition state machine
        self.phase = "GREEN"           # GREEN | YELLOW | ALL_RED
        self.phase_elapsed = 0.0
        self.transition_from = None
        self.transition_target = None
        self.transition_reason = None

        # emergency state
        self.clock = 0.0
        self.emergency_lane = None
        self.emergency_green_elapsed = 0.0
        self.emergency_unseen = 0.0
        self.cooldown_until = {lane: -1.0 for lane in self.lanes}
        self._hits = {lane: [] for lane in self.lanes}          # rolling detection history
        self._confirmed_since = {lane: None for lane in self.lanes}
        self._confidence = {lane: 0.0 for lane in self.lanes}
        self._raw = {lane: False for lane in self.lanes}

    # ---- helpers --------------------------------------------------------
    @property
    def emergency_active(self):
        return self.emergency_lane is not None

    def _grant_green(self, lane):
        self.current_green = lane
        self.green_elapsed = 0.0
        self.waiting_time[lane] = 0.0
        self.consecutive_clear_count = 0
        self.phase = "GREEN"
        self.phase_elapsed = 0.0
        self.transition_from = self.transition_target = self.transition_reason = None

    def _switch_to(self, new_lane, reason="switch"):
        """Begin a safe change of green to new_lane."""
        if self.current_green is None and self.phase == "GREEN":
            self._grant_green(new_lane)          # very first green
            return
        if self.phase in ("YELLOW", "ALL_RED"):  # already mid-transition: retarget only
            self.transition_target = new_lane
            self.transition_reason = reason
            return
        if self.yellow_seconds <= 0 and self.all_red_seconds <= 0:
            self._grant_green(new_lane)
            return
        self.transition_from = self.current_green
        self.transition_target = new_lane
        self.transition_reason = reason
        self.current_green = None
        self.phase_elapsed = 0.0
        self.phase = "YELLOW" if self.yellow_seconds > 0 else "ALL_RED"
        self.consecutive_clear_count = 0

    def _advance_transition(self, dt):
        self.phase_elapsed += dt
        if self.phase == "YELLOW" and self.phase_elapsed >= self.yellow_seconds:
            self.phase, self.phase_elapsed = "ALL_RED", 0.0
        if self.phase == "ALL_RED" and self.phase_elapsed >= self.all_red_seconds:
            self._grant_green(self.transition_target)

    def _update_ambulance(self, ambulance, dt):
        """Update confirmation history. Returns set of confirmed lanes."""
        ambulance = ambulance or {}
        confirmed = set()
        for lane in self.lanes:
            info = ambulance.get(lane) or {}
            hit = bool(info.get("detected"))
            conf = float(info.get("confidence", 0.0) or 0.0) if hit else 0.0
            self._raw[lane] = hit
            if hit:
                self._confidence[lane] = conf
            h = self._hits[lane]
            h.append(hit)
            del h[:-self.confirm_window]
            if sum(h) >= self.confirm_frames and self.clock >= self.cooldown_until[lane]:
                confirmed.add(lane)
                if self._confirmed_since[lane] is None:
                    self._confirmed_since[lane] = self.clock
            else:
                self._confirmed_since[lane] = None
                if not hit:
                    self._confidence[lane] = 0.0
        return confirmed

    def _pick_emergency(self, confirmed):
        def key(l):  # earliest confirmation, then higher confidence, then longer wait, then lane order
            return (self._confirmed_since[l], -self._confidence[l], -self.waiting_time[l], self.lanes.index(l))
        return min(confirmed, key=key)

    def _release_emergency(self, why):
        lane = self.emergency_lane
        self.cooldown_until[lane] = self.clock + self.emergency_cooldown_seconds
        self._hits[lane] = []
        self._confirmed_since[lane] = None
        self.emergency_lane = None
        self.emergency_green_elapsed = 0.0
        self.emergency_unseen = 0.0
        self.consecutive_clear_count = 0
        print(f"[EMERGENCY] Ambulance cleared {lane} ({why})")
        print("[SIGNAL] Returning to normal adaptive control")

    # ---- main entry -----------------------------------------------------
    def decide(self, counts, segment_seconds, ambulance=None):
        counts = {lane: max(0, int(counts.get(lane, 0))) for lane in self.lanes}
        dt = max(0.0, float(segment_seconds))
        self.clock += dt
        reason = "initial"
        confirmed = self._update_ambulance(ambulance, dt)

        first_call = self.current_green is None and self.phase == "GREEN" and self.transition_target is None
        if not first_call:
            for lane in self.lanes:
                if lane != self.current_green:
                    self.waiting_time[lane] += dt
            if self.current_green is not None:
                self.green_elapsed += dt

        # ---- emergency bookkeeping -------------------------------------
        if self.emergency_lane is not None:
            lane = self.emergency_lane
            if self._raw[lane]:
                self.emergency_unseen = 0.0
            else:
                self.emergency_unseen += dt
            if self.current_green == lane:
                self.emergency_green_elapsed += dt
                if self.emergency_green_elapsed >= self.emergency_max_green_seconds:
                    self._release_emergency("max emergency green timeout")
                elif (self.emergency_green_elapsed >= self.emergency_min_green_seconds
                      and self.emergency_unseen >= self.emergency_lost_timeout_seconds):
                    self._release_emergency("ambulance passed")
        confirmed = {l for l in confirmed if self.clock >= self.cooldown_until[l]}
        if self.emergency_lane is None and confirmed:
            lane = self._pick_emergency(confirmed)
            self.emergency_lane = lane
            self.emergency_green_elapsed = self.green_elapsed if self.current_green == lane else 0.0
            self.emergency_unseen = 0.0
            print(f"[EMERGENCY] Ambulance confirmed on {lane}")

        # ---- advance an in-flight transition ---------------------------
        if self.phase in ("YELLOW", "ALL_RED"):
            if self.emergency_lane is not None and self.transition_target != self.emergency_lane:
                self.transition_target = self.emergency_lane
                self.transition_reason = "ambulance_priority"
            pending_reason = self.transition_reason or "transition_complete"
            self._advance_transition(dt)
            if self.phase in ("YELLOW", "ALL_RED"):
                reason = "transition_" + self.phase.lower()
            else:
                reason = pending_reason
                print(f"[SIGNAL] {self.current_green} GREEN reason={reason}")

        # ---- decision logic (only when a lane is actually green) -------
        elif first_call:
            if self.emergency_lane is not None:
                new = self.emergency_lane; reason = "ambulance_priority"
            else:
                cand = [l for l in self.lanes if counts[l] > 0]
                new = max(cand, key=lambda l: counts[l]) if cand else self.lanes[0]
            self._grant_green(new)
        elif self.emergency_lane is not None:
            if self.current_green != self.emergency_lane:
                self._switch_to(self.emergency_lane, "ambulance_priority")
                reason = "ambulance_priority"
                print(f"[SIGNAL] {self.emergency_lane} priority: yellow -> all-red -> green (ambulance_priority)")
            else:
                reason = "ambulance_priority"
        else:
            others = [l for l in self.lanes if l != self.current_green]
            busy_others = [l for l in others if counts[l] > 0]
            if counts[self.current_green] <= self.clear_threshold_vehicles:
                self.consecutive_clear_count += 1
            else:
                self.consecutive_clear_count = 0

            starved = [l for l in others
                       if self.waiting_time[l] >= self.max_wait_seconds
                       and self.starvation_min <= counts[l] <= self.starvation_max]
            if starved:
                self._switch_to(max(starved, key=lambda l: self.waiting_time[l]), "starvation_relief")
                reason = "starvation_relief"
            elif (self.green_elapsed >= self.min_green_seconds
                  and self.consecutive_clear_count >= self.consecutive_clear_required
                  and busy_others):
                self._switch_to(max(busy_others, key=lambda l: counts[l]), "traffic_cleared")
                reason = "traffic_cleared"
            elif self.green_elapsed >= self.max_green_seconds:
                if busy_others:
                    self._switch_to(max(busy_others, key=lambda l: counts[l]), "max_green_exceeded")
                    reason = "max_green_exceeded"
                else:
                    reason = "max_green_exceeded_no_other_traffic"
            else:
                reason = "continue_green"

        # a switch with zero-length transition completes inside _switch_to
        return self._build_output(counts, reason)

    def _lane_signal(self, lane):
        if self.phase == "GREEN":
            return "GREEN" if lane == self.current_green else "RED"
        if self.phase == "YELLOW":
            return "YELLOW" if lane == self.transition_from else "RED"
        return "RED"  # ALL_RED

    def _build_output(self, counts, reason):
        decisions = {}
        for lane in self.lanes:
            sig = self._lane_signal(lane)
            confirmed = self._confirmed_since[lane] is not None
            d = {
                "signal": sig,
                "vehicle_count": counts[lane],
                "waiting_time_seconds": 0.0 if sig == "GREEN" else round(self.waiting_time[lane], 1),
                "ambulance_detected": confirmed,
                "ambulance_raw_detected": self._raw[lane],
                "ambulance_confidence": round(self._confidence[lane], 3),
            }
            decisions[lane] = d
        selected = self.current_green if self.current_green is not None else self.transition_target
        decisions["_controller"] = {
            "selected_lane": selected,
            "green_elapsed_seconds": round(self.green_elapsed, 1),
            "reason": reason,
            "min_green_seconds": self.min_green_seconds,
            "max_green_seconds": self.max_green_seconds,
            "max_wait_seconds": self.max_wait_seconds,
            "clear_threshold_vehicles": self.clear_threshold_vehicles,
            "consecutive_clear_required": self.consecutive_clear_required,
            "consecutive_clear_count": self.consecutive_clear_count,
            "emergency_active": self.emergency_active,
            "emergency_lane": self.emergency_lane,
            "transition_state": self.phase,
            "transition_from": self.transition_from,
            "transition_target": self.transition_target,
        }
        return decisions
