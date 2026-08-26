import os
import sqlite3
import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger("fham-ai")


# =========================================================
# ENVIRONMENT
# =========================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(APP_DIR, "fham.db")
)

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
).strip()

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile"
).strip()

FRONTEND_ORIGIN = os.getenv(
    "FRONTEND_ORIGIN",
    "*"
).strip()


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title="FHAM AI",
    description="FHAM AI educational and general-purpose assistant",
    version="5.0.0"
)


# =========================================================
# CORS
# =========================================================

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
# DATABASE
# =========================================================

def conn():
    connection = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chats(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
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
# REQUEST MODELS
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
# TIME
# =========================================================

def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# DEMO RESPONSE
# =========================================================

def demo_answer(
    message,
    language,
    mode,
    reason="AI service is unavailable."
):

    if language == "en":

        text = (
            f'I received your request: "{message}".\n\n'
            "FHAM AI could not generate a live AI response "
            "because the AI service is currently unavailable."
        )

    elif language == "ps":

        text = (
            f'ستاسې غوښتنه ترلاسه شوه: «{message}».\n\n'
            "FHAM AI اوس مهال د AI خدمت څخه ریښتینی ځواب "
            "نه شي ترلاسه کولی."
        )

    else:

        text = (
            f'درخواست شما دریافت شد: «{message}».\n\n'
            "FHAM AI در حال حاضر نتوانست پاسخ واقعی "
            "هوش مصنوعی را دریافت کند."
        )

    return {
        "answer": text,
        "mode": mode,
        "demo": True,
        "reason": reason
    }


# =========================================================
# GROQ AI
# =========================================================

def ai_answer(
    message,
    language,
    mode,
    history
):

    if not GROQ_API_KEY:

        logger.error(
            "GROQ_API_KEY is not configured."
        )

        raise RuntimeError(
            "GROQ_API_KEY is not configured"
        )

    from groq import Groq

    client = Groq(
        api_key=GROQ_API_KEY
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
You are FHAM AI, a professional, helpful,
educational and general-purpose AI assistant.

Answer in {language_name}.

Your responsibilities:

1. Give accurate and useful answers.
2. Explain difficult subjects clearly.
3. Use structured responses when appropriate.
4. For educational questions, teach step-by-step.
5. Give examples when they improve understanding.
6. Never invent facts, sources, citations,
   credentials or personal experiences.
7. If you are uncertain, say so clearly.
8. Do not claim that you accessed the internet
   unless a web-search tool was actually used.
9. For current information, explain that
   live verification may be required.
10. Be respectful and professional.
11. When relevant, consider the user's
    Afghanistan/Dari/Pashto context.

Current response mode:
{mode}
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    # -----------------------------------------------------
    # Conversation history
    # -----------------------------------------------------

    for item in history[-10:]:

        role = item["role"]

        if role not in (
            "user",
            "assistant"
        ):
            continue

        content = item["content"]

        if not content:
            continue

        messages.append(
            {
                "role": role,
                "content": content
            }
        )

    # -----------------------------------------------------
    # Current message
    # -----------------------------------------------------

    messages.append(
        {
            "role": "user",
            "content": message
        }
    )

    logger.info(
        "Sending request to Groq. model=%s",
        GROQ_MODEL
    )

    try:

        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.25,
            max_tokens=2048
        )

    except Exception:

        logger.exception(
            "Groq API request failed."
        )

        raise

    if not completion.choices:

        logger.error(
            "Groq returned no choices."
        )

        raise RuntimeError(
            "Groq returned no choices"
        )

    answer = (
        completion
        .choices[0]
        .message
        .content
    )

    if not answer:

        logger.error(
            "Groq returned an empty response."
        )

        raise RuntimeError(
            "Groq returned an empty response"
        )

    logger.info(
        "Groq response received successfully."
    )

    return answer


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():

    return {
        "ok": True,
        "service": "FHAM AI",
        "version": "5.0.0",
        "provider": "groq",
        "ai_configured": bool(GROQ_API_KEY),
        "model": GROQ_MODEL
    }


# =========================================================
# PROFILE GET
# =========================================================

@app.get("/api/profile/{user_id}")
def profile(user_id: str):

    connection = conn()

    connection.execute(
        """
        INSERT OR IGNORE INTO profiles(
            user_id
        )
        VALUES(?)
        """,
        (user_id,)
    )

    row = connection.execute(
        """
        SELECT *
        FROM profiles
        WHERE user_id=?
        """,
        (user_id,)
    ).fetchone()

    connection.commit()
    connection.close()

    return dict(row)


# =========================================================
# PROFILE UPDATE
# =========================================================

@app.post("/api/profile/{user_id}")
def update_profile(
    user_id: str,
    req: ProfileRequest
):

    connection = conn()

    connection.execute(
        """
        INSERT OR IGNORE INTO profiles(
            user_id
        )
        VALUES(?)
        """,
        (user_id,)
    )

    connection.execute(
        """
        UPDATE profiles
        SET
            display_name=?,
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

    row = connection.execute(
        """
        SELECT *
        FROM profiles
        WHERE user_id=?
        """,
        (user_id,)
    ).fetchone()

    connection.close()

    return dict(row)


# =========================================================
# CHAT HISTORY
# =========================================================

@app.get("/api/history/{user_id}")
def history(user_id: str):

    connection = conn()

    rows = connection.execute(
        """
        SELECT
            role,
            content,
            created_at
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
# CHAT
# =========================================================

@app.post("/api/chat")
def chat(req: ChatRequest):

    connection = conn()

    try:

        rows = connection.execute(
            """
            SELECT
                role,
                content
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

        # -------------------------------------------------
        # AI
        # -------------------------------------------------

        try:

            answer = ai_answer(
                message=req.message,
                language=req.language,
                mode=req.mode,
                history=history_rows
            )

            demo = False
            reason = None

        except Exception as error:

            logger.exception(
                "AI request failed: %s",
                error
            )

            fallback = demo_answer(
                req.message,
                req.language,
                req.mode,
                reason=str(error)
            )

            answer = fallback["answer"]
            demo = True
            reason = str(error)

        # -------------------------------------------------
        # Save user message
        # -------------------------------------------------

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
                utc_now()
            )
        )

        # -------------------------------------------------
        # Save assistant message
        # -------------------------------------------------

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
                utc_now()
            )
        )

        connection.commit()

        return {
            "answer": answer,
            "mode": req.mode,
            "demo": demo,
            "provider": "groq",
            "model": GROQ_MODEL,
            "error": reason
        }

    finally:

        connection.close()


# =========================================================
# FRONTEND
# =========================================================

frontend_directory = os.path.abspath(
    os.path.join(
        APP_DIR,
        "..",
        "frontend"
    )
)

if os.path.isdir(frontend_directory):

    logger.info(
        "Frontend found: %s",
        frontend_directory
    )

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
