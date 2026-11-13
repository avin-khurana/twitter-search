"""Email (Gmail SMTP + app password) and optional Telegram — ported from LEAPS/scanner.py."""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

import config


def send_email(subject: str, html_body: str, to: str | None = None) -> bool:
    to = to or config.EMAIL_TO
    if not (config.EMAIL_FROM and config.EMAIL_APP_PASSWORD and to):
        print("Email not configured (EMAIL_FROM / EMAIL_APP_PASSWORD / EMAIL_TO) — skipping")
        return False
    recipients = [a.strip() for a in to.split(",") if a.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, config.EMAIL_FROM, ", ".join(recipients)
    msg.attach(MIMEText("Your email client needs HTML to show this report.", "plain"))
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(config.EMAIL_FROM, config.EMAIL_APP_PASSWORD)
            s.sendmail(config.EMAIL_FROM, recipients, msg.as_string())
        print(f"Email sent to {len(recipients)} recipient(s)")
        return True
    except Exception as e:
        print(f"Email error: {type(e).__name__}: {e}")
        return False


def send_telegram(text: str) -> bool:
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID):
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage",
                          data={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        return r.ok
    except requests.RequestException as e:
        print(f"Telegram error: {e}")
        return False
