"""
CustomerServe Analytics Agent — Gradio UI
Single-column layout: heading → description → query → templates → response → chart
"""

import os
import gradio as gr
import plotly.io as pio
from dotenv import load_dotenv

load_dotenv()

from database.setup import setup_database
print("Initialising database …")
setup_database()
print("Database ready.")

from agent.gemini_agent import get_agent
from auth.manager import get_role, gradio_auth_pairs
from auth.roles import VIEWER_TEMPLATES, Role


# ── CSS ───────────────────────────────────────────────────────────────────────
# Strategy: dark page + strip every Gradio block border/bg + force white text

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&family=Inter:wght@400;500&display=swap');

/* Page background */
html, body {
    background: #0d0f1a !important;
    font-family: 'Inter', system-ui, sans-serif !important;
    color: #f0f0fa !important;
}

/* Hide Gradio footer */
footer, .built-with { display: none !important; }

/* Center and pad the app */
.gradio-container {
    background: transparent !important;
    max-width: 820px !important;
    margin: 0 auto !important;
    padding: 2rem 1.25rem 4rem !important;
}

/* ── Strip every block/card/panel border and background ── */
.block, .form, .gap, .panel, .wrap, .padded {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    padding: 0 !important;
    margin-bottom: 0 !important;
}

/* ── Force ALL text inside app to white ── */
.gradio-container * { color: #f0f0fa !important; }

/* ── Labels above inputs ── */
.label-wrap span {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.15em !important;
    color: rgba(155,109,255,0.90) !important;
}

/* ── Query textarea ── */
textarea {
    background: #161824 !important;
    border: 2px solid rgba(155,109,255,0.45) !important;
    color: #ffffff !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 1rem !important;
    line-height: 1.6 !important;
    border-radius: 0.75rem !important;
    padding: 0.875rem 1rem !important;
    resize: none !important;
    width: 100% !important;
    box-sizing: border-box !important;
}
textarea:focus {
    border-color: #9b6dff !important;
    box-shadow: 0 0 0 3px rgba(155,109,255,0.18) !important;
    outline: none !important;
}
textarea::placeholder { color: rgba(160,160,210,0.40) !important; }

/* ── Send button ── */
button.primary {
    background: linear-gradient(135deg, #9b6dff 0%, #22d3ee 100%) !important;
    border: none !important;
    color: #06070d !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    border-radius: 0.75rem !important;
    padding: 0.75rem 1.5rem !important;
    width: 100% !important;
    box-shadow: 0 4px 20px -4px rgba(155,109,255,0.60) !important;
    cursor: pointer !important;
}
button.primary:hover { opacity: 0.82 !important; }

/* ── Template buttons ── */
button:not(.primary) {
    background: #161824 !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    color: #d0d0ea !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.82rem !important;
    border-radius: 0.55rem !important;
    padding: 0.5rem 0.85rem !important;
    text-align: left !important;
    white-space: normal !important;
    width: 100% !important;
    cursor: pointer !important;
    line-height: 1.4 !important;
}
button:not(.primary):hover {
    border-color: rgba(155,109,255,0.55) !important;
    color: #ffffff !important;
}

/* ── Chatbot shell ── */
.chatbot {
    background: #13152a !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 0.875rem !important;
}
/* User bubble */
.message.user .bubble-wrap {
    background: rgba(75,45,170,0.30) !important;
    border: 1px solid rgba(155,109,255,0.35) !important;
    border-radius: 0.75rem !important;
}
/* Bot bubble */
.message.bot .bubble-wrap {
    background: rgba(18,20,42,0.95) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 0.75rem !important;
}
.message p, .message li, .message span { color: #f0f0fa !important; line-height: 1.7 !important; }
.message code {
    background: rgba(155,109,255,0.20) !important;
    color: #c4b5fd !important;
    border-radius: 0.25rem !important;
    padding: 0.1em 0.4em !important;
}

/* ── Chart area ── */
.plot-container, .plot-container > div, .js-plotly-plot {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* ── Slim scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(155,109,255,0.30); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(155,109,255,0.55); }
"""

# ── Static HTML blocks ────────────────────────────────────────────────────────

def _heading_html(username: str = "", role_label: str = "") -> str:
    badge = ""
    if username:
        badge = (
            f"<span style='background:linear-gradient(135deg,#9b6dff,#22d3ee);"
            f"color:#06070d;padding:4px 14px;border-radius:999px;"
            f"font-size:0.76rem;font-weight:700;font-family:Inter,sans-serif;"
            f"letter-spacing:0.05em;vertical-align:middle;'>"
            f"{username}&nbsp;·&nbsp;{role_label}</span>"
        )
    return f"""
<div style='display:flex;justify-content:space-between;align-items:flex-start;
            padding:1rem 0 0.25rem;'>
  <div>
    <h1 style='font-family:"Space Grotesk",sans-serif;
               font-size:clamp(1.9rem,4vw,2.7rem);
               font-weight:700;letter-spacing:-0.03em;
               line-height:1.15;margin:0 0 0.5rem;
               background:linear-gradient(130deg,#c4b5fd,#9b6dff 50%,#22d3ee);
               -webkit-background-clip:text;background-clip:text;
               color:transparent;'>
      CustomerServe Analytics
    </h1>
    <p style='font-size:0.9rem;color:rgba(190,190,230,0.72);
              line-height:1.6;margin:0;max-width:560px;
              font-family:Inter,sans-serif;'>
      Ask questions about orders, products, and sales in plain English.
      The agent writes SQL, queries the database, and draws charts for you.
    </p>
  </div>
  <div style='flex-shrink:0;padding-top:0.25rem;'>{badge}</div>
</div>
<hr style='border:none;border-top:1px solid rgba(255,255,255,0.09);margin:1.25rem 0 0;'>
"""

_TPL_HEADING = """
<p style='font-size:0.68rem;font-weight:600;text-transform:uppercase;
          letter-spacing:0.18em;color:rgba(155,109,255,0.85);
          margin:1.25rem 0 0.6rem;font-family:Inter,sans-serif;'>
  Quick templates — click to fill the box above
</p>
"""

_DIVIDER = "<hr style='border:none;border-top:1px solid rgba(255,255,255,0.09);margin:1.5rem 0;'>"


# ── Handlers ──────────────────────────────────────────────────────────────────

def respond(message: str, history: list, request: gr.Request):
    username = request.username
    role     = get_role(username)
    agent    = get_agent()

    history_tuples = []
    for i in range(0, len(history) - 1, 2):
        if i + 1 < len(history):
            history_tuples.append((history[i]["content"], history[i + 1]["content"]))

    text, chart_json = agent.chat(
        user_query=message,
        history=history_tuples,
        role=role,
        username=username,
    )

    fig = None
    if chart_json:
        try:
            fig = pio.from_json(chart_json)
        except Exception as e:
            text += f"\n\n*(Chart could not be rendered: {e})*"

    history = history + [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": text},
    ]
    return "", history, fig


def fill_input(template: str):
    return template


def build_heading(request: gr.Request) -> str:
    if not request or not request.username:
        return _heading_html()
    role = get_role(request.username)
    return _heading_html(request.username, role.value.upper())


# ── Layout ────────────────────────────────────────────────────────────────────

def build_ui():
    with gr.Blocks(
        title="CustomerServe Analytics",
        theme=gr.themes.Base(),
        css=CSS,
    ) as demo:

        # 1. Page heading + description + role badge (inline HTML, no Gradio columns)
        heading = gr.HTML(value=_heading_html())

        # 2. Query input field
        msg_box = gr.Textbox(
            placeholder="e.g.  Show me monthly revenue for 2024 …",
            label="Your question",
            lines=3,
            max_lines=8,
        )

        # 3. Send button
        send_btn = gr.Button("Send →", variant="primary")

        # 4. Templates
        gr.HTML(_TPL_HEADING)
        tpl_btns = []
        # Two template buttons per row for compactness, still single logical column
        for i in range(0, len(VIEWER_TEMPLATES), 2):
            with gr.Row():
                for tpl in VIEWER_TEMPLATES[i : i + 2]:
                    b = gr.Button(tpl, size="sm")
                    tpl_btns.append((b, tpl))

        # 5. Divider
        gr.HTML(_DIVIDER)

        # 6. Text response area
        chatbot = gr.Chatbot(
            height=380,
            show_label=False,
            type="messages",
            placeholder="*Your results will appear here …*",
        )

        # 7. Visualisation chart
        chart_output = gr.Plot(show_label=False)

        # ── Wire everything ───────────────────────────────────────────────
        send_btn.click(
            fn=respond,
            inputs=[msg_box, chatbot],
            outputs=[msg_box, chatbot, chart_output],
        )
        msg_box.submit(
            fn=respond,
            inputs=[msg_box, chatbot],
            outputs=[msg_box, chatbot, chart_output],
        )
        for btn, tpl in tpl_btns:
            btn.click(fn=fill_input, inputs=gr.State(tpl), outputs=msg_box)

        # Populate heading with role badge after login
        demo.load(fn=build_heading, outputs=heading)

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
