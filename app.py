"""
Main entry point for the CustomerServe Analytics Agent.
Runs Gradio UI with built-in login.  Also mounts the FastAPI backend
on the same process so everything ships as a single HuggingFace Space.
"""

import json
import os

import gradio as gr
import plotly.io as pio
from dotenv import load_dotenv

load_dotenv()

# ── Bootstrap database (runs once on startup) ─────────────────────────────────
from database.setup import setup_database
print("Initialising database …")
setup_database()
print("Database ready.")

# ── Application imports (after DB is ready) ───────────────────────────────────
from agent.gemini_agent import get_agent
from auth.manager import get_role, gradio_auth_pairs
from auth.roles import VIEWER_TEMPLATES, Role


# ── Theme ─────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');

/* ── Base & aurora background ── */
html { color-scheme: dark; }

html, body {
    background-color: #191b2e !important;
    background-image:
        radial-gradient(ellipse at 20% 10%, rgba(124, 92, 191, 0.32) 0%, transparent 52%),
        radial-gradient(ellipse at 82% 8%,  rgba(34, 211, 238, 0.20) 0%, transparent 48%),
        radial-gradient(ellipse at 50% 96%, rgba(52, 211, 153, 0.14) 0%, transparent 52%) !important;
    background-attachment: fixed !important;
    font-family: 'Inter', system-ui, sans-serif !important;
    color: #f0f0f8 !important;
}

/* Hide Gradio branding */
footer, .built-with { display: none !important; }

/* ── Container ── */
.gradio-container {
    background: transparent !important;
    max-width: 1200px !important;
    padding-top: 1.5rem !important;
}

/* ── Glassmorphism blocks ── */
.block {
    background: rgba(33, 36, 61, 0.72) !important;
    backdrop-filter: blur(20px) saturate(140%) !important;
    -webkit-backdrop-filter: blur(20px) saturate(140%) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 1rem !important;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.05) inset,
                0 24px 48px -20px rgba(0, 0, 0, 0.55) !important;
}

/* ── Text ── */
.gradio-container p,
.gradio-container span:not(.sr-only),
.gradio-container label,
.gradio-container h1, .gradio-container h2,
.gradio-container h3, .gradio-container h4 {
    color: #f0f0f8 !important;
}
.prose { color: #f0f0f8 !important; }

/* ── Inputs ── */
input, textarea {
    background: rgba(22, 24, 44, 0.88) !important;
    border: 1px solid rgba(255, 255, 255, 0.10) !important;
    color: #f0f0f8 !important;
    border-radius: 0.75rem !important;
    font-family: 'Inter', sans-serif !important;
}
input:focus, textarea:focus {
    border-color: rgba(155, 109, 255, 0.55) !important;
    box-shadow: 0 0 0 3px rgba(155, 109, 255, 0.15) !important;
    outline: none !important;
}
input::placeholder, textarea::placeholder {
    color: rgba(180, 180, 210, 0.40) !important;
}

/* ── Primary button – purple→cyan gradient ── */
button.primary {
    background: linear-gradient(135deg, #9b6dff 0%, #22d3ee 100%) !important;
    border: none !important;
    color: #0d0f1e !important;
    font-weight: 600 !important;
    border-radius: 0.75rem !important;
    font-family: 'Inter', sans-serif !important;
    box-shadow: 0 8px 28px -6px rgba(155, 109, 255, 0.50) !important;
    transition: opacity 0.15s ease !important;
}
button.primary:hover { opacity: 0.87 !important; }

/* ── Secondary / template buttons ── */
button:not(.primary) {
    background: rgba(40, 43, 69, 0.85) !important;
    border: 1px solid rgba(255, 255, 255, 0.09) !important;
    color: #c8c8de !important;
    border-radius: 0.75rem !important;
    font-family: 'Inter', sans-serif !important;
    transition: background 0.15s ease, color 0.15s ease !important;
}
button:not(.primary):hover {
    background: rgba(55, 58, 90, 0.9) !important;
    color: #f0f0f8 !important;
}

/* ── Labels ── */
.label-wrap > span, label > span {
    color: rgba(170, 170, 200, 0.60) !important;
    font-size: 0.68rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.15em !important;
    font-family: 'Inter', sans-serif !important;
}

/* ── Chatbot bubbles ── */
.message.user .bubble-wrap {
    background: rgba(95, 60, 190, 0.22) !important;
    border: 1px solid rgba(155, 109, 255, 0.28) !important;
    border-radius: 0.875rem !important;
}
.message.bot .bubble-wrap {
    background: rgba(28, 31, 54, 0.80) !important;
    border: 1px solid rgba(255, 255, 255, 0.07) !important;
    border-radius: 0.875rem !important;
}
.message p, .message li, .message code { color: #f0f0f8 !important; }
.message code {
    background: rgba(155, 109, 255, 0.15) !important;
    border-radius: 0.25rem !important;
    padding: 0.1em 0.3em !important;
}

/* ── Accordion ── */
.accordion {
    background: rgba(26, 29, 50, 0.65) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 0.875rem !important;
}
.accordion .label-wrap { color: rgba(170, 170, 200, 0.65) !important; }

/* ── Plot area ── */
.plot-container, .plot-container > div, .js-plotly-plot {
    background: transparent !important;
}

/* ── Scrollbars ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(100, 100, 155, 0.35); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(155, 109, 255, 0.50); }

/* ── Role badge ── */
.role-badge {
    display: flex;
    justify-content: flex-end;
    align-items: flex-start;
    padding-top: 0.25rem;
}

/* ── Hero header (gr.HTML block) ── */
.hero-wrap { padding: 0.25rem 0 1.25rem; }
.hero-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: clamp(1.9rem, 3.8vw, 3rem);
    font-weight: 700;
    letter-spacing: -0.025em;
    line-height: 1.15;
    background: linear-gradient(135deg, #9b6dff 0%, #22d3ee 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent !important;
    margin: 0 0 0.55rem;
}
.hero-sub {
    font-size: 0.92rem;
    color: rgba(185, 185, 220, 0.72) !important;
    max-width: 560px;
    line-height: 1.65;
    margin: 0 0 0.75rem;
}
.hero-status {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.73rem;
    font-family: 'Courier New', monospace;
    color: rgba(150, 150, 185, 0.65) !important;
}
.hero-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #34d399;
    display: inline-block;
    animation: hpulse 2.2s ease-in-out infinite;
}
@keyframes hpulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.35; }
}
"""

HERO_HTML = """
<div class="hero-wrap">
  <h1 class="hero-title">Ask your orders<br>anything.</h1>
  <p class="hero-sub">
    Query revenue, orders, and products in plain English.
    The agent writes SQL, queries the database, and draws interactive charts for you.
  </p>
  <span class="hero-status">
    <span class="hero-dot"></span>
    Live · powered by Llama 4 Scout + DuckDB
  </span>
