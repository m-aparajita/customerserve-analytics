"""
Main entry point for the CustomerServe Analytics Agent.
Runs Gradio UI with built-in login.  Everything ships as a single HuggingFace Space.
"""

import os

import gradio as gr
import plotly.io as pio
from dotenv import load_dotenv

load_dotenv()

# ── Bootstrap database ────────────────────────────────────────────────────────
from database.setup import setup_database
print("Initialising database …")
setup_database()
print("Database ready.")

# ── App imports ───────────────────────────────────────────────────────────────
from agent.gemini_agent import get_agent
from auth.manager import get_role, gradio_auth_pairs
from auth.roles import VIEWER_TEMPLATES, Role


# ── Theme & CSS ───────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');

/* ── Dark base ── */
html {
    color-scheme: dark;
    background: #0e1018 !important;
}
body {
    background: #0e1018 !important;
    background-image:
        radial-gradient(ellipse at 12% 0%, rgba(120,80,200,0.25) 0%, transparent 48%),
        radial-gradient(ellipse at 88% 0%, rgba(34,211,238,0.16) 0%, transparent 44%) !important;
    background-attachment: fixed !important;
    font-family: 'Inter', system-ui, sans-serif !important;
    color: #e2e2f0 !important;
}

/* Hide Gradio footer */
footer, .built-with { display: none !important; }

/* ── Container ── */
.gradio-container {
    background: transparent !important;
    max-width: 880px !important;
    margin: 0 auto !important;
    padding: 1.5rem 1rem 3rem !important;
}

