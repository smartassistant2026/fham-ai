import os
import sqlite3
import logging
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# =========================================================
# Logging
# =========================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fham-ai")


# =========================================================
# Environment
# =========================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(APP_DIR, "fham.db")
)

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    ""
).strip()

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-4o-mini"
).strip()

FRONTEND_ORIGIN = os.getenv(
    "FRONTEND_ORIGIN",
    "*"
).strip()


# =========================================================
# FastAPI
# =========================================================

app = FastAPI(
    title="FHAM AI",
    version="4.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        ["*"]
        if FRONTEND_ORIGIN == "*"
        else [FRONTEND_ORIGIN]
    ),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# Database
# =========================================================

def conn():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chats(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles(
            user_id TEXT PRIMARY KEY,
            display_name TEXT DEFAULT '',
            language TEXT DEFAULT 'fa'
        )
        """
    )

    connection.commit()

    return connection


# =========================================================
# Request Models
# =========================================================

class ChatRequest(BaseModel):
    user_id: str = Field(
        min_length=1,
        max_length=200
    )

    message: str = Field(
        min_length=1,
        max_length=8000
    )

    language: str = Field(
        default="fa",
        max_length=10
    )

    mode: str = Field(
        default="professional",
        max_length=30
    )


class ProfileRequest(BaseModel):
    display_name: str = Field(
        default="",
        max_length=100
    )

    language: str = Field(
        default="fa",
        max_length=10
    )


# =========================================================
# Demo Response
# =========================================================

def demo_answer(message, language, mode):

    if language == "en":
        text = (
            f'I received your request: "{message}".\n\n'
            "FHAM AI could not connect to the AI service. "
            "Please check the backend configuration."
        )

    elif language == "ps":
        text = (
            f'ستاسې غوښتنه ترلاسه شوه: «{message}».\n\n'
            "FHAM AI د AI خدمت سره وصل نه شو. "
            "مهرباني وکړئ د Backend تنظیمات وګورئ."
        )

    else:
        text = (
            f'درخواست شما دریافت شد: «{message}».\n\n'
            "FHAM AI نتوانست به سرویس هوش مصنوعی متصل شود. "
            "لطفاً تنظیمات Backend را بررسی کنید."
        )

    return {
        "answer": text,
        "mode": mode,
        "demo": True
    }


# =========================================================
# OpenAI AI Response
# =========================================================

def ai_answer(message, language, mode, history):

    if not OPENAI_API_KEY:
        logger.error(
            "OPENAI_API_KEY is not configured."
        )

        raise RuntimeError(
            "OPENAI_API_KEY is not configured"
        )

    from openai import OpenAI

    client = OpenAI(
        api_key=OPENAI_API_KEY
    )

    language_name = {
        "fa": "Dari/Persian",
        "ps": "Pashto",
        "en": "English"
    }.get(
        language,
        "Dari/Persian"
    )

    system_prompt = f"""
You are FHAM AI, a professional educational
and general-purpose AI assistant.

Answer in {language_name}.

Be accurate, clear, structured, useful,
and honest about uncertainty.

Do not invent facts, citations, sources,
credentials, or personal experiences.

If information may have changed recently,
clearly explain that current verification
may be required.

Mode: {mode}.

When teaching something, explain it
step-by-step and provide examples.

Use clear language and Afghanistan-relevant
context when it is useful.
"""

    input_messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    for item in history[-10:]:

        role = item["role"]

        if role not in ["user", "assistant"]:
            continue

        input_messages.append(
            {
                "role": role,
                "content": item["content"]
            }
        )

    input_messages.append(
        {
            "role": "user",
            "content": message
        }
    )

    logger.info(
        "Sending request to OpenAI. Model=%s",
        OPENAI_MODEL
    )

    try:

        response = client.responses.create(
            model=OPENAI_MODEL,
            input=input_messages
        )

    except Exception:

        logger.exception(
            "OpenAI API request failed."
        )

        raise

    answer = getattr(
        response,
        "output_text",
        None
    )

    if not answer:

        logger.error(
            "OpenAI returned an empty response."
        )

        raise RuntimeError(
            "OpenAI returned an empty response"
        )

    logger.info(
        "OpenAI response received successfully."
    )

    return answer


# =========================================================
# Health Check
# =========================================================

@app.get("/api/health")
def health():

    return {
        "ok": True,
        "service": "FHAM AI",
        "version": "4.0.0",
        "ai_configured": bool(
            OPENAI_API_KEY
        ),
        "model": OPENAI_MODEL
    }


# =========================================================
# Profile
# =========================================================

@app.get("/api/profile/{user_id}")
def profile(user_id: str):

    connection = conn()

    connection.execute(
        """
        INSERT OR IGNORE INTO profiles(user_id)
        VALUES(?)
        """,
        (user_id,)
    )

    profile_row = connection.execute(
        """
        SELECT *
        FROM profiles
        WHERE user_id=?
        """,
        (user_id,)
    ).fetchone()

    connection.commit()
    connection.close()

    return dict(profile_row)


@app.post("/api/profile/{user_id}")
def update_profile(
    user_id: str,
    req: ProfileRequest
):

    connection = conn()

    connection.execute(
        """
        INSERT OR IGNORE INTO profiles(user_id)
        VALUES(?)
        """,
        (user_id,)
    )

    connection.execute(
        """
        UPDATE profiles
        SET display_name=?,
            language=?
        WHERE user_id=?
        """,
        (
            req.display_name,
            req.language,
            user_id
        )
    )

    connection.commit()

    profile_row = connection.execute(
        """
        SELECT *
        FROM profiles
        WHERE user_id=?
        """,
        (user_id,)
    ).fetchone()

    connection.close()

    return dict(profile_row)


# =========================================================
# Chat History
# =========================================================

@app.get("/api/history/{user_id}")
def history(user_id: str):

    connection = conn()

    rows = connection.execute(
        """
        SELECT role, content, created_at
        FROM chats
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 50
        """,
        (user_id,)
    ).fetchall()

    connection.close()

    return [
        dict(row)
        for row in reversed(rows)
    ]


# =========================================================
# Chat
# =========================================================

@app.post("/api/chat")
def chat(req: ChatRequest):

    connection = conn()

    rows = connection.execute(
        """
        SELECT role, content
        FROM chats
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 10
        """,
        (req.user_id,)
    ).fetchall()

    history_rows = list(
        reversed(rows)
    )

    # -----------------------------------------------------
    # Try real AI
    # -----------------------------------------------------

    if OPENAI_API_KEY:

        try:

            answer = ai_answer(
                req.message,
                req.language,
                req.mode,
                history_rows
            )

            demo = False

        except Exception as error:

            logger.exception(
                "OpenAI request failed: %s",
                error
            )

            answer = (
                demo_answer(
                    req.message,
                    req.language,
                    req.mode
                )["answer"]
                +
                "\n\n"
                +
                "خطا در اتصال به سرویس AI. "
                "جزئیات خطا در Application Logs ثبت شده است."
            )

            demo = True

    else:

        logger.error(
            "OPENAI_API_KEY is missing."
        )

        answer = demo_answer(
            req.message,
            req.language,
            req.mode
        )["answer"]

        demo = True

    # -----------------------------------------------------
    # Save conversation
    # -----------------------------------------------------

    now = datetime.utcnow().isoformat()

    connection.execute(
        """
        INSERT INTO chats(
            user_id,
            role,
            content,
            created_at
        )
        VALUES(?,?,?,?)
        """,
        (
            req.user_id,
            "user",
            req.message,
            now
        )
    )

    connection.execute(
        """
        INSERT INTO chats(
            user_id,
            role,
            content,
            created_at
        )
        VALUES(?,?,?,?)
        """,
        (
            req.user_id,
            "assistant",
            answer,
            datetime.utcnow().isoformat()
        )
    )

    connection.commit()
    connection.close()

    return {
        "answer": answer,
        "mode": req.mode,
        "demo": demo
    }


# =========================================================
# Frontend
# =========================================================

frontend_directory = os.path.join(
    os.path.dirname(APP_DIR),
    "frontend"
)

if os.path.isdir(frontend_directory):

    app.mount(
        "/",
        StaticFiles(
            directory=frontend_directory,
            html=True
        ),
        name="frontend"
    )

else:

    logger.warning(
        "Frontend directory not found: %s",
        frontend_directory
    )
