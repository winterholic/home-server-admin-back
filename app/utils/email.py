import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import get_settings


async def send_alert_email(recipients: list[str], subject: str, body: str) -> bool:
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password:
        raise ValueError("SMTP credentials not configured")

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    html_body = f"""
    <html>
    <body style="font-family: 'Inter', Arial, sans-serif; background: #0a0e1a; color: #e2e8f0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #111827; border-radius: 12px; padding: 24px; border: 1px solid rgba(0,242,255,0.2);">
            <h2 style="color: #00f2ff; margin: 0 0 16px 0;">NodeCtrl Alert</h2>
            <p style="font-size: 16px; line-height: 1.6;">{body}</p>
            <hr style="border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 20px 0;">
            <p style="font-size: 12px; color: #64748b;">
                This is an automated alert from your HomeServer Dashboard.
            </p>
        </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_body, "html"))

    # Port 465 uses implicit TLS; port 587 uses STARTTLS upgrade.
    use_implicit_tls = settings.smtp_port == 465

    smtp_kwargs: dict = dict(
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
    )
    if use_implicit_tls:
        smtp_kwargs["use_tls"] = True
    elif settings.smtp_tls:
        smtp_kwargs["start_tls"] = True

    await aiosmtplib.send(msg, **smtp_kwargs)
    return True