</div>
"""


# ── Core chat handler ─────────────────────────────────────────────────────────

def respond(message: str, history: list, request: gr.Request):
    username = request.username
    role = get_role(username)
    agent = get_agent()

    # Convert messages-format history to (user, assistant) tuples for the agent
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


# ── Role badge helper ─────────────────────────────────────────────────────────

def get_role_badge(request: gr.Request) -> str:
    if not request or not request.username:
        return ""
    role = get_role(request.username)
    colours = {
        Role.ADMIN:   "linear-gradient(135deg,#c0392b,#e74c3c)",
        Role.ANALYST: "linear-gradient(135deg,#2980b9,#22d3ee)",
        Role.VIEWER:  "linear-gradient(135deg,#27ae60,#34d399)",
    }
    grad = colours.get(role, "#555")
    return (
        f"<span style='"
        f"background:{grad};color:#fff;"
        f"padding:4px 14px;border-radius:999px;"
        f"font-size:0.78em;font-weight:600;"
        f"font-family:Inter,sans-serif;letter-spacing:0.04em;"
        f"box-shadow:0 4px 14px -4px rgba(0,0,0,0.4)'>"
        f"{request.username} · {role.value.upper()}"
        f"</span>"
    )


# ── UI layout ─────────────────────────────────────────────────────────────────

def build_ui():
    with gr.Blocks(
        title="CustomerServe Analytics",
        theme=gr.themes.Base(),
        css=CSS,
    ) as demo:

        # ── Hero header ───────────────────────────────────────────────────
        with gr.Row(equal_height=True):
            gr.HTML(HERO_HTML)
            role_badge = gr.HTML(value="", elem_classes=["role-badge"])

        with gr.Row():
            # ── Left column: chat ─────────────────────────────────────────
            with gr.Column(scale=5):
                chatbot = gr.Chatbot(height=460, label="Conversation", type="messages")

                with gr.Row():
                    msg_box = gr.Textbox(
                        placeholder="e.g. Show me monthly revenue for 2024 …",
                        label="Your question",
                        scale=5,
                        lines=1,
                    )
                    send_btn = gr.Button("Send →", variant="primary", scale=1)

                with gr.Accordion("Quick question templates", open=False):
                    gr.Markdown("*Viewers must use these templates. Analysts and Admins can also type freely.*")
                    for tpl in VIEWER_TEMPLATES:
                        gr.Button(tpl, size="sm").click(
                            fn=fill_input, inputs=gr.State(tpl), outputs=msg_box
                        )

            # ── Right column: chart ───────────────────────────────────────
            with gr.Column(scale=6):
                chart_output = gr.Plot(label="Visualisation", show_label=True)

        # ── Wire events ───────────────────────────────────────────────────
        submit_inputs  = [msg_box, chatbot]
        submit_outputs = [msg_box, chatbot, chart_output]

        send_btn.click(respond, inputs=submit_inputs, outputs=submit_outputs)
        msg_box.submit(respond, inputs=submit_inputs, outputs=submit_outputs)

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
