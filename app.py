"""
CustomerServe Analytics Agent — Gradio UI
Single-column layout: heading → description → query → templates → response → chart
Light theme with violet/cyan accent — works reliably with Gradio's default rendering.
"""

import os
import tempfile
import threading
from datetime import date as _date
import gradio as gr
import plotly.io as pio
from dotenv import load_dotenv

load_dotenv()

from database.setup import setup_database
from database.scheduler import save_schedule, get_due_schedules, mark_sent
from mcp.tools import get_schema, get_schema_html
from agent.gemini_agent import get_agent
from agent.chart_agent import get_chart_agent
from auth.manager import get_role, gradio_auth_pairs
from auth.roles import VIEWER_TEMPLATES, Role, PERMISSIONS
from mailer.sender import send_email

print("Initialising database …")
setup_database()

print("Pre-loading schema cache …")
get_schema()
print("Schema cached.")


# ── CSS ───────────────────────────────────────────────────────────────────────
# Keep Gradio's white background. Only override: fonts, colours, borders, spacing.

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&family=Inter:wght@400;500;600&display=swap');

/* Hide Gradio footer */
footer, .built-with { display: none !important; }

/* Container width and font */
.gradio-container {
    font-family: 'Inter', system-ui, sans-serif !important;
    max-width: 820px !important;
    margin: 0 auto !important;
    padding: 1rem 1.25rem 4rem !important;
}

/* Strip decorative block borders; keep backgrounds intact */
.block, .form, .gap, .panel {
    box-shadow: none !important;
    border: none !important;
}

/* ── Labels above inputs ── */
.label-wrap span {
    font-size: 0.70rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.15em !important;
    color: #5b21b6 !important;
    font-family: 'Inter', sans-serif !important;
}

