import asyncio
import json
import os
import shutil
import tempfile
import time
import uuid
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

try:
    from supabase import create_client, Client
except Exception:
    create_client = None
    Client = object

try:
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    )
except Exception:
    cloudinary = None

from vision.lane_processor import process_multi_lane_videos

app = FastAPI(title="Traffic Signal Control API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

ESP32_IP = os.getenv("ESP32_IP", "").strip()
SESSION_TTL_SECONDS = float(os.getenv("SESSION_TTL_SECONDS", "1800"))

supabase = None
if create_client and os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
    try:
        supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    except Exception as e:
        print(f"[supabase] disabled: {e}")


class SessionManager:
    def __init__(self):
        self._sessions = {}
        self._lock = asyncio.Lock()

    async def create(self, lanes):
        sid = uuid.uuid4().hex[:12]
        async with self._lock:
            self._sessions[sid] = {
                "queue": asyncio.Queue(maxsize=500), "lanes": lanes,
                "status": "processing", "created_at": time.time(),
                "finished_at": None, "last_decision": None, "result": None,
            }
        return sid

    def get(self, sid): return self._sessions.get(sid)

    def publish(self, sid, event):
        s = self._sessions.get(sid)
        if not s: return
        if event.get("type") == "decision": s["last_decision"] = event.get("decisions")
        q = s["queue"]
        try: q.put_nowait(event)
        except asyncio.QueueFull:
            try: q.get_nowait()
            except Exception: pass
            try: q.put_nowait(event)
            except Exception: pass

    def mark_complete(self, sid, result=None):
        s = self._sessions.get(sid)
        if s:
            s.update(status="complete", finished_at=time.time(), result=result)

    def mark_error(self, sid, message):
        s = self._sessions.get(sid)
        if s:
            s.update(status="error", finished_at=time.time(), error=message)

    async def sweep(self):
        now = time.time()
        async with self._lock:
            expired = [sid for sid,s in self._sessions.items() if
                       (s["finished_at"] and now-s["finished_at"] > SESSION_TTL_SECONDS) or
                       (not s["finished_at"] and now-s["created_at"] > SESSION_TTL_SECONDS*4)]
            for sid in expired: del self._sessions[sid]

sessions = SessionManager()

@app.on_event("startup")
async def startup():
    async def cleanup():
        while True:
            await asyncio.sleep(300)
            await sessions.sweep()
    asyncio.create_task(cleanup())


def _signal_params(decisions):
    out = {}
    for lane in ["North","South","East","West"]:
        d = decisions.get(lane, {})
        out[lane.lower()] = str(d.get("signal", "RED") if isinstance(d,dict) else d).upper()
    return out


def send_signal_to_esp32_sync(decisions):
    ip = os.getenv("ESP32_IP", ESP32_IP).strip()
    if not ip: return {"status":"skipped", "message":"ESP32_IP not configured"}
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"http://{ip}/traffic", params=_signal_params(decisions))
        return {"status":"success" if r.status_code == 200 else "error", "code":r.status_code}
    except Exception as e:
        print(f"[ESP32] unavailable: {e}")
        return {"status":"unavailable", "message":str(e)}

async def send_signal_to_esp32(decisions):
    return await asyncio.to_thread(send_signal_to_esp32_sync, decisions)


def reset_esp32_sync():
    ip = os.getenv("ESP32_IP", ESP32_IP).strip()
    if not ip: return {"status":"skipped", "message":"ESP32_IP not configured"}
    try:
        with httpx.Client(timeout=3.0) as client:
            r=client.get(f"http://{ip}/reset")
        return {"status":"success", "data":r.text}
    except Exception as e: return {"status":"unavailable", "message":str(e)}

@app.get("/")
def root():
    import torch
    return {"message":"Traffic Signal Control API is running", "esp32_configured":bool(ESP32_IP), "gpu_available":bool(torch.cuda.is_available())}

@app.get("/gpu-status")
def gpu_status():
    import torch
    from vision.yolo_engine import DEVICE
    mps_available = bool(getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available())
    return {
        "device_in_use": DEVICE,  # what the YOLO engine actually loaded on, including any fallback
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "mps_available": mps_available,
    }

async def run_session(session_id, temp_paths, filenames):
    try:
        sessions.publish(session_id, {"type":"status","status":"analyzing"})
        loop = asyncio.get_running_loop()

        def publish(event):
            loop.call_soon_threadsafe(sessions.publish, session_id, event)

        def esp32_push(decisions):
            return send_signal_to_esp32_sync(decisions)

        result = await asyncio.to_thread(process_multi_lane_videos, temp_paths, publish, esp32_push, filenames)

        # Save completed result without allowing database failure to affect live processing.
        if supabase:
            try:
                supabase.table("traffic_analysis").insert({
                    "filenames": filenames,
                    "lane_counts": result["lane_counts"],
                    "signal_decisions": result["signal_decisions"],
                    "segment_decisions": result["segment_decisions"],
                    "frame_data": result["frame_data"],
                    "processed_video_urls": result.get("processed_video_urls", {}),
                    "total_vehicles": result["total_vehicles"],
                }).execute()
            except Exception as e: print(f"[supabase] save failed: {e}")

        final_payload = {"success":True, "lanes_uploaded":list(temp_paths), **result}
        sessions.mark_complete(session_id, final_payload)
        sessions.publish(session_id, {"type":"complete", "result":final_payload})
    except Exception as e:
        import traceback; traceback.print_exc()
        sessions.mark_error(session_id, str(e))
        sessions.publish(session_id, {"type":"error","message":str(e)})
    finally:
        for p in temp_paths.values():
            try:
                if os.path.exists(p): os.remove(p)
            except Exception: pass

