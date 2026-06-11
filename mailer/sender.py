import os
import resend


def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    attachment_path: str | None = None,
) -> None:
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        raise ValueError("RESEND_API_KEY is not set")

    to_email = to_email.strip().lower()
    resend.api_key = api_key
    from_addr = os.getenv("RESEND_FROM_EMAIL", "Order Insights <onboarding@resend.dev>")

    params: dict = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "html": body_html,
    }

    if attachment_path:
        try:
            with open(attachment_path, "rb") as f:
                params["attachments"] = [{"filename": "chart.png", "content": list(f.read())}]
        except Exception:
            pass

    resend.Emails.send(params)
