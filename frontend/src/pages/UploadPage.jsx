import { useState, useRef } from "react";
import { startLaneVideoSession } from "../api/traffic";

const LANES = ["North", "South", "East", "West"];
const LANE_ICON = { North: "⬆️", South: "⬇️", East: "➡️", West: "⬅️" };
const LANE_COLOR = { North: "#00b4ff", South: "#00ff87", East: "#ffd32a", West: "#ff6b81" };

const S = {
  page: {
    minHeight: "calc(100vh - 70px)",
    display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center",
    padding: "40px 20px",
    background: "radial-gradient(ellipse at 50% 0%, #0d2040 0%, #0a0f1e 70%)",
  },
  title: {
    fontSize: "clamp(28px, 5vw, 52px)", fontWeight: 900,
    color: "#e0f0ff", textAlign: "center", marginBottom: 8,
    letterSpacing: -1,
  },
  sub: { color: "#4a7090", fontSize: 15, textAlign: "center", marginBottom: 16, maxWidth: 620 },
  hint: { color: "#3a5070", fontSize: 12, textAlign: "center", marginBottom: 40, maxWidth: 620, lineHeight: 1.6 },
  grid: {
    display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16,
    width: "100%", maxWidth: 680,
  },
  dropzone: (drag, color, hasFile) => ({
    border: `2px dashed ${drag ? color : hasFile ? color + "88" : "#1e3a5a"}`,
    borderRadius: 14, padding: "28px 16px",
    textAlign: "center", cursor: "pointer",
    background: drag ? `${color}0c` : hasFile ? `${color}08` : "rgba(255,255,255,0.02)",
    transition: "all 0.2s",
    minHeight: 150,
    display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
  }),
  laneLabel: (color) => ({
    fontSize: 11, fontWeight: 800, letterSpacing: 2, color, marginBottom: 8, textTransform: "uppercase",
  }),
  btn: (disabled) => ({
    marginTop: 28, padding: "14px 48px",
    background: disabled
      ? "linear-gradient(135deg, #1e3a5a, #1e3a5a)"
      : "linear-gradient(135deg, #00ff87, #00b4ff)",
    border: "none", borderRadius: 10, cursor: disabled ? "not-allowed" : "pointer",
    color: disabled ? "#4a7090" : "#0a0f1e",
    fontWeight: 800, fontSize: 15, letterSpacing: 1,
    width: "100%", maxWidth: 680, transition: "all 0.2s",
  }),
  progress: {
    width: "100%", maxWidth: 680, marginTop: 16,
    height: 4, background: "#1e2d4a", borderRadius: 2, overflow: "hidden",
  },
  bar: (pct) => ({
    height: "100%", width: `${pct}%`,
    background: "linear-gradient(90deg, #00ff87, #00b4ff)",
    transition: "width 0.3s", borderRadius: 2,
  }),
  error: {
    marginTop: 16, color: "#ff6b6b", fontSize: 13,
    background: "rgba(255,107,107,0.08)", padding: "10px 20px",
    borderRadius: 8, maxWidth: 680, textAlign: "center",
  },
  steps: {
    display: "flex", gap: 32, marginTop: 64,
    flexWrap: "wrap", justifyContent: "center",
  },
  step: {
    textAlign: "center", color: "#4a7090", fontSize: 13, maxWidth: 130,
  },
};

