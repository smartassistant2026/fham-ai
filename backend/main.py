import os
import re
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
# PATHS
# =========================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(APP_DIR, "fham.db")
)


# =========================================================
# ENVIRONMENT
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# مدل پیش‌فرض معتبر
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

raw_model = os.getenv(
    "GROQ_MODEL",
    DEFAULT_GROQ_MODEL
).strip()


def normalize_model(value: str) -> str:
    """
    پاک‌سازی مقدار مدل.
    اگر مدل به اشتباه دوبار چسبیده باشد،
    فقط یک نسخه را نگه می‌دارد.
    """

    if not value:
        return DEFAULT_GROQ_MODEL

    value = value.strip()

    # حذف quoteهای احتمالی
    value = value.strip("\"'")

    # حالت خراب:
    # llama-3.3-70b-versatilellama-3.3-70b-versatile
    doubled = DEFAULT_GROQ_MODEL + DEFAULT_GROQ_MODEL

    if value == doubled:
        logger.warning(
            "GROQ_MODEL was duplicated. Automatically corrected."
        )
        return DEFAULT_GROQ_MODEL

    # اگر چند بار پشت سر هم تکرار شده باشد
    while value.endswith(DEFAULT_GROQ_MODEL + DEFAULT_GROQ_MODEL):
        value = value[:-len(DEFAULT_GROQ_MODEL)]

    # فقط برای مدل شناخته‌شده فعلی
    if value != DEFAULT_GROQ_MODEL:
        logger.warning(
            "GROQ_MODEL value received: %s",
            value
        )

    return value


GROQ_MODEL = normalize_model(raw_model)


FRONTEND_ORIGIN = os.getenv(
    "FRONTEND_ORIGIN",
    "*"
).strip()


APP_ENV = os.getenv(
    "APP_ENV",
    "production"
).strip()


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title="FHAM AI",
    description="FHAM AI educational and general-purpose AI assistant",
    version="6.0.0"
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
# ERROR CLASSIFICATION
# =========================================================

def classify_error(error):

    text = str(error)

    lower = text.lower()

    if "model_not_found" in lower or "does not exist" in lower:
        return "MODEL_NOT_FOUND"

    if "401" in lower or "invalid api key" in lower:
        return "INVALID_API_KEY"

    if "403" in lower or "permission" in lower:
        return "PERMISSION_DENIED"

    if "429" in lower or "rate limit" in lower:
        return "RATE_LIMIT"

    if "timeout" in lower:
        return "TIMEOUT"

    if "connection" in lower:
        return "CONNECTION_ERROR"

    return "AI_REQUEST_ERROR"


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
# GROQ CLIENT
# =========================================================

def get_groq_client():

    if not GROQ_API_KEY:

        logger.error(
            "GROQ_API_KEY is missing."
        )

        raise RuntimeError(
            "GROQ_API_KEY is not configured on Render."
        )

    from groq import Groq

    return Groq(
        api_key=GROQ_API_KEY
    )


# =========================================================
# AI ANSWER
# =========================================================

def ai_answer(
    message,
    language,
    mode,
    history
):

    client = get_groq_client()

    language_name = {
        "fa": "Dari/Persian",
        "ps": "Pashto",
        "en": "English"
    }.get(
        language,
        "Dari/Persian"
    )

    system_prompt = f"""
You are FHAM AI.

You are a professional, helpful, educational,
accurate and general-purpose AI assistant.

Answer in {language_name}.

Current mode:
{mode}

Rules:

1. Answer the user's question directly.
2. Be accurate and useful.
3. Explain difficult subjects clearly.
4. For educational questions, teach step by step.
5. Use examples when useful.
6. Never invent facts, sources or credentials.
7. If uncertain, say so.
8. Do not claim to browse the internet unless
   a real web-search tool was used.
9. Be respectful and professional.
10. For mathematics, calculate carefully.
11. For simple questions, give a simple direct answer.
12. Do not mention internal APIs, Groq, backend,
    environment variables or system configuration
    unless the user specifically asks about them.
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    # -----------------------------------------------------
    # History
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
        "AI REQUEST | model=%s | language=%s | mode=%s",
        GROQ_MODEL,
        language,
        mode
    )

    try:

        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.3,
            max_completion_tokens=2048
        )

    except Exception as error:

        error_type = classify_error(error)

        logger.exception(
            "GROQ ERROR | type=%s | model=%s | error=%s",
            error_type,
            GROQ_MODEL,
            error
        )

        raise RuntimeError(
            f"{error_type}: {error}"
        ) from error

    if not completion.choices:

        logger.error(
            "GROQ returned zero choices."
        )

        raise RuntimeError(
            "EMPTY_GROQ_RESPONSE"
        )

    answer = (
        completion
        .choices[0]
        .message
        .content
    )

    if not answer:

        logger.error(
            "GROQ returned empty content."
        )

        raise RuntimeError(
            "EMPTY_GROQ_CONTENT"
        )

    answer = answer.strip()

    logger.info(
        "AI RESPONSE SUCCESS | model=%s | chars=%s",
        GROQ_MODEL,
        len(answer)
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
        "version": "6.0.0",
        "provider": "groq",
        "ai_configured": bool(GROQ_API_KEY),
        "model": GROQ_MODEL,
        "environment": APP_ENV
    }


# =========================================================
# DIRECT AI TEST
# =========================================================

@app.get("/api/ai-test")
def ai_test():

    try:

        answer = ai_answer(
            message="Reply with exactly: FHAM AI is working.",
            language="en",
            mode="professional",
            history=[]
        )

        return {
            "ok": True,
            "ai": True,
            "model": GROQ_MODEL,
            "answer": answer
        }

    except Exception as error:

        error_type = classify_error(error)

        logger.exception(
            "AI TEST FAILED | type=%s | error=%s",
            error_type,
            error
        )

        return {
            "ok": False,
            "ai": False,
            "model": GROQ_MODEL,
            "error_type": error_type,
            "error": str(error)
        }


# =========================================================
# PROFILE GET
# =========================================================

@app.get("/api/profile/{user_id}")
def profile(user_id: str):

    connection = conn()

    try:

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

        return dict(row)

    finally:

        connection.close()


# =========================================================
# PROFILE UPDATE
# =========================================================

@app.post("/api/profile/{user_id}")
def update_profile(
    user_id: str,
    req: ProfileRequest
):

    connection = conn()

    try:

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

        return dict(row)

    finally:

        connection.close()


# =========================================================
# CHAT HISTORY
# =========================================================

@app.get("/api/history/{user_id}")
def history(user_id: str):

    connection = conn()

    try:

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

        return [
            dict(row)
            for row in reversed(rows)
        ]

    finally:

        connection.close()


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
        # AI REQUEST
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

            error_type = classify_error(error)

            logger.exception(
                "CHAT AI FAILED | type=%s | error=%s",
                error_type,
                error
            )

            fallback = demo_answer(
                req.message,
                req.language,
                req.mode,
                reason=f"{error_type}: {error}"
            )

            answer = fallback["answer"]
            demo = True
            reason = f"{error_type}: {error}"

        # -------------------------------------------------
        # Save user
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
        # Save assistant
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
