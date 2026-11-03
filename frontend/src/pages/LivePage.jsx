import { useEffect, useMemo, useRef, useState } from "react";
import { subscribeToTrafficEvents } from "../api/traffic";

const LANES = ["North", "South", "East", "West"];
const LANE_ICON = { North: "⬆️", South: "⬇️", East: "➡️", West: "⬅️" };
const LANE_COLOR = { North: "#00b4ff", South: "#00ff87", East: "#ffd32a", West: "#ff6b81" };
const SIGNAL_COLOR = { GREEN: "#00ff87", YELLOW: "#ffd32a", RED: "#ff4757" };

const STATUS_LABEL = {
  uploading: "Uploading videos…",
  uploaded: "Uploaded — starting AI…",
  analyzing: "AI analyzing (live)…",
  complete: "Analysis complete",
  error: "Error",
};

const REASON_LABEL = {
  initial: "Initial pick",
  continue_green: "Holding green",
  traffic_cleared: "Lane cleared — switching early",
  max_green_exceeded: "Max green reached — rotating",
  max_green_exceeded_no_other_traffic: "Max green reached (no other traffic waiting)",
  starvation_relief: "Starvation relief — rescuing a waiting lane",
  transition_yellow: "Transition: yellow",
  transition_all_red: "Transition: all red",
  ambulance_priority: "Ambulance priority",
};

// Timing model (matches the backend): event 0 is the "instant" decision at
// video t=0. Event k>=1 is made after observing video seconds
// [(k-1)*seg, k*seg) and therefore takes effect at t = k*seg.
const indexForTime = (t, seg) => Math.max(0, Math.floor(t / seg));

