import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const API = axios.create({ baseURL: BASE_URL });

// Kicks off a live-processing session: uploads one video per direction and
// returns almost immediately with a session_id, WITHOUT waiting for AI
// analysis to finish. `files` is an object like
// { North: File, South: File, East: File, West: File }; any missing
// direction is simply omitted (that lane is skipped by the backend).
//
// Follow this up by subscribing to the returned session with
// subscribeToTrafficEvents(session_id, handlers) to get live decisions as
// the AI produces them.
export const startLaneVideoSession = (files, onProgress) => {
  const formData = new FormData();
  const fieldNames = { North: "north_file", South: "south_file", East: "east_file", West: "west_file" };
  Object.entries(files).forEach(([lane, file]) => {
    if (file) formData.append(fieldNames[lane], file);
  });
  // The request itself only has to wait for the upload to reach the
  // backend, not for AI processing, so a short timeout is fine here.
  return API.post("/upload-video", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (e) => {
      if (onProgress) onProgress(Math.round((e.loaded * 100) / e.total));
    },
    timeout: 120000,
  });
};

// Opens a Server-Sent Events connection for a processing session and wires
// up the given handlers. Returns the EventSource so the caller can close()
// it (e.g. on unmount). Handlers is an object of:
//   onStatus(status), onDecision(decisions, esp32Push), onComplete(result),
//   onError(message)
export const subscribeToTrafficEvents = (sessionId, handlers = {}) => {
  const es = new EventSource(`${BASE_URL}/events/${sessionId}`);

  es.onmessage = (evt) => {
    let data;
    try {
      data = JSON.parse(evt.data);
    } catch {
      return;
    }
    switch (data.type) {
      case "status":
        handlers.onStatus?.(data.status, data.lane);
        break;
      case "decision":
        handlers.onDecision?.(data.decisions, data.esp32_push);
        break;
      case "complete":
        handlers.onComplete?.(data.result);
        es.close();
        break;
      case "error":
        handlers.onError?.(data.message);
        es.close();
        break;
      default:
        break;
    }
  };

  es.onerror = () => {
    // EventSource auto-retries on transient network errors; only surface
    // a hard failure if the connection is fully closed.
    if (es.readyState === EventSource.CLOSED) {
      handlers.onError?.("Live connection to the AI backend was lost.");
    }
  };

  return es;
};

// LEGACY: single wide-angle video, algorithmically split into 4 quadrants,
// still fully synchronous (waits for the whole result). Kept for backward
// compatibility; prefer startLaneVideoSession for the real-time flow.
export const uploadVideo = (file, onProgress) => {
  const formData = new FormData();
  formData.append("file", file);
  return API.post("/upload-video-legacy", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (e) => {
      if (onProgress) onProgress(Math.round((e.loaded * 100) / e.total));
    },
    timeout: 3600000,
  });
};

export const getHistory = () => API.get("/history");
export const getRecord = (id) => API.get(`/history/${id}`);

// ESP32 Hardware helpers
export const getESP32Status = () => API.get("/esp32/status");
export const resetESP32 = () => API.post("/esp32/reset");
export const syncESP32 = (signalDecisions) => API.post("/esp32/sync", { signal_decisions: signalDecisions });