@app.post("/upload-video")
async def upload_video(north_file:Optional[UploadFile]=File(None), south_file:Optional[UploadFile]=File(None), east_file:Optional[UploadFile]=File(None), west_file:Optional[UploadFile]=File(None)):
    files={"North":north_file,"South":south_file,"East":east_file,"West":west_file}
    provided={lane:f for lane,f in files.items() if f is not None}
    if not provided: raise HTTPException(400,"Upload at least one lane video")
    for lane,f in provided.items():
        if not (f.content_type or "").startswith("video/"):
            raise HTTPException(400,f"{lane} file must be a video")
    temp_paths={}; filenames={}
    try:
        for lane,f in provided.items():
            suffix=os.path.splitext(f.filename or ".mp4")[1] or ".mp4"
            path=os.path.join(tempfile.gettempdir(), f"traffic_{uuid.uuid4().hex}{suffix}")
            with open(path,"wb") as out: shutil.copyfileobj(f.file,out)
            temp_paths[lane]=path; filenames[lane]=f.filename
    except Exception:
        for p in temp_paths.values():
            if os.path.exists(p): os.remove(p)
        raise HTTPException(500,"Failed to save uploaded video(s)")
    sid=await sessions.create(list(provided))
    asyncio.create_task(run_session(sid,temp_paths,filenames))
    return JSONResponse({"success":True,"session_id":sid,"status":"processing","lanes_uploaded":list(provided),"events_url":f"/events/{sid}"})


def _sse(event): return f"data: {json.dumps(event)}\n\n"

@app.get("/events/{session_id}")
async def events(session_id:str, request:Request):
    s=sessions.get(session_id)
    if not s: raise HTTPException(404,"Session not found or expired")
    async def gen():
        yield _sse({"type":"status","status":s["status"]})
        if s.get("last_decision"): yield _sse({"type":"decision","decisions":s["last_decision"]})
        if s["status"]=="complete" and s.get("result"):
            yield _sse({"type":"complete","result":s["result"]}); return
        if s["status"]=="error":
            yield _sse({"type":"error","message":s.get("error","Processing failed")}); return
        while True:
            if await request.is_disconnected(): return
            try: event=await asyncio.wait_for(s["queue"].get(),15)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"; continue
            yield _sse(event)
            if event.get("type") in ("complete","error"): return
    return StreamingResponse(gen(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","Connection":"keep-alive","X-Accel-Buffering":"no"})

@app.post("/esp32/sync")
async def esp32_sync(payload:dict):
    decisions=payload.get("signal_decisions",{})
    res=await send_signal_to_esp32(decisions)
    sid=payload.get("session_id")
    if sid: sessions.publish(sid,{"type":"decision","decisions":decisions,"esp32_push":res})
    return res

@app.get("/esp32/status")
async def esp32_status():
    ip=os.getenv("ESP32_IP",ESP32_IP).strip()
    if not ip: return {"connected":False,"configured":False,"ip":None}
    try:
        with httpx.Client(timeout=2.0) as c: r=c.get(f"http://{ip}/")
        return {"connected":r.status_code==200,"configured":True,"ip":ip}
    except Exception as e: return {"connected":False,"configured":True,"ip":ip,"error":str(e)}

@app.post("/esp32/reset")
async def esp32_reset(): return await asyncio.to_thread(reset_esp32_sync)

@app.get("/history")
async def history():
    if not supabase: return {"history":[]}
    try:
        return {"history":supabase.table("traffic_analysis").select("*").order("created_at",desc=True).limit(20).execute().data}
    except Exception as e: raise HTTPException(500,str(e))

@app.get("/history/{record_id}")
async def record(record_id:int):
    if not supabase: raise HTTPException(503,"Supabase is not configured")
    data=supabase.table("traffic_analysis").select("*").eq("id",record_id).execute().data
    if not data: raise HTTPException(404,"Record not found")
    return data[0]

@app.post("/upload-video-legacy")
async def upload_video_legacy(file: UploadFile = File(...)):
    if not (file.content_type or "").startswith("video/"):
        raise HTTPException(400,"File must be a video")
    path=os.path.join(tempfile.gettempdir(),f"traffic_legacy_{uuid.uuid4().hex}{os.path.splitext(file.filename or '.mp4')[1]}")
    with open(path,"wb") as out: shutil.copyfileobj(file.file,out)
    try:
        result=await asyncio.to_thread(process_multi_lane_videos,{"North":path})
        return result
    finally:
        if os.path.exists(path): os.remove(path)
