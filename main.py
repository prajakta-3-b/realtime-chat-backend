from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import os
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

# Load env variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()


@app.get("/")
async def home():
    return {"message": "Backend running successfully"}


# ---------- Helper functions ----------

def save_session_if_not_exists(session_id: str):
    res = supabase.table("sessions") \
        .select("session_id") \
        .eq("session_id", session_id) \
        .limit(1) \
        .execute()

    if not res.data:
        supabase.table("sessions").insert({
            "session_id": session_id
        }).execute()


def save_event(session_id: str, role: str, message: str):
    supabase.table("event_logs").insert({
        "session_id": session_id,
        "role": role,
        "message": message
    }).execute()


def generate_summary(messages: list[str]) -> str:
    if not messages:
        return "No conversation."
    return f"Conversation had {len(messages)} messages."


def finalize_session(session_id: str, summary: str):
    res = supabase.table("sessions") \
        .select("start_time") \
        .eq("session_id", session_id) \
        .limit(1) \
        .execute()

    start_time = res.data[0]["start_time"] if res.data else None
    end_time = datetime.utcnow()

    duration = None
    if start_time:
        duration = int(
            (end_time - datetime.fromisoformat(start_time.replace("Z", "")))
            .total_seconds()
        )

    supabase.table("sessions").update({
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,
        "summary": summary
    }).eq("session_id", session_id).execute()


# ---------- WebSocket ----------

@app.websocket("/ws/session/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    print("Client connected:", session_id)

    # insert session only once
    save_session_if_not_exists(session_id)

    try:
        while True:
            data = await websocket.receive_text()

            save_event(session_id, "user", data)

            reply = f"Received: {data}"
            save_event(session_id, "assistant", reply)

            await websocket.send_text(reply)

    except WebSocketDisconnect:
        print("Client disconnected:", session_id)

        logs = supabase.table("event_logs") \
            .select("message") \
            .eq("session_id", session_id) \
            .execute()

        messages = [row["message"] for row in logs.data] if logs.data else []
        summary = generate_summary(messages)

        finalize_session(session_id, summary)
