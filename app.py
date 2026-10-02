"""
HuggingFace Spaces entry point — Gradio SDK (ZeroGPU) wrapper around FastAPI backend.
ZeroGPU requires @spaces.GPU wired to a Gradio event handler.
"""
import os
import spaces
import gradio as gr
import uvicorn

from combined_backend import app as fastapi_app


@spaces.GPU
def _status_check():
    """ZeroGPU event handler. Backend runs CPU-only; GPU is never actually used."""
    return "Backend is running (CPU-only mode)"


with gr.Blocks(title="India Transition Lab — Backend") as _demo:
    gr.Markdown("""
# 🏭 India Transition Lab — Backend API

FastAPI serving all 5 sector LP/MILP models.

| Sector | Mount |
|--------|-------|
| Steel | `/steel/` |
| Cement | `/cement/` |
| Aluminium | `/aluminium/` |
| Textile | `/textile/` |
| Fertiliser | `/fertiliser/` |

**Health:** [`/health`](/health) &nbsp;·&nbsp; **Docs:** [`/docs`](/docs)
    """)
    with gr.Row():
        btn = gr.Button("Check Status")
        out = gr.Textbox(label="Status", interactive=False)
    btn.click(fn=_status_check, outputs=out)

app = gr.mount_gradio_app(fastapi_app, _demo, path="/ui")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
