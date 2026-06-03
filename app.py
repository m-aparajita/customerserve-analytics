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
    colours = {Role.ADMIN: "#c0392b", Role.ANALYST: "#2980b9", Role.VIEWER: "#27ae60"}
    colour = colours.get(role, "#555")
    return (
        f"<span style='background:{colour};color:#fff;padding:3px 10px;"
        f"border-radius:12px;font-size:0.85em;font-weight:bold'>"
        f"{request.username} · {role.value.upper()}</span>"
    )


# ── UI layout ─────────────────────────────────────────────────────────────────

def build_ui():
    with gr.Blocks(
        title="CustomerServe Analytics",
        theme=gr.themes.Soft(primary_hue="blue"),
        css=".role-badge {margin-bottom: 4px}",
    ) as demo:

        # Header
        with gr.Row():
            gr.Markdown("## CustomerServe Analytics Agent")
            role_badge = gr.HTML(value="", elem_classes=["role-badge"])

        gr.Markdown(
            "Ask questions about **orders**, **products**, and **sales** in plain English. "
            "The agent writes SQL, queries the database, and draws interactive charts for you."
        )

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
                    send_btn = gr.Button("Send", variant="primary", scale=1)

                # Viewer templates (visible to everyone, Viewer-only enforced in agent)
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

        # Populate role badge on page load
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