/* ── Strip ALL default block card styling ── */
.block, .form, .gap, .panel {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* ── Force readable text everywhere ── */
.gradio-container,
.gradio-container p,
.gradio-container span,
.gradio-container div,
.gradio-container label,
.gradio-container li {
    color: #e2e2f0 !important;
}

/* ── Textarea (query box) ── */
textarea {
    background: #161826 !important;
    border: 1.5px solid rgba(155,109,255,0.40) !important;
    color: #f0f0f8 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.975rem !important;
    line-height: 1.6 !important;
    border-radius: 0.75rem !important;
    resize: none !important;
}
textarea:focus {
    border-color: rgba(155,109,255,0.75) !important;
    box-shadow: 0 0 0 3px rgba(155,109,255,0.14) !important;
    outline: none !important;
}
textarea::placeholder { color: rgba(160,160,200,0.38) !important; }

/* ── Send button ── */
button.primary {
    background: linear-gradient(135deg, #9b6dff 0%, #22d3ee 100%) !important;
    border: none !important;
    color: #08090f !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.01em !important;
    border-radius: 0.75rem !important;
    font-family: 'Inter', sans-serif !important;
    box-shadow: 0 4px 20px -4px rgba(155,109,255,0.60) !important;
    min-height: 42px !important;
    width: 100% !important;
    margin-top: 0.5rem !important;
}
button.primary:hover { opacity: 0.84 !important; }

/* ── Template buttons ── */
button:not(.primary) {
    background: rgba(22,24,40,0.95) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    color: #c4c4dc !important;
    border-radius: 0.55rem !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8rem !important;
    line-height: 1.4 !important;
    text-align: left !important;
    white-space: normal !important;
    padding: 0.45rem 0.75rem !important;
    width: 100% !important;
    justify-content: flex-start !important;
    transition: border-color 0.15s, color 0.15s !important;
}
button:not(.primary):hover {
    border-color: rgba(155,109,255,0.50) !important;
    color: #f0f0f8 !important;
}

/* ── Label text above inputs ── */
.label-wrap span, label > span {
    color: rgba(155,109,255,0.85) !important;
    font-size: 0.68rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.16em !important;
    font-family: 'Inter', sans-serif !important;
}

/* ── Chatbot container ── */
.chatbot {
    background: #13152a !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 1rem !important;
}
/* User bubble */
.message.user .bubble-wrap {
    background: rgba(75,45,165,0.28) !important;
    border: 1px solid rgba(155,109,255,0.30) !important;
    border-radius: 0.875rem !important;
}
/* Bot bubble */
.message.bot .bubble-wrap {
    background: rgba(20,22,42,0.85) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 0.875rem !important;
}
.message p, .message li { color: #e8e8f4 !important; line-height: 1.65 !important; }
.message strong { color: #f5f5fb !important; font-weight: 600 !important; }
.message code {
    background: rgba(155,109,255,0.18) !important;
    color: #c4b5fd !important;
    border-radius: 0.25rem !important;
    padding: 0.1em 0.35em !important;
    font-size: 0.88em !important;
}

/* ── Plotly transparent background ── */
.plot-container, .plot-container > div, .js-plotly-plot, .plotly {
    background: transparent !important;
    border: none !important;
}

/* ── Thin scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(155,109,255,0.28); border-radius: 4px; }

/* ── Role badge ── */
.role-badge { display: flex; justify-content: flex-end; align-items: center; height: 100%; }

/* ── Hero ── */
.hero-wrap { padding: 0.5rem 0 1.5rem; }
.hero-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: clamp(2rem, 5vw, 2.8rem);
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.12;
    background: linear-gradient(130deg, #c4b5fd 0%, #9b6dff 45%, #22d3ee 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent !important;
    margin: 0 0 0.55rem;
}
.hero-sub {
    font-family: 'Inter', sans-serif;
    font-size: 0.9rem;
    color: rgba(180,180,220,0.68) !important;
    line-height: 1.65;
    max-width: 520px;
    margin: 0;
}

/* ── Section divider ── */
.section-head {
    font-family: 'Inter', sans-serif;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: rgba(155,109,255,0.75) !important;
    margin: 0 0 0.6rem;
    display: block;
}

/* ── Result divider line ── */
.divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.07);
    margin: 1.25rem 0;
}
"""

HERO_HTML = """
<div class="hero-wrap">
  <h1 class="hero-title">Ask your orders<br>anything.</h1>
  <p class="hero-sub">Query revenue, orders, and products in plain English.
  The agent writes SQL, queries the database, and renders charts for you.</p>
</div>
"""

TEMPLATES_LABEL = "<span class='section-head'>Quick templates</span>"
DIVIDER_HTML    = "<hr class='divider'>"


# ── Core handlers ─────────────────────────────────────────────────────────────

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


def get_role_badge(request: gr.Request) -> str:
    if not request or not request.username:
        return ""
    role = get_role(request.username)
    grad = {
        Role.ADMIN:   "linear-gradient(135deg,#9b6dff,#7c3aed)",
        Role.ANALYST: "linear-gradient(135deg,#22d3ee,#0891b2)",
        Role.VIEWER:  "linear-gradient(135deg,#34d399,#059669)",
    }.get(role, "#555")
    return (
        f"<span style='background:{grad};color:#fff;"
        f"padding:5px 16px;border-radius:999px;"
        f"font-size:0.76rem;font-weight:600;"
        f"font-family:Inter,sans-serif;letter-spacing:0.05em;"
        f"box-shadow:0 3px 12px rgba(0,0,0,0.35);'>"
        f"{request.username}&nbsp;·&nbsp;{role.value.upper()}</span>"
    )


# ── Layout ────────────────────────────────────────────────────────────────────

def build_ui():
    with gr.Blocks(
        title="CustomerServe Analytics",
        theme=gr.themes.Base(),
        css=CSS,
    ) as demo:

        # ── 1. Title row ──────────────────────────────────────────────────
        with gr.Row(equal_height=True):
            gr.HTML(HERO_HTML)
            role_badge = gr.HTML(value="", elem_classes=["role-badge"])

        # ── 2. Query box (left) + Templates (right) ───────────────────────
        with gr.Row(equal_height=False):
            with gr.Column(scale=3, min_width=300):
                msg_box = gr.Textbox(
                    placeholder="e.g.  Show me monthly revenue for 2024 …",
                    label="Your question",
                    lines=4,
                    max_lines=8,
                )
                send_btn = gr.Button("Send →", variant="primary")

            with gr.Column(scale=2, min_width=200):
                gr.HTML(TEMPLATES_LABEL)
                tpl_btns = []
                for tpl in VIEWER_TEMPLATES:
                    b = gr.Button(tpl, size="sm")
                    tpl_btns.append((b, tpl))

        # ── 3. Divider ────────────────────────────────────────────────────
        gr.HTML(DIVIDER_HTML)

        # ── 4. Response area ──────────────────────────────────────────────
        chatbot = gr.Chatbot(
            height=380,
            label="Response",
            show_label=False,
            type="messages",
            placeholder="*Your results will appear here after you send a question.*",
        )

        # ── 5. Chart ──────────────────────────────────────────────────────
        chart_output = gr.Plot(show_label=False)

        # ── Wire events ───────────────────────────────────────────────────
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

        demo.load(fn=get_role_badge, outputs=role_badge)

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