export default function LivePage({ sessionId, files, onViewFullReport, setPage }) {
  const [status, setStatus] = useState("uploading");
  const [errorMsg, setErrorMsg] = useState(null);
  const [result, setResult] = useState(null);
  const [updateCount, setUpdateCount] = useState(0);

  const [timeline, setTimeline] = useState([]);   // full decision objects (incl. _controller), in order
  const [seg, setSeg] = useState(1);              // seconds of video per decision
  const [playing, setPlaying] = useState(true);   // user intent
  const [waiting, setWaiting] = useState(false);  // paused because AI is behind the video
  const [time, setTime] = useState(0);            // shared video clock (seconds)
  const [duration, setDuration] = useState(0);
  const [ended, setEnded] = useState(false);

  const videoRefs = useRef({});
  const timelineRef = useRef([]);
  const statusRef = useRef("uploading");
  const playingRef = useRef(true);
  const segRef = useRef(1);
  timelineRef.current = timeline;
  statusRef.current = status;
  playingRef.current = playing;
  segRef.current = seg;

  const objectUrls = useMemo(() => {
    const urls = {};
    LANES.forEach((lane) => {
      if (files?.[lane]) urls[lane] = URL.createObjectURL(files[lane]);
    });
    return urls;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  useEffect(() => () => {
    Object.values(objectUrls).forEach((u) => URL.revokeObjectURL(u));
  }, [objectUrls]);

  useEffect(() => {
    if (!sessionId) return;
    const es = subscribeToTrafficEvents(sessionId, {
      onStatus: (s) => setStatus(s),
      onDecision: (d) => {
        setStatus("analyzing");
        setTimeline((t) => [...t, d]);
        setUpdateCount((n) => n + 1);
      },
      onComplete: (r) => {
        setStatus("complete");
        setResult(r);
        // The result carries the authoritative, ordered timeline.
        if (Array.isArray(r?.segment_decisions) && r.segment_decisions.length) {
          setTimeline(r.segment_decisions.map((e) => e.decisions));
        }
        if (r?.segment_seconds) setSeg(Number(r.segment_seconds) || 1);
      },
      onError: (msg) => { setStatus("error"); setErrorMsg(msg); },
    });
    return () => es.close();
  }, [sessionId]);

  const activeLanes = LANES.filter((l) => files?.[l]);

  // ---- shared clock: one master video, others follow; playback is gated by AI progress ----
  useEffect(() => {
    const id = setInterval(() => {
      const vids = activeLanes.map((l) => videoRefs.current[l]).filter(Boolean);
      if (!vids.length) return;
      const finite = vids.filter((v) => Number.isFinite(v.duration) && v.duration > 0);
      const master = finite.length ? finite.reduce((a, b) => (b.duration > a.duration ? b : a)) : vids[0];
      const t = master.currentTime || 0;
      setTime(t);
      if (finite.length) setDuration(master.duration);

      const len = timelineRef.current.length;
      const complete = statusRef.current === "complete";
      const need = indexForTime(t, segRef.current);
      const aiHasIt = complete || need < len;
      const isEnded = master.ended;
      setEnded(isEnded);
      const shouldPlay = playingRef.current && aiHasIt && !isEnded;
      setWaiting(playingRef.current && !aiHasIt && !isEnded);

      vids.forEach((v) => {
        if (shouldPlay && v.paused && !v.ended) v.play().catch(() => {});
        if (!shouldPlay && !v.paused) v.pause();
        // keep every lane on the same timestamp
        if (v !== master && !v.ended && Math.abs(v.currentTime - t) > 0.35) v.currentTime = t;
      });
      if (isEnded && playingRef.current) setPlaying(false);
    }, 100);
    return () => clearInterval(id);
  }, [sessionId, activeLanes.join(",")]);

  const seekTo = (t) => {
    const analyzed = status === "complete" ? Infinity : Math.max(0, timeline.length * seg - 0.05);
    const target = Math.max(0, Math.min(t, duration || t, analyzed));
    activeLanes.forEach((l) => { const v = videoRefs.current[l]; if (v) v.currentTime = target; });
    setTime(target);
  };
  const togglePlay = () => {
    if (ended) { seekTo(0); setPlaying(true); return; }
    setPlaying((p) => !p);
  };

  const idx = timeline.length ? Math.min(indexForTime(time, seg), timeline.length - 1) : -1;
  const current = idx >= 0 ? timeline[idx] : null;
  const controllerInfo = current?._controller || null;
  const decisions = current || null;
  const analyzedSeconds = timeline.length * seg;

  return (
    <div style={S.page}>
      <div style={S.header}>
        <h1 style={S.title}>Live Traffic Analysis</h1>
        <StatusPill status={status} updateCount={updateCount} />
      </div>

      {errorMsg && <div style={S.error}>⚠️ {errorMsg}</div>}

      {controllerInfo?.emergency_active && (
        <div style={S.emergencyBanner} role="alert">
          🚑 AMBULANCE DETECTED — EMERGENCY PRIORITY: {String(controllerInfo.emergency_lane).toUpperCase()}
          {controllerInfo.transition_state && controllerInfo.transition_state !== "GREEN"
            ? ` · clearing intersection (${controllerInfo.transition_state})` : " · GREEN"}
        </div>
      )}

      <div style={S.grid(activeLanes.length)}>
        {activeLanes.map((lane) => (
          <LaneTile
            key={lane}
            lane={lane}
            videoUrl={objectUrls[lane]}
            registerVideo={(el) => { videoRefs.current[lane] = el; }}
            decision={decisions?.[lane]}
            waiting={waiting}
          />
        ))}
      </div>

      <div style={S.playerBar}>
        <button style={S.playBtn} onClick={togglePlay}>{ended ? "↻ Replay" : playing ? "❚❚ Pause" : "▶ Play"}</button>
        <input
          type="range" min="0" max={Math.max(duration, 0.1)} step="0.1" value={Math.min(time, duration || time)}
          onChange={(e) => seekTo(Number(e.target.value))} style={{ flex: 1, minWidth: 160 }}
          aria-label="Video position"
        />
        <span style={S.timeLabel}>{time.toFixed(1)}s / {duration ? duration.toFixed(1) : "—"}s</span>
        <span style={S.timeLabel}>AI analyzed: {status === "complete" ? "all" : `${analyzedSeconds.toFixed(0)}s`}</span>
      </div>
      {waiting && <div style={S.waitNote}>⏳ Paused — waiting for the AI to analyze this part of the video. Playback resumes automatically so the signals always match the picture.</div>}

      {timeline.length > 0 && (
        <SignalTimeline lanes={activeLanes} timeline={timeline} seg={seg} total={Math.max(duration, analyzedSeconds)}
          time={time} onSeek={seekTo} />
      )}

      {controllerInfo && (
        <div style={S.controllerBar}>
          <span style={S.controllerItem}>
            <b style={{ color: controllerInfo.transition_state && controllerInfo.transition_state !== "GREEN" ? SIGNAL_COLOR.YELLOW : SIGNAL_COLOR.GREEN }}>
              {controllerInfo.transition_state && controllerInfo.transition_state !== "GREEN"
                ? `SWITCHING → ${controllerInfo.transition_target || controllerInfo.selected_lane} (${controllerInfo.transition_state})`
                : `GREEN: ${controllerInfo.selected_lane}`}
            </b>
          </span>
          <span style={S.controllerItem}>held {controllerInfo.green_elapsed_seconds ?? 0}s</span>
          <span style={S.controllerItem}>{REASON_LABEL[controllerInfo.reason] || controllerInfo.reason}</span>
          <span style={S.controllerItem}>decision #{idx} @ {(idx * seg).toFixed(0)}s</span>
        </div>
      )}

      {status === "complete" && result && (
        <div style={S.completeBar}>
          <span>✓ Full analysis finished — {result.total_vehicles} vehicles detected total.</span>
          <button style={S.reportBtn} onClick={() => { onViewFullReport(result); setPage("result"); }}>
            View Full Report →
          </button>
        </div>
      )}

      {status !== "error" && (
        <p style={S.hint}>
          Videos play from one shared clock. Each signal shown is the controller's state at the current video
          time (a decision made after watching second N takes effect at second N+1). If playback gets ahead of the
          AI it pauses automatically. Use videos of equal length for the cleanest alignment.
        </p>
      )}
    </div>
  );
}

function StatusPill({ status, updateCount }) {
  const dotColor = status === "error" ? "#ff4757" : status === "complete" ? "#00ff87" : "#ffd32a";
  return (
    <div style={S.statusPill}>
      <span style={{ ...S.dot, background: dotColor, boxShadow: status !== "error" ? `0 0 8px ${dotColor}` : "none" }} />
      <span>{STATUS_LABEL[status] || status}</span>
      {status === "analyzing" && updateCount > 0 && (
        <span style={{ color: "#4a7090", marginLeft: 6 }}>· {updateCount} updates</span>
      )}
    </div>
  );
}

function LaneTile({ lane, videoUrl, registerVideo, decision, waiting }) {
  const color = LANE_COLOR[lane];
  // No decision yet is NOT the same as RED — show a neutral WAITING state.
  const signal = decision?.signal || "WAITING";
  const signalColor = SIGNAL_COLOR[signal] || "#7090b0";
  const isGreen = signal === "GREEN";
  const conf = Math.round((decision?.ambulance_confidence || 0) * 100);

  return (
    <div style={S.tile(isGreen, signalColor)}>
      <div style={S.tileHeader}>
        <span style={{ color, fontWeight: 800, fontSize: 13, letterSpacing: 1 }}>
          {LANE_ICON[lane]} {lane.toUpperCase()}
        </span>
        <span style={S.signalBadge(signalColor)}>{signal}</span>
      </div>
      <div style={S.videoWrap}>
        <video ref={registerVideo} src={videoUrl} muted playsInline preload="auto" style={S.video} />
        <div style={S.lightOverlay} title={`${lane} signal: ${signal}`}>
          {["RED", "YELLOW", "GREEN"].map((c) => (
            <span key={c} style={{ ...S.lamp, background: signal === c ? SIGNAL_COLOR[c] : "#2a2f3a",
              boxShadow: signal === c ? `0 0 10px ${SIGNAL_COLOR[c]}` : "none" }} />
          ))}
        </div>
        {decision?.ambulance_detected && <div style={S.ambOverlay}>🚑 AMBULANCE</div>}
        {waiting && <div style={S.waitOverlay}>waiting for AI…</div>}
      </div>
      <div style={S.tileStats}>
        <span>🚗 {decision?.vehicle_count ?? "—"} vehicles</span>
        <span>⏱ waited {decision?.waiting_time_seconds ?? 0}s</span>
      </div>
      <div style={decision?.ambulance_detected ? S.ambOn : decision?.ambulance_raw_detected ? S.ambMaybe : S.ambOff}>
        {decision?.ambulance_detected
          ? `🚑 AMBULANCE DETECTED · EMERGENCY PRIORITY · Confidence: ${conf}%`
          : decision?.ambulance_raw_detected
            ? `Possible ambulance (${conf}%) — confirming…`
            : "NO EMERGENCY"}
      </div>
    </div>
  );
}

// One row per lane: a block per decision, coloured by that lane's signal, with a playhead.
function SignalTimeline({ lanes, timeline, seg, total, time, onSeek }) {
  const n = Math.max(timeline.length, Math.ceil(total / seg) || 1);
  const span = n * seg;
  const handle = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - r.left) / r.width) * span);
  };
  return (
    <div style={S.tlWrap}>
      <div style={S.tlTitle}>SIGNAL TIMELINE (click to seek)</div>
      <div style={{ position: "relative", cursor: "pointer" }} onClick={handle}>
        {lanes.map((lane) => (
          <div key={lane} style={S.tlRow}>
            <span style={{ ...S.tlLabel, color: LANE_COLOR[lane] }}>{lane}</span>
            <div style={{ display: "grid", gridTemplateColumns: `repeat(${n}, 1fr)`, gap: 1, flex: 1 }}>
              {Array.from({ length: n }, (_, i) => {
                const d = timeline[i]?.[lane];
                const c = d ? SIGNAL_COLOR[d.signal] || "#2a2f3a" : "#1a2236";
                return <span key={i} title={d ? `t=${(i * seg).toFixed(0)}s ${d.signal}${d.ambulance_detected ? " · ambulance" : ""}` : "not analyzed yet"}
                  style={{ height: 16, background: c, opacity: d ? 1 : 0.5, borderBottom: d?.ambulance_detected ? "3px solid #fff" : "none" }} />;
              })}
            </div>
          </div>
        ))}
        <div style={{ ...S.playhead, left: `calc(54px + (100% - 54px) * ${Math.min(1, time / span)})` }} />
      </div>
      <div style={S.tlLegend}>
        <span style={{ color: SIGNAL_COLOR.GREEN }}>■ green</span>
        <span style={{ color: SIGNAL_COLOR.YELLOW }}>■ yellow</span>
        <span style={{ color: SIGNAL_COLOR.RED }}>■ red</span>
        <span style={{ color: "#fff" }}>▁ ambulance confirmed</span>
      </div>
    </div>
  );
}

