r"""
scripts/serve_landing_page.py

Standalone Web Server for diad.d4e.ai Landing Page & Client Portal.
Use this script in any project or server to host the diad.d4e.ai landing page,
1-click installer (.bat / .ps1) downloads, and chatbot preview interfaces.

Usage:
    python scripts/serve_landing_page.py
"""

import sys
import os
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
CONFIG_PATH = ROOT_DIR / "config" / "client_rawdata.json"

app = FastAPI(title="diad.d4e.ai - Landing Page & Client Portal")

def get_config_data():
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def render_dynamic_template(file_name: str) -> str:
    file_path = WEB_DIR / file_name
    if not file_path.exists():
        file_path = ROOT_DIR / file_name
    if not file_path.exists():
        return ""
    
    content = file_path.read_text(encoding="utf-8")
    cfg = get_config_data()
    biz_name = cfg.get("client", {}).get("business_name", "Your Business")
    if not biz_name or biz_name == "YOUR_BUSINESS_NAME":
        biz_name = "Your Business"
        
    project_id = cfg.get("client", {}).get("project_id", "your-gcp-project-id")
    if not project_id or project_id == "YOUR_PROJECT_ID":
        project_id = "your-gcp-project-id"

    replacements = {
        "{{BUSINESS_NAME}}": biz_name,
        "{{PROJECT_ID}}": project_id,
        "{{EXTERNAL_API_URL}}": "/external/chat",
        "{{INTERNAL_API_URL}}": "/internal/chat"
    }
    for key, val in replacements.items():
        content = content.replace(key, val)
    return content

@app.get('/', response_class=HTMLResponse)
@app.get('/portal', response_class=HTMLResponse)
@app.get('/client', response_class=HTMLResponse)
async def get_landing_page():
    content = render_dynamic_template("index.html")
    if content:
        return HTMLResponse(content)
    raise HTTPException(status_code=404, detail="index.html landing page file not found.")

@app.get('/external_chatbot', response_class=HTMLResponse)
async def get_external_chatbot():
    content = render_dynamic_template("external_chatbot.html")
    if content:
        return HTMLResponse(content)
    raise HTTPException(status_code=404, detail="external_chatbot.html file not found.")

@app.get('/internal_chatbot', response_class=HTMLResponse)
async def get_internal_chatbot():
    content = render_dynamic_template("internal_chatbot.html")
    if content:
        return HTMLResponse(content)
    raise HTTPException(status_code=404, detail="internal_chatbot.html file not found.")

@app.get('/setup.bat')
async def download_setup_bat():
    bat_path = ROOT_DIR / "setup.bat"
    if bat_path.exists():
        return FileResponse(str(bat_path), media_type="application/x-msdos-program", filename="setup.bat")
    raise HTTPException(status_code=404, detail="setup.bat file not found.")

@app.get('/setup.ps1')
async def download_setup_ps1():
    ps1_path = ROOT_DIR / "setup.ps1"
    if ps1_path.exists():
        return FileResponse(str(ps1_path), media_type="text/plain", filename="setup.ps1")
    raise HTTPException(status_code=404, detail="setup.ps1 file not found.")

class ChatPayload(BaseModel):
    question: str
    email: str = ""
    order_number: str = ""

@app.post("/internal/chat")
async def internal_chat(payload: ChatPayload):
    return {"answer": f"📊 Executive Advisor response for: '{payload.question}'"}

@app.post("/external/chat")
async def external_chat(payload: ChatPayload):
    return {"answer": f"🛍️ Customer Support response for: '{payload.question}'"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
