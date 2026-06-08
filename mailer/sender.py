import os
import resend


def send_report_email(
    to_email: str,
    question: str,
    insights: str,
    png_path: str | None = None,
    schedule_label: str = "On demand",
) -> None:
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        raise ValueError("RESEND_API_KEY is not set")

    resend.api_key = api_key
    from_addr = os.getenv("RESEND_FROM_EMAIL", "Order Insights <onboarding@resend.dev>")

    insights_html = ""
    if insights:
        lines = [l.strip() for l in insights.strip().splitlines() if l.strip()]
        items = "".join(
            f"<li style='margin:4px 0;color:#1e1b4b;'>{l.lstrip('•- ')}</li>"
            for l in lines
        )
        insights_html = (
            "<div style='background:#f0fdf4;border:1px solid #86efac;border-radius:8px;"
            "padding:12px 16px;margin:16px 0;'>"
            "<p style='font-weight:600;color:#15803d;font-size:12px;text-transform:uppercase;"
            "letter-spacing:0.1em;margin:0 0 8px;font-family:Inter,sans-serif;'>Key Insights</p>"
            f"<ul style='margin:0;padding-left:20px;font-size:14px;line-height:1.7;"
            f"font-family:Inter,sans-serif;'>{items}</ul></div>"
        )

    attachment_note = (
        "<p style='color:#6b7280;font-size:13px;font-family:Inter,sans-serif;'>"
        "The chart is attached as <strong>chart.png</strong>.</p>"
        if png_path else ""
    )

    html = (
        "<div style='font-family:Inter,system-ui,sans-serif;max-width:600px;"
        "margin:0 auto;padding:24px;'>"
        "<h1 style='color:#3b0764;font-size:22px;font-weight:700;margin:0 0 4px;'>"
        "Order Insights</h1>"
        "<p style='color:#6b7280;font-size:13px;margin:0 0 24px;'>Your scheduled report</p>"
        "<div style='background:#f5f3ff;border-radius:8px;padding:16px;margin:0 0 8px;'>"
        "<p style='font-weight:600;color:#5b21b6;font-size:11px;text-transform:uppercase;"
        "letter-spacing:0.12em;margin:0 0 6px;font-family:Inter,sans-serif;'>Question</p>"
        f"<p style='color:#1e1b4b;margin:0;font-size:15px;font-family:Inter,sans-serif;'>"
        f"{question}</p></div>"
        f"{insights_html}"
        f"{attachment_note}"
        "<hr style='border:none;border-top:1px solid #e5e7eb;margin:24px 0;'>"
        f"<p style='color:#9ca3af;font-size:11px;font-family:Inter,sans-serif;'>"
        f"Schedule: {schedule_label} &middot; Order Insights Analytics</p></div>"
    )

    params: dict = {
        "from": from_addr,
        "to": [to_email],
        "subject": f"Order Insights: {question[:80]}",
        "html": html,
    }

    if png_path:
        try:
            with open(png_path, "rb") as f:
                params["attachments"] = [{"filename": "chart.png", "content": list(f.read())}]
        except Exception:
            pass

    resend.Emails.send(params)
