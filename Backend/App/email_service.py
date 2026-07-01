import html
import os
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variabila de mediu {name} nu este configurata")
    return value


def build_password_reset_url(token: str) -> str:
    frontend_url = _required_env("FRONTEND_URL").rstrip("/")
    return f"{frontend_url}/?{urlencode({'reset_token': token})}"


def send_password_reset_email(recipient: str, reset_url: str, expires_minutes: int):
    smtp_host = _required_env("SMTP_HOST")
    smtp_username = _required_env("SMTP_USERNAME")
    smtp_password = _required_env("SMTP_PASSWORD")
    sender_email = (os.getenv("SMTP_FROM_EMAIL") or smtp_username).strip()
    sender_name = (
        os.getenv("SMTP_FROM_NAME") or "Imobiliare Timisoara"
    ).strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    safe_url = html.escape(reset_url, quote=True)
    message = EmailMessage()
    message["Subject"] = "Resetarea parolei - Imobiliare Timisoara"
    message["From"] = f"{sender_name} <{sender_email}>"
    message["To"] = recipient
    message.set_content(
        "Ai solicitat resetarea parolei pentru contul tau.\n\n"
        f"Deschide linkul urmator in maximum {expires_minutes} de minute:\n"
        f"{reset_url}\n\n"
        "Daca nu ai solicitat aceasta schimbare, poti ignora mesajul."
    )
    message.add_alternative(
        f"""
        <!doctype html>
        <html lang="ro">
          <body style="margin:0;background:#f5f0e8;font-family:Arial,sans-serif;color:#241f1a;">
            <div style="max-width:560px;margin:32px auto;padding:32px;background:#fffaf4;border:1px solid #e4d8ca;border-radius:18px;">
              <p style="margin:0 0 8px;color:#b9582f;font-size:13px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">
                Radar rezidential
              </p>
              <h1 style="margin:0 0 18px;font-size:26px;">Resetarea parolei</h1>
              <p style="line-height:1.6;">Ai solicitat resetarea parolei pentru contul tau.</p>
              <p style="line-height:1.6;">Linkul este valabil {expires_minutes} de minute.</p>
              <p style="margin:28px 0;">
                <a href="{safe_url}" style="display:inline-block;padding:13px 20px;border-radius:999px;background:#b9582f;color:#ffffff;text-decoration:none;font-weight:700;">
                  Alege parola noua
                </a>
              </p>
              <p style="line-height:1.6;color:#6f655c;font-size:14px;">
                Daca nu ai solicitat aceasta schimbare, poti ignora mesajul.
              </p>
            </div>
          </body>
        </html>
        """,
        subtype="html",
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)
