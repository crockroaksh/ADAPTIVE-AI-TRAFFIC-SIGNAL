import { useEffect, useState } from "react";
import { getHistory } from "../api/traffic";

export default function HistoryPage({ setResult, setPage }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getHistory()
      .then(res => setHistory(res.data.history))
      .catch(() => setError("Could not load history"))
      .finally(() => setLoading(false));
  }, []);

  const viewResult = (record) => {
    setResult(record);
    setPage("result");
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "40px 20px" }}>
      <h1 style={{ color: "#e0f0ff", fontSize: 28, fontWeight: 900, marginBottom: 8 }}>
        Analysis History
      </h1>
      <p style={{ color: "#4a7090", fontSize: 14, marginBottom: 32 }}>
        Past traffic video analyses
      </p>

      {loading && <div style={{ color: "#4a7090", textAlign: "center", padding: 60 }}>Loading...</div>}
      {error && <div style={{ color: "#ff6b6b", textAlign: "center" }}>{error}</div>}

      {!loading && history.length === 0 && (
        <div style={{ textAlign: "center", padding: 60, color: "#4a7090" }}>
          No analyses yet.{" "}
          <button onClick={() => setPage("upload")} style={linkBtn}>Upload your first video</button>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {history.map(record => (
          <div key={record.id} style={{
            background: "rgba(255,255,255,0.02)", border: "1px solid #1e2d4a",
            borderRadius: 12, padding: "20px 24px",
            display: "flex", alignItems: "center", justifyContent: "space-between",
            flexWrap: "wrap", gap: 12,
          }}>
            <div>
              <div style={{ color: "#e0f0ff", fontWeight: 700, fontSize: 15 }}>
                {record.filename}
              </div>
              <div style={{ color: "#4a7090", fontSize: 12, marginTop: 4 }}>
                {new Date(record.created_at).toLocaleString()} · {record.total_vehicles} vehicles detected
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                {record.signal_decisions && Object.entries(record.signal_decisions).map(([lane, d]) => (
                  <span key={lane} style={{
                    fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 4,
                    background: d.signal === "GREEN" ? "#00ff8718" : "#ff475718",
                    color: d.signal === "GREEN" ? "#00ff87" : "#ff4757",
                    border: `1px solid ${d.signal === "GREEN" ? "#00ff8730" : "#ff475730"}`,
                  }}>
                    {lane} {d.signal}
                  </span>
                ))}
              </div>
            </div>
            <button onClick={() => viewResult(record)} style={{
              padding: "10px 24px", borderRadius: 8, border: "none",
              background: "linear-gradient(135deg, #00ff87, #00b4ff)",
              color: "#0a0f1e", fontWeight: 800, fontSize: 12,
              cursor: "pointer", letterSpacing: 1,
            }}>
              VIEW →
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

const linkBtn = {
  background: "none", border: "none", color: "#00b4ff",
  cursor: "pointer", fontSize: 14, textDecoration: "underline",
};
