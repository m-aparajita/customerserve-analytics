"""
CustomerServe Analytics Agent — Gradio UI
Single-column layout: heading → description → query → templates → response → chart
Light theme with violet/cyan accent — works reliably with Gradio's default rendering.
"""

import os
import tempfile
import gradio as gr
import plotly.io as pio
from dotenv import load_dotenv

load_dotenv()

from database.setup import setup_database
from mcp.tools import get_schema, get_schema_html
from agent.gemini_agent import get_agent
from agent.chart_agent import get_chart_agent
from auth.manager import get_role, gradio_auth_pairs
from auth.roles import VIEWER_TEMPLATES, Role, PERMISSIONS

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
      CustomerServe Analytics
    </h1>
    <p style="font-size:0.92rem;
              color:#374151;
              line-height:1.65;
              margin:0;
              max-width:560px;
              font-family:Inter,sans-serif;">
      Ask questions about orders, products, and sales in plain English.
      The agent writes SQL, queries the database, and draws charts for you.
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


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    insights_update  = gr.update(visible=False)
    chart_download   = gr.update(visible=False)

    if query_result and query_result.get("rows"):
        chart_json, insights = chart_agent.analyze(
            rows=query_result["rows"],
            columns=query_result["columns"],
            user_question=message,
            role=role,
        )

        if chart_json:
            try:
                fig = pio.from_json(chart_json)
            except Exception as e:
                text += f"\n\n*(Chart could not be rendered: {e})*"

        if fig is not None:
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="chart_")
                export_fig = pio.from_json(fig.to_json())
                export_fig.update_layout(
                    font=dict(family="Arial, sans-serif"),
                    title=dict(font=dict(family="Arial, sans-serif")),
                )
                export_fig.write_image(tmp.name, width=1000, height=520, scale=2)
                chart_download = gr.update(value=tmp.name, visible=True)
            except Exception:
                pass

        if insights:
            insights_update = gr.update(value=_format_insights(insights), visible=True)

    history = history + [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": text},
    ]
    return "", history, fig, chart_download, insights_update


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
    if not request or not request.username:
        return _heading_html()
    role = get_role(request.username)
    return _heading_html(request.username, role.value.upper())


# ── Layout ────────────────────────────────────────────────────────────────────

def build_ui():
    with gr.Blocks(
        title="CustomerServe Analytics",
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

        # ── Events ───────────────────────────────────────────────────────
        send_btn.click(
            fn=respond,
            inputs=[msg_box, chatbot],
            outputs=[msg_box, chatbot, chart_output, download_btn, insights_box],
        )
        msg_box.submit(
            fn=respond,
            inputs=[msg_box, chatbot],
            outputs=[msg_box, chatbot, chart_output, download_btn, insights_box],
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
        auth_message="Welcome to CustomerServe Analytics. Please log in.",
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", 7860)),
        show_error=True,
    )
