import { useState, useEffect } from "react";
import UploadPage from "./pages/UploadPage";
import LivePage from "./pages/LivePage";
import ResultPage from "./pages/ResultPage";
import HistoryPage from "./pages/HistoryPage";
import { getESP32Status, resetESP32 } from "./api/traffic";

export default function App() {
  const [page, setPage] = useState("upload");
  const [result, setResult] = useState(null);
  const [liveSession, setLiveSession] = useState(null); // { sessionId, files }

  const startLiveSession = (sessionId, files) => {
    setLiveSession({ sessionId, files });
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0a0f1e", fontFamily: "'DM Mono', monospace" }}>
      <Nav page={page} setPage={setPage} />
      {page === "upload" && <UploadPage startLiveSession={startLiveSession} setPage={setPage} />}
      {page === "live" && liveSession && (
        <LivePage
          sessionId={liveSession.sessionId}
          files={liveSession.files}
          onViewFullReport={setResult}
          setPage={setPage}
        />
      )}
      {page === "result" && <ResultPage result={result} setPage={setPage} />}
      {page === "history" && <HistoryPage setResult={setResult} setPage={setPage} />}
    </div>
  );
}

function Nav({ page, setPage }) {
  const [espStatus, setEspStatus] = useState({ checked: false, connected: false, ip: null });
  const [resetting, setResetting] = useState(false);

  const checkStatus = () => {
    getESP32Status()
      .then(res => {
        setEspStatus({
          checked: true,
          connected: Boolean(res.data.connected),
          ip: res.data.ip || null,
          configured: res.data.configured
        });
      })
      .catch(() => {
        setEspStatus({ checked: true, connected: false, ip: null, configured: false });
      });
  };

  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleResetHardware = async () => {
    setResetting(true);
    try {
      await resetESP32();
      checkStatus();
    } catch (e) {
      console.error("Hardware reset failed:", e);
    } finally {
      setResetting(false);
    }
  };

  return (
    <nav style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "16px 32px", borderBottom: "1px solid #1e2d4a",
      background: "rgba(10,15,30,0.95)", position: "sticky", top: 0, zIndex: 100,
      flexWrap: "wrap", gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8,
          background: "linear-gradient(135deg, #00ff87, #00b4ff)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 16,
        }}>🚦</div>
        <span style={{ color: "#e0f0ff", fontSize: 15, fontWeight: 700, letterSpacing: 1 }}>
          ADAPTIVE TRAFFIC AI
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        {/* ESP32 Status Pill */}
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          background: "rgba(255,255,255,0.03)", border: "1px solid #1e2d4a",
          padding: "6px 12px", borderRadius: 8, fontSize: 11, color: "#7090b0",
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: "50%",
            background: espStatus.connected ? "#00ff87" : (espStatus.configured ? "#ffd32a" : "#ff4757"),
            boxShadow: espStatus.connected ? "0 0 8px #00ff87" : "none",
            display: "inline-block",
          }} />
          <span>
            ESP32: {espStatus.connected ? `Online (${espStatus.ip})` : (espStatus.configured ? "Unreachable" : "Offline / Unset")}
          </span>
          {espStatus.connected && (
            <button
              onClick={handleResetHardware}
              disabled={resetting}
              style={{
                background: "rgba(255,71,87,0.15)",
                border: "1px solid rgba(255,71,87,0.4)",
                color: "#ff4757",
                borderRadius: 4,
                padding: "2px 6px",
                fontSize: 10,
                fontWeight: 700,
                cursor: resetting ? "not-allowed" : "pointer",
              }}
              title="Reset physical ESP32 LEDs to ALL RED safe state"
            >
              {resetting ? "Resetting..." : "Safe Reset"}
            </button>
          )}
        </div>

        {/* Page Nav Buttons */}
        <div style={{ display: "flex", gap: 8 }}>
          {[["upload","Upload Videos"],["history","History"]].map(([p, label]) => (
            <button key={p} onClick={() => setPage(p)} style={{
              padding: "8px 20px", borderRadius: 6, border: "none", cursor: "pointer",
              background: page === p ? "linear-gradient(135deg, #00ff87, #00b4ff)" : "transparent",
              color: page === p ? "#0a0f1e" : "#7090b0",
              fontWeight: 700, fontSize: 12, letterSpacing: 1,
              textTransform: "uppercase", transition: "all 0.2s",
            }}>{label}</button>
          ))}
        </div>
      </div>
    </nav>
  );
}