/* ── Query textarea ── */
textarea {
    font-family: 'Inter', sans-serif !important;
    font-size: 1rem !important;
    color: #1e1b4b !important;
    background: #ffffff !important;
    border: 2px solid #c4b5fd !important;
    border-radius: 0.75rem !important;
    padding: 0.875rem 1rem !important;
    line-height: 1.6 !important;
    resize: none !important;
}
textarea:focus {
    border-color: #7c3aed !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.12) !important;
    outline: none !important;
}
textarea::placeholder { color: #a5a5c8 !important; }

/* ── Send button ── */
button.primary {
    background: linear-gradient(135deg, #7c3aed 0%, #0891b2 100%) !important;
    border: none !important;
    color: #ffffff !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    border-radius: 0.75rem !important;
    width: 100% !important;
    padding: 0.75rem !important;
    box-shadow: 0 4px 16px -4px rgba(124,58,237,0.40) !important;
    cursor: pointer !important;
}
button.primary:hover { opacity: 0.86 !important; }

/* ── Template buttons ── */
button:not(.primary) {
    background: #f5f3ff !important;
    border: 1px solid #ddd6fe !important;
    color: #3b0764 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.82rem !important;
    border-radius: 0.55rem !important;
    text-align: left !important;
    white-space: normal !important;
    width: 100% !important;
    line-height: 1.45 !important;
    padding: 0.5rem 0.85rem !important;
    cursor: pointer !important;
}
button:not(.primary):hover {
    background: #ede9fe !important;
    border-color: #7c3aed !important;
    color: #1e1b4b !important;
}

/* ── Chatbot container ── */
.chatbot {
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 0.875rem !important;
    background: #fafafa !important;
}

/* User bubble */
.message.user .bubble-wrap {
    background: #ede9fe !important;
    border: 1px solid #c4b5fd !important;
    border-radius: 0.75rem !important;
}
/* Bot bubble */
.message.bot .bubble-wrap {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 0.75rem !important;
}
/* Message text — force dark so it reads on white/lavender bubbles */
.message p, .message li, .message h1, .message h2,
.message h3, .message strong, .message em {
    color: #1e1b4b !important;
    font-family: 'Inter', sans-serif !important;
    line-height: 1.7 !important;
}
.message code {
    background: #ede9fe !important;
    color: #5b21b6 !important;
    border-radius: 0.25rem !important;
    padding: 0.1em 0.4em !important;
    font-size: 0.88em !important;
}
.message span { color: #1e1b4b !important; }

/* ── Chart area ── */
.plot-container, .plot-container > div, .js-plotly-plot {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* ── Schema accordion ── */
.schema-ref > .label-wrap > span {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.13em !important;
    color: #5b21b6 !important;
}
.schema-ref {
    background: #faf9ff !important;
    border: 1px solid #ede9fe !important;
    border-radius: 0.65rem !important;
    margin-bottom: 0.25rem !important;
}

/* ── Slim scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(124,58,237,0.25); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(124,58,237,0.50); }

/* ── Schedule panel ── */
.schedule-panel > .label-wrap > span {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.13em !important;
    color: #5b21b6 !important;
}
.schedule-panel {
    background: #faf9ff !important;
    border: 1px solid #ede9fe !important;
    border-radius: 0.75rem !important;
    margin-top: 0.75rem !important;
}
"""


# ── Static HTML blocks ────────────────────────────────────────────────────────

def _heading_html(username: str = "", role_label: str = "") -> str:
    badge = ""
    if username:
        badge = (
            f"<span style='"
            f"background:linear-gradient(135deg,#7c3aed,#0891b2);"
            f"color:#ffffff;"
            f"padding:5px 16px;border-radius:999px;"
            f"font-size:0.78rem;font-weight:700;"
            f"font-family:Inter,sans-serif;letter-spacing:0.05em;"
            f"box-shadow:0 2px 10px rgba(124,58,237,0.30);'>"
            f"{username}&nbsp;·&nbsp;{role_label}"
            f"</span>"
        )
    return f"""
<div style="display:flex;justify-content:space-between;align-items:flex-start;
            padding:1.25rem 0 0.5rem;">
  <div>
    <h1 style="font-family:'Space Grotesk',sans-serif;
               font-size:clamp(1.8rem,4vw,2.6rem);
               font-weight:700;
               letter-spacing:-0.025em;
               line-height:1.15;
               margin:0 0 0.55rem;
               color:#3b0764;">
      Order Insights
    </h1>
    <p style="font-size:0.92rem;
              color:#374151;
              line-height:1.65;
              margin:0;
              max-width:560px;
              font-family:Inter,sans-serif;">
      Ask questions in plain English — get instant charts and insights, and schedule email reports.
    </p>
  </div>
  <div style="flex-shrink:0;padding-top:0.35rem;">{badge}</div>
</div>
<hr style="border:none;border-top:2px solid #ede9fe;margin:0.5rem 0 0;">
"""

_TPL_HEADING = """
<p style="font-size:0.70rem;font-weight:600;text-transform:uppercase;
          letter-spacing:0.16em;color:#5b21b6;
          margin:1.25rem 0 0.65rem;font-family:Inter,sans-serif;">
  Quick templates &mdash; click to fill the box above
</p>
"""

_DIVIDER = (
    "<hr style='border:none;border-top:2px solid #ede9fe;"
    "margin:1.5rem 0;'>"
)

_SCHEDULE_INTRO = (
    "<p style='font-size:0.85rem;color:#374151;font-family:Inter,sans-serif;"
    "margin:0 0 0.75rem;line-height:1.6;'>"
    "Email this chart and its insights — once now, or on a recurring schedule.</p>"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sched_status(msg: str, kind: str) -> dict:
    color  = "#15803d" if kind == "success" else "#dc2626"
    bg     = "#f0fdf4" if kind == "success" else "#fef2f2"
    border = "#86efac" if kind == "success" else "#fca5a5"
    icon   = "✓" if kind == "success" else "⚠"
    return gr.update(
        value=(
            f"<div style='background:{bg};border:1px solid {border};border-radius:0.5rem;"
            f"padding:0.65rem 1rem;margin-top:0.5rem;'>"
            f"<span style='color:{color};font-family:Inter,sans-serif;font-size:0.88rem;'>"
            f"{icon}&nbsp;{msg}</span></div>"
        ),
        visible=True,
    )


def _run_due_schedules() -> None:
    """Background thread: send any overdue scheduled reports with freshly generated data."""
    try:
        due = get_due_schedules()
        if not due:
            return
        for sched in due:
            try:
                role = get_role(sched["username"])
                _, query_result = get_agent().chat(
                    user_query=sched["question"],
                    history=[],
                    role=role,
                    username=sched["username"],
                )
                insights = ""
                png_path = None
                if query_result and query_result.get("rows"):
                    chart_json, insights = get_chart_agent().analyze(
                        rows=query_result["rows"],
                        columns=query_result["columns"],
                        user_question=sched["question"],
                        role=role,
                    )
                    if chart_json:
                        fig = pio.from_json(chart_json)
                        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="sched_")
                        fig.write_image(tmp.name, width=1000, height=520, scale=2)
                        png_path = tmp.name

                freq_labels = {"weekly": "Weekly", "biweekly": "Bi-weekly", "monthly": "Monthly"}
                days_str = f" ({', '.join(sched['days_of_week'])})" if sched["days_of_week"] else ""
                label = freq_labels.get(sched["frequency"], "Scheduled") + days_str
                body = _build_report_email_html(sched["question"], insights, label)
                send_email(sched["email"], f"Order Insights: {sched['question'][:80]}", body, png_path)
                mark_sent(sched["id"], sched["frequency"], sched["days_of_week"], _date.today())
            except Exception as e:
                print(f"[Scheduler] Failed to send report {sched['id']}: {e}")
    except Exception as e:
        print(f"[Scheduler] Error checking schedules: {e}")


def _format_insights(insights: str) -> str:
    lines = [l.strip() for l in insights.strip().splitlines() if l.strip()]
    items = "".join(
        f"<li style='margin-bottom:0.35rem;'>{l.lstrip('•- ')}</li>"
        for l in lines
    )
    return (
        "<div style='background:#f0fdf4;border:1px solid #86efac;"
        "border-radius:0.65rem;padding:0.75rem 1rem;margin-top:0.25rem;'>"
        "<p style='font-size:0.72rem;font-weight:600;text-transform:uppercase;"
        "letter-spacing:0.13em;color:#15803d;margin:0 0 0.45rem;"
        "font-family:Inter,sans-serif;'>Key Insights</p>"
        "<ul style='margin:0;padding-left:1.2rem;color:#1e1b4b;"
        "font-family:Inter,sans-serif;font-size:0.88rem;line-height:1.7;'>"
        f"{items}</ul></div>"
    )


def _build_report_email_html(question: str, insights: str, schedule_label: str) -> str:
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

    return (
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
        "<p style='color:#6b7280;font-size:13px;font-family:Inter,sans-serif;'>"
        "The chart is attached as <strong>chart.png</strong>.</p>"
        "<hr style='border:none;border-top:1px solid #e5e7eb;margin:24px 0;'>"
        f"<p style='color:#9ca3af;font-size:11px;font-family:Inter,sans-serif;'>"
        f"Schedule: {schedule_label} &middot; Order Insights Analytics</p></div>"
    )


# ── Handlers ──────────────────────────────────────────────────────────────────

def respond(message: str, history: list, request: gr.Request):
    username    = request.username
    role        = get_role(username)
    query_agent = get_agent()
    chart_agent = get_chart_agent()

    history_tuples = []
    for i in range(0, len(history) - 1, 2):
        if i + 1 < len(history):
            history_tuples.append((history[i]["content"], history[i + 1]["content"]))

    # ── Stage 1: QueryAgent — schema + SQL + data retrieval ──────────────
    text, query_result = query_agent.chat(
        user_query=message,
        history=history_tuples,
        role=role,
        username=username,
    )

    # ── Stage 2: ChartAgent — visualisation + insights ───────────────────
    fig              = None
    raw_insights     = ""
    png_path_val     = ""
    insights_update  = gr.update(visible=False)
    chart_download   = gr.update(visible=False)

    if query_result and query_result.get("rows"):
        chart_json, insights = chart_agent.analyze(
            rows=query_result["rows"],
            columns=query_result["columns"],
            user_question=message,
            role=role,
        )
        raw_insights = insights or ""

        if chart_json:
            try:
                fig = pio.from_json(chart_json)
            except Exception as e:
                text += f"\n\n*(Chart could not be rendered: {e})*"

        if fig is not None:
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="chart_")
                export_fig = pio.from_json(fig.to_json())
                _arial_dark  = dict(family="Arial, sans-serif", color="#1e1b4b")
                _arial_title = dict(family="Arial, sans-serif", color="#3b0764")
                _arial_axis  = dict(family="Arial, sans-serif", color="#374151")
                export_fig.update_layout(
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#f5f3ff",
                    font=_arial_dark,
                    title=dict(font=_arial_title),
                    xaxis=dict(tickfont=_arial_axis),
                    yaxis=dict(tickfont=_arial_axis),
                    legend=dict(font=_arial_dark),
                )
                # pie slice labels use a trace-level textfont (near-white in interactive view)
                export_fig.update_traces(textfont=_arial_dark)
                export_fig.write_image(tmp.name, width=1000, height=520, scale=2)
                chart_download = gr.update(value=tmp.name, visible=True)
                png_path_val = tmp.name
            except Exception:
                pass

        if insights:
            insights_update = gr.update(value=_format_insights(insights), visible=True)

    schedule_update = gr.update(visible=fig is not None, open=fig is not None)

    history = history + [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": text},
    ]
    return "", history, fig, chart_download, insights_update, schedule_update, message, png_path_val, raw_insights


def schedule_report(
    email: str,
    freq: str,
    days: list,
    start_str: str,
    end_str: str,
    question: str,
    png_path: str,
    insights: str,
    request: gr.Request,
) -> dict:
    username = request.username if request else "unknown"

    if not email or "@" not in email:
        return _sched_status("Please enter a valid email address.", "error")
    if not question:
        return _sched_status("No report to schedule — run a query first.", "error")

    freq_map = {
        "Send now": "now", "Weekly": "weekly",
        "Bi-weekly": "biweekly", "Monthly": "monthly",
    }
    freq_key = freq_map.get(freq, "now")

    if freq_key == "now":
        try:
            body = _build_report_email_html(question, insights, "On demand")
            send_email(email, f"Order Insights: {question[:80]}", body, png_path or None)
            return _sched_status(f"Report sent to {email}!", "success")
        except Exception as e:
            return _sched_status(f"Could not send email: {e}", "error")

    try:
        start_date = _date.fromisoformat(start_str.strip()) if start_str.strip() else _date.today()
    except ValueError:
        return _sched_status("Invalid start date — use YYYY-MM-DD (e.g. 2025-07-01).", "error")

    end_date = None
    if end_str and end_str.strip():
        try:
            end_date = _date.fromisoformat(end_str.strip())
        except ValueError:
            return _sched_status("Invalid end date — use YYYY-MM-DD (e.g. 2025-12-31).", "error")

    try:
        save_schedule(username, email, question, freq_key, list(days or []), start_date, end_date)
        freq_labels = {"weekly": "weekly", "biweekly": "every two weeks", "monthly": "monthly"}
        days_str = f" on {', '.join(days)}" if days else ""
        return _sched_status(
            f"Scheduled {freq_labels[freq_key]}{days_str}, starting {start_date}. "
            "You'll receive fresh data each delivery.",
            "success",
        )
    except Exception as e:
        return _sched_status(f"Could not save schedule: {e}", "error")


def fill_input(template: str) -> str:
    return template


def build_schema_panel(request: gr.Request) -> tuple:
    if not request or not request.username:
        return gr.update(visible=False), gr.update(value="")
    role = get_role(request.username)
    if not PERMISSIONS[role].can_see_schema:
        return gr.update(visible=False), gr.update(value="")
    return gr.update(visible=True), gr.update(value=get_schema_html())


def build_heading(request: gr.Request) -> str:
    threading.Thread(target=_run_due_schedules, daemon=True).start()
    if not request or not request.username:
        return _heading_html()
    role = get_role(request.username)
    return _heading_html(request.username, role.value.upper())


# ── Layout ────────────────────────────────────────────────────────────────────

def build_ui():
    with gr.Blocks(
        title="Order Insights",
        theme=gr.themes.Soft(
            primary_hue="violet",
            secondary_hue="cyan",
            font=gr.themes.GoogleFont("Inter"),
        ),
        css=CSS,
    ) as demo:

        # 1 ── Heading + description + role badge
        heading = gr.HTML(value=_heading_html())

        # 2 ── Schema reference accordion (ADMIN / ANALYST only; hidden until load)
        with gr.Accordion(
            "📋  Schema Reference — click to explore the data",
            open=False,
            visible=False,
            elem_classes=["schema-ref"],
        ) as schema_accordion:
            schema_panel = gr.HTML("")

        # 3 ── Query input
        msg_box = gr.Textbox(
            placeholder="e.g.  Show me monthly revenue for 2024 …",
            label="Your question",
            lines=3,
            max_lines=8,
        )

        # 4 ── Send button
        send_btn = gr.Button("Send →", variant="primary")

        # 4 ── Templates
        gr.HTML(_TPL_HEADING)
        tpl_btns = []
        for i in range(0, len(VIEWER_TEMPLATES), 2):
            with gr.Row():
                for tpl in VIEWER_TEMPLATES[i : i + 2]:
                    b = gr.Button(tpl, size="sm")
                    tpl_btns.append((b, tpl))

        # 5 ── Divider
        gr.HTML(_DIVIDER)

        # 6 ── Response area
        chatbot = gr.Chatbot(
            height=380,
            show_label=False,
            type="messages",
            placeholder="*Results will appear here after you send a question.*",
        )

        # 7 ── Visualisation
        chart_output = gr.Plot(show_label=False)

        # 8 ── Download chart button (hidden until a chart is rendered)
        download_btn = gr.DownloadButton(
            label="Download Chart",
            visible=False,
            size="sm",
        )

        # 9 ── Key Insights (hidden until ChartAgent returns analysis)
        insights_box = gr.HTML(value="", visible=False)

        # 10 ── Hidden state: carry current question / png / insights into schedule handler
        current_question = gr.State("")
        current_png      = gr.State("")
        current_insights = gr.State("")

        # 11 ── Schedule panel (revealed after a chart is rendered)
        with gr.Accordion(
            "📅  Schedule this report",
            open=True,
            visible=False,
            elem_classes=["schedule-panel"],
        ) as schedule_panel:
            gr.HTML(_SCHEDULE_INTRO)
            sched_email = gr.Textbox(
                label="Email address",
                placeholder="you@example.com",
            )
            sched_freq = gr.Radio(
                choices=["Send now", "Weekly", "Bi-weekly", "Monthly"],
                value="Send now",
                label="Frequency",
            )
            sched_days = gr.CheckboxGroup(
                choices=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                label="Day(s) of week",
                visible=False,
            )
            sched_start = gr.Textbox(
                label="Start date",
                placeholder="YYYY-MM-DD",
                value=str(_date.today()),
                visible=False,
            )
            sched_end = gr.Textbox(
                label="End date (optional — leave blank to repeat indefinitely)",
                placeholder="YYYY-MM-DD",
                visible=False,
            )
            sched_btn    = gr.Button("Send Report →", variant="primary", size="sm")
            sched_status = gr.HTML("", visible=False)

        # ── Events ───────────────────────────────────────────────────────
        _respond_outputs = [
            msg_box, chatbot, chart_output, download_btn, insights_box,
            schedule_panel, current_question, current_png, current_insights,
        ]
        send_btn.click(fn=respond, inputs=[msg_box, chatbot], outputs=_respond_outputs)
        msg_box.submit(fn=respond, inputs=[msg_box, chatbot], outputs=_respond_outputs)

        def _on_freq_change(freq):
            show_days  = freq in ("Weekly", "Bi-weekly")
            show_dates = freq != "Send now"
            btn_label  = "Send Report →" if freq == "Send now" else "Schedule Report →"
            return (
                gr.update(visible=show_days),
                gr.update(visible=show_dates),
                gr.update(visible=show_dates),
                gr.update(value=btn_label),
            )

        sched_freq.change(
            fn=_on_freq_change,
            inputs=sched_freq,
            outputs=[sched_days, sched_start, sched_end, sched_btn],
        )
        sched_btn.click(
            fn=schedule_report,
            inputs=[
                sched_email, sched_freq, sched_days, sched_start, sched_end,
                current_question, current_png, current_insights,
            ],
            outputs=[sched_status],
        )

        for btn, tpl in tpl_btns:
            btn.click(fn=fill_input, inputs=gr.State(tpl), outputs=msg_box)

        demo.load(fn=build_heading, outputs=heading)
        demo.load(fn=build_schema_panel, outputs=[schema_accordion, schema_panel])

    return demo


# ── Launch ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo = build_ui()
    demo.launch(
        auth=gradio_auth_pairs(),
        auth_message="Welcome to Order Insights. Please log in.",
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", 7860)),
        show_error=True,
    )
