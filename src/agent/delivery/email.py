"""SMTP(SSL)로 HTML 메일 발송. 기본은 네이버 메일."""
import os
import smtplib
from email.message import EmailMessage


def send_email(subject: str, html: str, *, smtp_factory=smtplib.SMTP_SSL) -> None:
    host = os.environ.get("SMTP_HOST") or "smtp.naver.com"
    port = int(os.environ.get("SMTP_PORT") or 465)
    sender = os.environ["MAIL_FROM"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = os.environ.get("MAIL_TO") or sender
    msg.set_content("HTML 메일을 지원하는 메일 앱에서 열어주세요.")
    msg.add_alternative(html, subtype="html")
    with smtp_factory(host, port, timeout=30) as smtp:
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)
