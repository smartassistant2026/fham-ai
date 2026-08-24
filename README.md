# FHAM AI 4.0 — Final MVP

این نسخه یک پروژه یکپارچه است: Frontend + FastAPI Backend + SQLite + AI Chat + History + سه‌زبانه + حالت‌های پاسخ.

## اجرا
Windows: `run.bat`
Linux/macOS: `chmod +x run.sh && ./run.sh`

سپس:
`http://127.0.0.1:8000`

## فعال‌سازی AI واقعی
`.env.example` را به `.env` تبدیل کنید و `OPENAI_API_KEY` را فقط در محیط Backend قرار دهید.
برای اجرای ساده می‌توانید متغیرها را در محیط سیستم تنظیم کنید.

## امنیت
کلید API در Frontend وجود ندارد. برای محیط عمومی باید CORS محدود، rate limiting، احراز هویت، HTTPS و مدیریت Secret اضافه شود.

## انتشار عمومی
این بسته برای Deploy آماده ساختاری است، اما ایجاد URL عمومی واقعی نیازمند یک حساب میزبانی/Deploy و Secret API است؛ بدون آن ادعای «لینک آنلاین فعال» قابل اعتماد نیست.