const S = {
  page: {
    minHeight: "calc(100vh - 70px)",
    padding: "32px 24px 60px",
    background: "radial-gradient(ellipse at 50% 0%, #0d2040 0%, #0a0f1e 70%)",
  },
  header: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    flexWrap: "wrap", gap: 12, maxWidth: 1100, margin: "0 auto 20px",
  },
  title: { fontSize: "clamp(22px, 4vw, 34px)", fontWeight: 900, color: "#e0f0ff", letterSpacing: -0.5, margin: 0 },
  statusPill: {
    display: "flex", alignItems: "center", gap: 8,
    background: "rgba(255,255,255,0.03)", border: "1px solid #1e2d4a",
    padding: "8px 16px", borderRadius: 10, fontSize: 13, color: "#a0c0e0",
  },
  dot: { width: 9, height: 9, borderRadius: "50%", display: "inline-block" },
  grid: (count) => ({
    display: "grid",
    gridTemplateColumns: count <= 1 ? "1fr" : count === 2 ? "repeat(2, 1fr)" : "repeat(2, 1fr)",
    gap: 18, maxWidth: 1100, margin: "0 auto",
  }),
  tile: (isGreen, signalColor) => ({
    background: "rgba(255,255,255,0.02)",
    border: `2px solid ${isGreen ? signalColor : "#1e2d4a"}`,
    borderRadius: 14, padding: 12, transition: "border-color 0.3s",
    boxShadow: isGreen ? `0 0 20px ${signalColor}33` : "none",
  }),
  tileHeader: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  signalBadge: (color) => ({
    color, border: `1px solid ${color}`, borderRadius: 6, padding: "2px 10px",
    fontSize: 11, fontWeight: 800, letterSpacing: 1,
  }),
  video: {
    width: "100%", aspectRatio: "16 / 9", borderRadius: 8,
    background: "#000", objectFit: "cover", display: "block",
  },
  tileStats: {
    display: "flex", justifyContent: "space-between", marginTop: 8,
    color: "#7090b0", fontSize: 12.5,
  },
  emergencyBanner: { maxWidth: 1100, margin: "0 auto 16px", background: "#b00020", color: "#fff", fontWeight: 900, padding: "14px 20px", borderRadius: 10, fontSize: 16 },
  ambOn: { marginTop: 8, background: "#b00020", color: "#fff", fontWeight: 800, padding: "7px 10px", borderRadius: 6, fontSize: 12.5 },
  ambOff: { marginTop: 8, background: "rgba(255,255,255,0.04)", color: "#5a7090", padding: "7px 10px", borderRadius: 6, fontSize: 12 },
  controllerBar: {
    maxWidth: 1100, margin: "20px auto 0", display: "flex", gap: 20, flexWrap: "wrap",
    background: "rgba(0,255,135,0.05)", border: "1px solid rgba(0,255,135,0.2)",
    borderRadius: 10, padding: "12px 18px", color: "#c0d8f0", fontSize: 13,
  },
  controllerItem: { display: "inline-flex", alignItems: "center" },
  completeBar: {
    maxWidth: 1100, margin: "16px auto 0", display: "flex", alignItems: "center",
    justifyContent: "space-between", flexWrap: "wrap", gap: 12,
    background: "rgba(0,180,255,0.06)", border: "1px solid rgba(0,180,255,0.25)",
    borderRadius: 10, padding: "14px 18px", color: "#c0d8f0", fontSize: 13.5,
  },
  reportBtn: {
    padding: "10px 22px", background: "linear-gradient(135deg, #00ff87, #00b4ff)",
    border: "none", borderRadius: 8, color: "#0a0f1e", fontWeight: 800,
    fontSize: 13, cursor: "pointer",
  },
  ambMaybe: { marginTop: 8, background: "rgba(255,211,42,0.15)", color: "#ffd32a", padding: "7px 10px", borderRadius: 6, fontSize: 12.5 },
  hint: {
    maxWidth: 1100, margin: "18px auto 0", color: "#3a5070",
    fontSize: 12.5, textAlign: "center", lineHeight: 1.6,
  },
  error: {
    maxWidth: 1100, margin: "0 auto 16px", color: "#ff6b6b", fontSize: 13,
    background: "rgba(255,107,107,0.08)", padding: "10px 20px", borderRadius: 8,
  },
  videoWrap: { position: "relative" },
  lightOverlay: { position: "absolute", top: 8, right: 8, display: "flex", flexDirection: "column", gap: 4, background: "rgba(0,0,0,0.65)", padding: 5, borderRadius: 8 },
  lamp: { width: 13, height: 13, borderRadius: "50%", display: "block" },
  ambOverlay: { position: "absolute", top: 8, left: 8, background: "#d90429", color: "#fff", fontWeight: 900, padding: "4px 9px", borderRadius: 6, fontSize: 12 },
  waitOverlay: { position: "absolute", bottom: 8, left: 8, background: "rgba(0,0,0,0.7)", color: "#ffd32a", padding: "3px 9px", borderRadius: 6, fontSize: 11.5 },
  playerBar: { maxWidth: 1100, margin: "16px auto 0", display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", background: "rgba(255,255,255,0.03)", border: "1px solid #1e2d4a", borderRadius: 10, padding: "10px 16px" },
  playBtn: { padding: "7px 16px", borderRadius: 6, border: "1px solid #1e6fa0", background: "rgba(0,180,255,0.12)", color: "#cfe9ff", fontWeight: 700, fontSize: 12.5, cursor: "pointer" },
  timeLabel: { color: "#8fb0d0", fontSize: 12.5, whiteSpace: "nowrap" },
  waitNote: { maxWidth: 1100, margin: "10px auto 0", color: "#ffd32a", background: "rgba(255,211,42,0.08)", padding: "8px 14px", borderRadius: 8, fontSize: 12.5 },
  tlWrap: { maxWidth: 1100, margin: "16px auto 0", background: "rgba(255,255,255,0.02)", border: "1px solid #1e2d4a", borderRadius: 10, padding: "12px 16px" },
  tlTitle: { color: "#5a7090", fontSize: 10.5, letterSpacing: 1.5, marginBottom: 8, fontWeight: 800 },
  tlRow: { display: "flex", alignItems: "center", gap: 8, marginBottom: 5 },
  tlLabel: { width: 46, fontSize: 11.5, fontWeight: 800 },
  playhead: { position: "absolute", top: -2, bottom: -2, width: 2, background: "#fff", pointerEvents: "none" },
  tlLegend: { display: "flex", gap: 16, marginTop: 8, fontSize: 11.5 },
};
