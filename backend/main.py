import os, sqlite3, json, re
import logging
from datetime import datetime
from typing import Optional
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fham-ai")
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_DIR=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.getenv("DB_PATH", os.path.join(APP_DIR,"fham.db"))
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY","").strip()
OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-4o-mini").strip()
FRONTEND_ORIGIN=os.getenv("FRONTEND_ORIGIN","*").strip()

app=FastAPI(title="FHAM AI", version="4.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"] if FRONTEND_ORIGIN=="*" else [FRONTEND_ORIGIN],
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

def conn():
    c=sqlite3.connect(DB_PATH)
    c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS chats(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT,role TEXT,content TEXT,created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS profiles(
        user_id TEXT PRIMARY KEY,display_name TEXT DEFAULT '',language TEXT DEFAULT 'fa' )""")
    c.commit()
    return c

class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1,max_length=200)
    message: str = Field(min_length=1,max_length=8000)
    language: str = Field(default="fa",max_length=10)
    mode: str = Field(default="professional",max_length=30)

class ProfileRequest(BaseModel):
    display_name: str = Field(default="",max_length=100)
    language: str = Field(default="fa",max_length=10)

def demo_answer(message, language, mode):
    if language=="en":
        return {"answer":f"I received your request: “{message}”. FHAM AI is running in Demo Mode. Add OPENAI_API_KEY on the backend to enable real AI answers.",
                "mode":mode,"demo":True}
    if language=="ps":
        return {"answer":f"ستاسې غوښتنه ترلاسه شوه: «{message}». FHAM AI اوس په Demo Mode کې دی. د ریښتیني AI ځوابونو لپاره په Backend کې OPENAI_API_KEY تنظیم کړئ.",
                "mode":mode,"demo":True}
    return {"answer":f"درخواست شما دریافت شد: «{message}».\n\nFHAM AI در حال حاضر در حالت Demo اجرا می‌شود. برای پاسخ‌های واقعی هوش مصنوعی، باید OPENAI_API_KEY فقط در Backend تنظیم شود.",
            "mode":mode,"demo":True}
  def ai_answer(message, language, mode, history):
    from openai import OpenAI

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    client = OpenAI(api_key=OPENAI_API_KEY)

    lang = {
        "fa": "Dari/Persian",
        "ps": "Pashto",
        "en": "English"
    }.get(language, "Dari/Persian")

    system = f"""
You are FHAM AI, a careful educational and general-purpose AI assistant.

Answer in {lang}.

Be accurate, structured, practical, and honest about uncertainty.
Do not invent facts, citations, sources, or credentials.
For current information, clearly state when live verification is needed.

Response mode: {mode}.

If the user asks for teaching, explain step-by-step and provide examples.
Use clear language and local context when relevant.
"""

    messages = [
        {
            "role": "system",
            "content": system
        }
    ]

    for item in history[-10:]:
        messages.append({
            "role": item["role"],
            "content": item["content"]
        })

    messages.append({
        "role": "user",
        "content": message
    })

    logger.info(
        "Sending request to OpenAI: model=%s",
        OPENAI_MODEL
    )

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=messages
    )

    answer = response.output_text

    if not answer:
        raise RuntimeError("OpenAI returned an empty response")

    logger.info("OpenAI response received successfully")

    return answer
@app.get("/api/health")
def health():
    return {"ok":True,"service":"FHAM AI","version":"4.0.0","ai_configured":bool(OPENAI_API_KEY)}

@app.get("/api/profile/{user_id}")
def profile(user_id:str):
    c=conn()
    c.execute("INSERT OR IGNORE INTO profiles(user_id) VALUES(?)",(user_id,))
    p=c.execute("SELECT * FROM profiles WHERE user_id=?",(user_id,)).fetchone()
    c.commit(); c.close()
    return dict(p)

@app.post("/api/profile/{user_id}")
def update_profile(user_id:str, req:ProfileRequest):
    c=conn()
    c.execute("INSERT OR IGNORE INTO profiles(user_id) VALUES(?)",(user_id,))
    c.execute("UPDATE profiles SET display_name=?,language=? WHERE user_id=?",(req.display_name,req.language,user_id))
    c.commit(); p=c.execute("SELECT * FROM profiles WHERE user_id=?",(user_id,)).fetchone(); c.close()
    return dict(p)

@app.get("/api/history/{user_id}")
def history(user_id:str):
    c=conn()
    rows=c.execute("SELECT role,content,created_at FROM chats WHERE user_id=? ORDER BY id DESC LIMIT 50",(user_id,)).fetchall()
    c.close()
    return [dict(x) for x in reversed(rows)]

@app.post("/api/chat")
def chat(req: ChatRequest):
    c = conn()

    rows = c.execute(
        "SELECT role,content FROM chats WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (req.user_id,)
    ).fetchall()

    history = list(reversed(rows))

    if OPENAI_API_KEY:
        try:
            answer = ai_answer(
                req.message,
                req.language,
                req.mode,
                history
            )
            demo = False

        except Exception:
            logger.exception("OpenAI request failed")
            answer = (
                demo_answer(
                    req.message,
                    req.language,
                    req.mode
                )["answer"]
                + "\n\nخطا در اتصال به سرویس AI؛ تنظیمات Backend را بررسی کنید."
            )
            demo = True

    else:
        logger.error("OPENAI_API_KEY is not configured")
        answer = demo_answer(
            req.message,
            req.language,
            req.mode
        )["answer"]
        demo = True

    now = datetime.utcnow().isoformat()

    c.execute(
        "INSERT INTO chats(user_id,role,content,created_at) VALUES(?,?,?,?)",
        (req.user_id, "user", req.message, now)
    )

    c.execute(
        "INSERT INTO chats(user_id,role,content,created_at) VALUES(?,?,?,?)",
        (req.user_id, "assistant", answer, datetime.utcnow().isoformat())
    )

    c.commit()
    c.close()

    return {
        "answer": answer,
        "mode": req.mode,
        "demo": demo
    }

app.mount("/",StaticFiles(directory=os.path.join(os.path.dirname(APP_DIR),"frontend"),html=True),name="frontend")