export default function UploadPage({ startLiveSession, setPage }) {
  const [files, setFiles] = useState({ North: null, South: null, East: null, West: null });
  const [dragLane, setDragLane] = useState(null);
  const [progress, setProgress] = useState(0);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const inputRefs = { North: useRef(), South: useRef(), East: useRef(), West: useRef() };

  const handleFile = (lane, f) => {
    if (!f) return;
    if (!f.type.startsWith("video/")) { setError(`${lane} file must be a video`); return; }
    if (f.size > 500 * 1024 * 1024) { setError(`${lane} file too large (max 500MB)`); return; }
    setFiles((prev) => ({ ...prev, [lane]: f }));
    setError("");
  };

  const providedCount = Object.values(files).filter(Boolean).length;

  const handleSubmit = async () => {
    if (providedCount === 0) return;
    setLoading(true); setError(""); setProgress(0);

    try {
      setStatus("Uploading lane videos...");
      const res = await startLaneVideoSession(files, (pct) => {
        setProgress(pct);
        if (pct === 100) setStatus("Starting live analysis...");
      });
      // Hand off immediately -- the live page starts playing these files
      // locally and streaming decisions the moment it mounts, it does not
      // wait for AI processing to finish.
      startLiveSession(res.data.session_id, files);
      setPage("live");
    } catch (e) {
      setError(e.response?.data?.detail || "Something went wrong. Is the backend running?");
      setLoading(false); setStatus("");
    }
  };

  return (
    <div style={S.page}>
      <h1 style={S.title}>Traffic Signal AI</h1>
      <p style={S.sub}>Upload one video per direction → AI detects vehicles per lane → Smart signal decisions</p>
      <p style={S.hint}>
        Each direction should be its own camera footage of that specific approach road —
        not one wide shot cropped into quadrants. Upload at least one lane; any lane left
        empty is treated as having no traffic.
      </p>

      <div style={S.grid}>
        {LANES.map((lane) => {
          const color = LANE_COLOR[lane];
          const file = files[lane];
          const isDrag = dragLane === lane;
          return (
            <div
              key={lane}
              style={S.dropzone(isDrag, color, !!file)}
              onDragOver={(e) => { e.preventDefault(); setDragLane(lane); }}
              onDragLeave={() => setDragLane(null)}
              onDrop={(e) => { e.preventDefault(); setDragLane(null); handleFile(lane, e.dataTransfer.files[0]); }}
              onClick={() => inputRefs[lane].current.click()}
            >
              <input ref={inputRefs[lane]} type="file" accept="video/*" style={{ display: "none" }}
                onChange={(e) => handleFile(lane, e.target.files[0])} />
              <div style={S.laneLabel(color)}>{LANE_ICON[lane]} {lane} Lane</div>
              {file ? (
                <>
                  <div style={{ color, fontWeight: 700, fontSize: 14, wordBreak: "break-all", textAlign: "center" }}>
                    {file.name}
                  </div>
                  <div style={{ color: "#4a7090", fontSize: 12, marginTop: 4 }}>
                    {(file.size / (1024 * 1024)).toFixed(1)} MB
                  </div>
                </>
              ) : (
                <div style={{ color: "#3a5070", fontSize: 13 }}>
                  Drop {lane} video or click
                </div>
              )}
            </div>
          );
        })}
      </div>

      {loading && (
        <div style={S.progress}>
          <div style={S.bar(progress)} />
        </div>
      )}
      {status && <div style={{ color: "#00b4ff", fontSize: 13, marginTop: 8 }}>{status}</div>}
      {error && <div style={S.error}>⚠️ {error}</div>}

      <button style={S.btn(loading || providedCount === 0)} onClick={handleSubmit}
        disabled={loading || providedCount === 0}>
        {loading ? "Processing..." : `Analyze Traffic (${providedCount}/4 lanes) →`}
      </button>

      <div style={S.steps}>
        {[
          ["📤", "Upload Per Lane", "One video per direction"],
          ["🤖", "AI Detection", "YOLOv8 counts vehicles per lane"],
          ["🚦", "Signal Logic", "4-way adaptive timing"],
          ["📊", "Results", "Stats + annotated videos"],
        ].map(([icon, title, desc]) => (
          <div key={title} style={S.step}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>{icon}</div>
            <div style={{ color: "#7090b0", fontWeight: 700, fontSize: 13 }}>{title}</div>
            <div style={{ marginTop: 4 }}>{desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
