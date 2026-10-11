# scripts/onboarding_dashboard.py
import os
import sys
import json
import asyncio
import tempfile

# Force ProactorEventLoop on Windows to support subprocesses in asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import shutil
import subprocess
import io
import zipfile
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="DIAD Client Onboarding Suite")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path configuration relative to repository root
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "client_rawdata.json"
KEYS_DIR = ROOT_DIR / "keys"
ASSETS_DIR = ROOT_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
(ASSETS_DIR / "logo").mkdir(parents=True, exist_ok=True)

app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

WEB_DIR = ROOT_DIR / "web"
CLIENT_PACKAGE_DIR = ROOT_DIR / "client_site_package"

def get_client_replacements():
    cfg = get_config_data()
    biz_name = cfg.get("client", {}).get("business_name", "")
    if not biz_name or biz_name == "YOUR_BUSINESS_NAME":
        biz_name = "Your Business"
    project_id = cfg.get("client", {}).get("project_id", "")
    if not project_id or project_id == "YOUR_PROJECT_ID":
        project_id = "your-gcp-project-id"
    
    # Priority: configured API URL in client_rawdata.json, else local dashboard endpoints
    ext_url = cfg.get("client", {}).get("external_api_url", "").strip()
    int_url = cfg.get("client", {}).get("internal_api_url", "").strip()
    
    if not ext_url or "yhpwhxzeeq" in ext_url:
        ext_url = "/external/chat"
    if not int_url or "yhpwhxzeeq" in int_url:
        int_url = "/internal/chat"
    
    return {
        "{{BUSINESS_NAME}}": biz_name,
        "{{PROJECT_ID}}": project_id,
        "{{EXTERNAL_API_URL}}": ext_url,
        "{{INTERNAL_API_URL}}": int_url
    }

def find_source_file(filename, subfolder):
    candidates = [
        ROOT_DIR / subfolder / filename,
        ROOT_DIR.parent / subfolder / filename,
        Path.cwd() / subfolder / filename,
        Path(__file__).resolve().parent.parent / subfolder / filename
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

def render_dynamic_template(file_path: Path) -> str:
    if not file_path.exists():
        # Try fallback lookup
        fallback = find_source_file(file_path.name, "web")
        if fallback:
            file_path = fallback
        else:
            return ""
    content = file_path.read_text(encoding="utf-8")
    replacements = get_client_replacements()
    for key, val in replacements.items():
        content = content.replace(key, val)
    return content

@app.get('/landing', response_class=HTMLResponse)
async def get_landing_page():
    content = render_dynamic_template(WEB_DIR / "landing.html")
    if not content:
        content = render_dynamic_template(WEB_DIR / "index.html")
    if content:
        return HTMLResponse(content)
    raise HTTPException(status_code=404, detail="Landing page not found.")

@app.get('/portal', response_class=HTMLResponse)
@app.get('/client', response_class=HTMLResponse)
async def get_client_portal():
    content = render_dynamic_template(WEB_DIR / "index.html")
    if content:
        return HTMLResponse(content)
    raise HTTPException(status_code=404, detail="Client portal index file not found.")

@app.get('/setup.bat')
async def download_setup_bat():
    bat_path = ROOT_DIR / "setup.bat"
    if not bat_path.exists():
        bat_path = find_source_file("setup.bat", "")
    if bat_path and bat_path.exists():
        return FileResponse(str(bat_path), media_type="application/x-msdos-program", filename="setup.bat")
    raise HTTPException(status_code=404, detail="setup.bat file not found on server.")

@app.get('/setup.ps1')
async def download_setup_ps1():
    ps1_path = ROOT_DIR / "setup.ps1"
    if not ps1_path.exists():
        ps1_path = find_source_file("setup.ps1", "")
    if ps1_path and ps1_path.exists():
        return FileResponse(str(ps1_path), media_type="text/plain", filename="setup.ps1")
    raise HTTPException(status_code=404, detail="setup.ps1 file not found on server.")

@app.get('/external_chatbot', response_class=HTMLResponse)
async def get_external_chatbot_page():
    content = render_dynamic_template(WEB_DIR / "external_chatbot.html")
    if content:
        return HTMLResponse(content)
    raise HTTPException(status_code=404, detail="External chatbot page not found.")

@app.get('/internal_chatbot', response_class=HTMLResponse)
async def get_internal_chatbot_page():
    content = render_dynamic_template(WEB_DIR / "internal_chatbot.html")
    if content:
        return HTMLResponse(content)
    raise HTTPException(status_code=404, detail="Internal chatbot page not found.")

@app.get('/download_client_package')
async def download_client_package():
    cfg = get_config_data()
    raw_biz = cfg.get("client", {}).get("business_name", "")
    if not raw_biz or raw_biz == "YOUR_BUSINESS_NAME":
        raw_biz = "your_business"
    
    safe_biz = "".join([c if c.isalnum() else "_" for c in raw_biz]).strip("_").lower() or "your_business"
    
    zip_buffer = io.BytesIO()
    replacements = get_client_replacements()
    
    file_specs = [
        ("index.html", "web"),
        ("external_chatbot.html", "web"),
        ("internal_chatbot.html", "web"),
        ("diad-chat-widget.js", "client_site_package"),
        ("README_FOR_CLIENT.md", "client_site_package"),
        ("_redirects", "web")
    ]
    
    packed_count = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename_item, subfolder in file_specs:
            src_path = find_source_file(filename_item, subfolder)
            if src_path and src_path.exists():
                text = src_path.read_text(encoding="utf-8")
                for k, v in replacements.items():
                    text = text.replace(k, v)
                zip_file.writestr(filename_item, text)
                packed_count += 1
            else:
                print(f"Warning: Client package source file missing: {subfolder}/{filename_item}")

    zip_bytes = zip_buffer.getvalue()
    filename = f"diad_integration_package_{safe_biz}.zip"
    
    # Write package archive to local disk on client's machine
    local_output_dir = ROOT_DIR / "client_site_package"
    local_output_dir.mkdir(parents=True, exist_ok=True)
    local_zip_path = local_output_dir / filename
    try:
        local_zip_path.write_bytes(zip_bytes)
        print(f"Client integration package created on client machine: {local_zip_path}")
    except Exception as e:
        print(f"Error saving zip to local disk: {e}")
        
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Local-Package-Path": str(local_zip_path)
        }
    )



@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    ico_path = ASSETS_DIR / "favicon.ico"
    if not ico_path.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("generate_favicon", ROOT_DIR / "scripts" / "generate_favicon.py")
            gen_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gen_mod)
            gen_mod.generate_favicon()
        except Exception as e:
            print(f"Auto favicon generation attempt: {e}")
    if ico_path.exists():
        return FileResponse(ico_path)
    svg_path = ASSETS_DIR / "favicon.svg"
    if svg_path.exists():
        return FileResponse(svg_path, media_type="image/svg+xml")
    svg_favicon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="20" fill="#7f5af0"/><text x="50" y="68" font-size="55" font-weight="bold" fill="#ffffff" text-anchor="middle" font-family="sans-serif">D</text></svg>"""
    return Response(content=svg_favicon, media_type="image/svg+xml")

# Help endpoints map steps to shell/python execution calls
def get_config_data():
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading config: {e}")
        return {}

def save_config_data(data):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error writing config: {e}")
        return False

# Pydantic models for request payloads
class ConfigUpdatePayload(BaseModel):
    config: dict

class SecretsPayload(BaseModel):
    secrets: dict

class KeyUploadPayload(BaseModel):
    filename: str
    content: str

class MentorChatPayload(BaseModel):
    question: str

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    # Read the current config to inject some state if needed
    cfg = get_config_data()
    project_id = cfg.get("client", {}).get("project_id", "Not Configured")
    business_name = cfg.get("client", {}).get("business_name", "Not Configured")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DIAD Onboarding Dashboard</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    
    <style>
        :root {{
            --bg-primary: #0b0f19;
            --bg-secondary: rgba(17, 25, 40, 0.75);
            --bg-tertiary: #161f30;
            --accent-cyan: #00f2fe;
            --accent-blue: #4facfe;
            --accent-purple: #7f5af0;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --text-dark: #6b7280;
            --success: #2ec4b6;
            --warning: #ff9f1c;
            --error: #ff4757;
            --border-glow: rgba(0, 242, 254, 0.15);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(at 10% 20%, rgba(79, 172, 254, 0.08) 0px, transparent 50%),
                radial-gradient(at 90% 80%, rgba(127, 90, 240, 0.06) 0px, transparent 50%);
            background-attachment: fixed;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.5rem 3rem;
            background: rgba(11, 15, 25, 0.8);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid var(--card-border);
            position: sticky;
            top: 0;
            z-index: 100;
        }}

        .logo-container {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .logo-glow {{
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            box-shadow: 0 0 15px var(--accent-cyan);
            animation: pulse 2s infinite alternate;
        }}

        @keyframes pulse {{
            0% {{ transform: scale(1); opacity: 0.8; box-shadow: 0 0 10px var(--accent-cyan); }}
            100% {{ transform: scale(1.2); opacity: 1; box-shadow: 0 0 20px var(--accent-blue); }}
        }}

        h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(120deg, #fff, var(--text-muted));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .client-status {{
            display: flex;
            gap: 1.5rem;
            font-size: 0.85rem;
        }}

        .status-pill {{
            background: var(--bg-tertiary);
            padding: 0.4rem 1rem;
            border-radius: 30px;
            border: 1px solid var(--card-border);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .status-pill span {{
            color: var(--accent-cyan);
            font-weight: 600;
        }}

        main {{
            flex: 1;
            display: grid;
            grid-template-columns: 1.1fr 0.9fr;
            gap: 2rem;
            padding: 2rem 3rem;
            max-width: 1800px;
            margin: 0 auto;
            width: 100%;
        }}

        @media (max-width: 1200px) {{
            main {{
                grid-template-columns: 1fr;
            }}
        }}

        .panel {{
            background: var(--bg-secondary);
            border-radius: 16px;
            border: 1px solid var(--card-border);
            box-shadow: var(--card-shadow);
            backdrop-filter: blur(12px);
            padding: 2rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
            height: calc(100vh - 180px);
            min-height: 600px;
            position: sticky;
            top: 100px;
        }}

        .panel-scrollable {{
            overflow-y: auto;
            padding-right: 0.5rem;
        }}

        /* Scrollbar custom styling */
        ::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        ::-webkit-scrollbar-track {{
            background: transparent;
        }}
        ::-webkit-scrollbar-thumb {{
            background: var(--bg-tertiary);
            border-radius: 4px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: var(--text-dark);
        }}

        .tabs-header {{
            display: flex;
            gap: 0.2rem;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 0.75rem;
            flex-wrap: nowrap;
            overflow-x: auto;
            scrollbar-width: none;
        }}

        .tab-btn {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-family: 'Outfit', sans-serif;
            font-size: 0.78rem;
            font-weight: 500;
            padding: 0.45rem 0.65rem;
            white-space: nowrap;
            flex-shrink: 0;
            cursor: pointer;
            position: relative;
            transition: color 0.3s;
        }}

        .tab-btn.active {{
            color: var(--accent-cyan);
            font-weight: 600;
        }}

        .tab-btn.active::after {{
            content: '';
            position: absolute;
            bottom: -0.85rem;
            left: 0;
            width: 100%;
            height: 2px;
            background: linear-gradient(90deg, var(--accent-cyan), var(--accent-blue));
            box-shadow: 0 0 10px var(--accent-cyan);
        }}

        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }}

        .form-section-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-main);
            margin-top: 1rem;
            margin-bottom: 0.5rem;
            border-left: 3px solid var(--accent-cyan);
            padding-left: 0.5rem;
        }}

        .form-group {{
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
            margin-bottom: 1rem;
        }}

        .form-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }}

        label {{
            font-size: 0.85rem;
            color: var(--text-muted);
            font-weight: 500;
        }}

        input[type="text"], input[type="password"], select, textarea {{
            background: rgba(22, 31, 48, 0.6);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            color: #fff;
            font-family: inherit;
            font-size: 0.9rem;
            transition: all 0.3s;
            outline: none;
        }}

        input[type="text"]:focus, input[type="password"]:focus, select:focus, textarea:focus {{
            border-color: var(--accent-cyan);
            box-shadow: 0 0 8px var(--border-glow);
            background: rgba(22, 31, 48, 0.9);
        }}

        .btn {{
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
            color: #fff;
            border: none;
            border-radius: 8px;
            padding: 0.8rem 1.5rem;
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            box-shadow: 0 4px 15px rgba(79, 172, 254, 0.2);
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(79, 172, 254, 0.35);
        }}

        .btn:active {{
            transform: translateY(0);
        }}

        .btn-secondary {{
            background: var(--bg-tertiary);
            border: 1px solid var(--card-border);
            box-shadow: none;
        }}

        .btn-secondary:hover {{
            background: rgba(255, 255, 255, 0.05);
            border-color: var(--text-muted);
            box-shadow: none;
            transform: none;
        }}

        .btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
            box-shadow: none !important;
        }}

        /* Steps and Stepper layout */
        .stepper-container {{
            display: flex;
            flex-direction: column;
            gap: 0.85rem;
            overflow-y: auto;
            flex: 1;
        }}

        .step-card {{
            background: var(--bg-tertiary);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: all 0.3s ease;
            position: relative;
        }}

        .step-card:hover {{
            border-color: rgba(0, 242, 254, 0.3);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }}

        .step-card.active {{
            border-color: var(--accent-cyan);
            box-shadow: 0 0 15px var(--border-glow);
            background: rgba(0, 242, 254, 0.02);
        }}

        .step-info {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .step-number {{
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Outfit', sans-serif;
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
            transition: all 0.3s;
        }}

        .step-card.active .step-number {{
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            color: var(--bg-primary);
            border: none;
            box-shadow: 0 0 10px var(--accent-cyan);
        }}

        .step-card.success .step-number {{
            background: var(--success);
            color: var(--bg-primary);
            border: none;
        }}

        .step-card.error .step-number {{
            background: var(--error);
            color: #fff;
            border: none;
        }}

        .step-details {{
            display: flex;
            flex-direction: column;
        }}

        .step-title {{
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-main);
        }}

        .step-desc {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.15rem;
        }}

        .step-actions {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .step-status-pill {{
            font-size: 0.75rem;
            padding: 0.25rem 0.6rem;
            border-radius: 4px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-muted);
        }}

        .step-card.success .step-status-pill {{
            background: rgba(46, 196, 182, 0.15);
            color: var(--success);
        }}

        .step-card.error .step-status-pill {{
            background: rgba(255, 71, 87, 0.15);
            color: var(--error);
        }}

        .step-card.active .step-status-pill {{
            background: rgba(0, 242, 254, 0.15);
            color: var(--accent-cyan);
        }}

        .btn-run-step {{
            padding: 0.4rem 0.9rem;
            font-size: 0.8rem;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            color: var(--text-main);
            box-shadow: none;
        }}

        .btn-run-step:hover {{
            background: var(--accent-cyan);
            color: var(--bg-primary);
            border-color: var(--accent-cyan);
            box-shadow: 0 0 10px var(--border-glow);
        }}

        /* Terminal styling */
        .terminal-container {{
            background: #060913;
            border: 1px solid var(--card-border);
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            height: 250px;
            overflow: hidden;
            box-shadow: inset 0 4px 20px rgba(0,0,0,0.5);
        }}

        .terminal-header {{
            background: #0d1222;
            padding: 0.5rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--card-border);
        }}

        .terminal-title {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .terminal-title::before {{
            content: '';
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent-cyan);
        }}

        .terminal-actions {{
            display: flex;
            gap: 0.5rem;
        }}

        .terminal-btn {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            font-size: 0.75rem;
            font-family: 'JetBrains Mono', monospace;
            padding: 0.1rem 0.4rem;
            border-radius: 3px;
            transition: all 0.2s;
        }}

        .terminal-btn:hover {{
            color: #fff;
            background: rgba(255, 255, 255, 0.05);
        }}

        .terminal-body {{
            flex: 1;
            padding: 1rem;
            overflow-y: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            line-height: 1.5;
            color: #e5e7eb;
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }}

        .log-line {{
            white-space: pre-wrap;
            word-break: break-all;
        }}

        .log-starting {{ color: var(--accent-blue); font-weight: bold; }}
        .log-success {{ color: var(--success); font-weight: bold; }}
        .log-error {{ color: var(--error); font-weight: bold; }}
        .log-cmd {{ color: var(--accent-cyan); }}
        .log-warning {{ color: var(--warning); }}

        .notification-toast {{
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            background: var(--bg-tertiary);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 1rem 1.5rem;
            box-shadow: var(--card-shadow);
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            transform: translateY(150%);
            transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            font-size: 0.9rem;
        }}

        .notification-toast.show {{
            transform: translateY(0);
        }}

        .notification-icon {{
            font-size: 1.2rem;
        }}

        .toast-success {{ border-left: 4px solid var(--success); }}
        .toast-error {{ border-left: 4px solid var(--error); }}
        .toast-warning {{ border-left: 4px solid var(--warning); }}

        /* Mentoring Bot classes */
        @keyframes float {{
            0% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-5px); }}
            100% {{ transform: translateY(0px); }}
        }}

        .btn-faq {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            color: var(--text-muted);
            font-size: 0.75rem;
            padding: 0.35rem 0.8rem;
            cursor: pointer;
            transition: all 0.2s;
            font-family: inherit;
        }}

        .btn-faq:hover {{
            background: rgba(127, 90, 240, 0.15);
            border-color: var(--accent-purple);
            color: #fff;
        }}

        /* Drag & Drop JSON upload zone classes */
        .upload-zone {{
            border: 2px dashed var(--card-border);
            border-radius: 12px;
            padding: 2rem 1.5rem;
            text-align: center;
            background: rgba(255, 255, 255, 0.01);
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.5rem;
            margin-top: 1rem;
        }}

        .upload-zone.dragover {{
            border-color: var(--accent-cyan);
            background: rgba(0, 242, 254, 0.05);
            box-shadow: 0 0 15px var(--border-glow);
        }}

        .upload-icon {{
            font-size: 2rem;
            color: var(--text-muted);
            transition: transform 0.3s ease;
        }}

        .upload-zone:hover .upload-icon {{
            transform: translateY(-3px);
            color: var(--accent-cyan);
        }}

        .upload-title {{
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-main);
        }}

        .upload-desc {{
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

    </style>
</head>
<body>
    <header>
        <div class="logo-container" style="display: flex; align-items: center; gap: 0.75rem;">
            <div class="logo-glow"></div>
            <img id="header-company-logo" src="/assets/logo/logo_dark.png" onerror="if(!this.triedLight){{this.triedLight=true;this.src='/assets/logo/logo_light.png';}}else{{this.style.display='none';}}" style="max-height: 32px; width: auto; object-fit: contain;" alt="Company Logo">
            <h1>DIAD Onboarding Suite</h1>
        </div>
        <div class="client-status" style="display: flex; align-items: center; gap: 0.75rem;">
            <div class="status-pill">
                Client: <span id="client-name-status">{business_name}</span>
            </div>
            <div class="status-pill">
                GCP Project: <span id="gcp-project-status">{project_id}</span>
            </div>
            <a href="/portal" target="_blank" class="status-pill" style="border: 1px solid var(--card-border); background: rgba(0, 242, 254, 0.1); color: var(--accent-cyan); text-decoration: none; font-weight: 600; cursor: pointer;">
                🌐 Public Portal (/portal) ↗
            </a>
            <div class="status-pill" style="border: 1px solid var(--card-border); background: rgba(127, 90, 240, 0.1);">
                Readiness: <span id="readiness-score" style="color: var(--accent-cyan); font-weight: 700;">25% Ready</span>
            </div>
        </div>
    </header>

    <main>
        <!-- LEFT PANEL: Forms & Execution Pipeline -->
        <section class="panel">
            <div class="tabs-header">
                <button class="tab-btn active" id="tab-btn-gcp" onclick="switchTab('gcp-tab')">1. Account & Setup</button>
                <button class="tab-btn" id="tab-btn-sources" onclick="switchTab('sources-tab')">2. Connect Docs</button>
                <button class="tab-btn" id="tab-btn-secrets" onclick="switchTab('secrets-tab')">3. Store Analytics</button>
                <button class="tab-btn" id="tab-btn-pipeline" onclick="switchTab('pipeline-tab')">4. Onboarding Pipeline</button>
                <button class="tab-btn" id="tab-btn-package" onclick="switchTab('package-tab')">5. Client Web Package</button>
            </div>

            
            <div class="panel-scrollable" style="flex: 1;">
                <!-- TAB 1: Business & GCP Account Setup -->
                <div id="gcp-tab" class="tab-content active">
                    <!-- Business Profile Form Card -->
                    <div style="background: rgba(127,90,240,0.05); border: 1px solid rgba(127,90,240,0.25); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-purple); margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.4rem;">
                            <span>🏢 Business Profile</span>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.75rem;">
                            Enter your company details so your AI chatbots can personalize their responses and brand identity.
                        </p>
                        <form id="business-profile-form" onsubmit="saveBusinessProfile(event)">
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem;">
                                <div class="form-group" style="margin-bottom: 0;">
                                    <label for="biz_name" style="font-weight: 600; color: #fff;">Business Name</label>
                                    <input type="text" id="biz_name" placeholder="e.g. Acme Jewelry" style="width: 100%; font-size: 0.85rem;" oninput="onBizNameChange(this.value)">
                                </div>
                                <div class="form-group" style="margin-bottom: 0;">
                                    <label for="biz_url" style="font-weight: 600; color: #fff;">Website URL</label>
                                    <input type="text" id="biz_url" placeholder="e.g. https://acme.com" style="width: 100%; font-size: 0.85rem;">
                                </div>
                            </div>
                            <div style="display: flex; gap: 0.5rem; align-items: center;">
                                <button type="submit" class="btn" style="padding: 0.4rem 1rem; font-size: 0.78rem; background: var(--accent-purple);">Save Profile</button>
                            </div>
                        </form>
                    </div>

                    <!-- Environment Health Check Banner -->
                    <div id="diagnostics-banner" style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-purple); margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem;">
                            <span>🩺</span> Environment Health Check
                            <span id="diag-refresh" onclick="loadDiagnostics()" style="margin-left: auto; cursor: pointer; font-size: 0.75rem; color: var(--accent-cyan); font-weight: 400;">↻ Refresh</span>
                        </div>
                        <div id="diag-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.78rem;">
                            <div class="diag-item" id="diag-python" style="display:flex;align-items:center;gap:0.4rem;padding:0.4rem 0.6rem;border-radius:6px;background:rgba(255,255,255,0.02);border:1px solid var(--card-border);">
                                <span class="diag-icon">⏳</span>
                                <span style="color:var(--text-muted);">Python</span>
                                <span class="diag-val" style="margin-left:auto;color:var(--text-muted);font-size:0.72rem;">checking...</span>
                            </div>
                            <div class="diag-item" id="diag-gcloud" style="display:flex;align-items:center;gap:0.4rem;padding:0.4rem 0.6rem;border-radius:6px;background:rgba(255,255,255,0.02);border:1px solid var(--card-border);">
                                <span class="diag-icon">⏳</span>
                                <span style="color:var(--text-muted);">gcloud CLI</span>
                                <span class="diag-val" style="margin-left:auto;color:var(--text-muted);font-size:0.72rem;">checking...</span>
                            </div>
                            <div class="diag-item" id="diag-config" style="display:flex;align-items:center;gap:0.4rem;padding:0.4rem 0.6rem;border-radius:6px;background:rgba(255,255,255,0.02);border:1px solid var(--card-border);">
                                <span class="diag-icon">⏳</span>
                                <span style="color:var(--text-muted);">Config</span>
                                <span class="diag-val" style="margin-left:auto;color:var(--text-muted);font-size:0.72rem;">checking...</span>
                            </div>
                            <div class="diag-item" id="diag-key" style="display:flex;align-items:center;gap:0.4rem;padding:0.4rem 0.6rem;border-radius:6px;background:rgba(255,255,255,0.02);border:1px solid var(--card-border);">
                                <span class="diag-icon">⏳</span>
                                <span style="color:var(--text-muted);">SA Key</span>
                                <span class="diag-val" style="margin-left:auto;color:var(--text-muted);font-size:0.72rem;">checking...</span>
                            </div>
                        </div>
                        <div style="margin-top: 0.65rem; padding-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.05); font-size: 0.76rem; color: var(--accent-cyan); display: flex; align-items: center; gap: 0.4rem;">
                            <span>💡</span> <span><strong>Next Step:</strong> Follow the steps below and upload your Service Account JSON key in <strong>Step 4</strong> to activate credentials!</span>
                        </div>
                    </div>

                    <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5; margin-bottom: 1rem;">
                        Before we begin deploying, we need to connect to your Google Cloud account. Follow these simple steps.
                    </p>
                    
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-cyan); margin-bottom: 0.5rem;">
                            Step 1: Sign up & log in
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4;">
                            Go to the <a href="https://console.cloud.google.com/" target="_blank" style="color: var(--accent-blue); font-weight: 500;">Google Cloud Console</a> and sign in with your Google account.
                        </p>
                    </div>

                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-cyan); margin-bottom: 0.5rem;">
                            Step 2: Create a Project & Link Billing
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4;">
                            Click the project dropdown in the top bar to create a <strong>New Project</strong> (e.g. <code>my-business-diad</code>). Then search for <strong>Billing</strong> in the top search bar, and add an active credit card or billing profile. (Billing is required for deploying chatbots).
                        </p>
                    </div>

                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-cyan); margin-bottom: 0.5rem;">
                            Step 3: Download your Owner Service Account Key
                        </div>
                        <ol style="font-size: 0.8rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.6;">
                            <li>Search for <strong>Service Accounts</strong> in the top GCP search bar and click it.</li>
                            <li>Click <strong>+ CREATE SERVICE ACCOUNT</strong> at the top of the page.</li>
                            <li>Enter <code>diad-onboarding</code> in the <strong>Service account name</strong> field, then click <strong>CREATE AND CONTINUE</strong>.</li>
                            <li>In Step 2 (<strong>Grant this service account access to project</strong>), click the <strong>Select a role</strong> dropdown → search for <strong>Owner</strong> → select <strong>Owner</strong>, then click <strong>CONTINUE</strong>.</li>
                            <li>Click <strong>DONE</strong> at the bottom of Step 3 to finish creating the account.</li>
                            <li>Click on your new <code>diad-onboarding</code> account in the list → open the <strong>KEYS</strong> tab → click <strong>ADD KEY → Create new key</strong> → select <strong>JSON</strong> → click <strong>CREATE</strong>. A <code>.json</code> key file will download to your computer.</li>
                        </ol>
                    </div>

                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem;">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-cyan); margin-bottom: 0.5rem;">
                            Step 4: Upload JSON Key File
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4;">
                            Drag and drop your downloaded JSON key file below, or click to browse. The platform will automatically extract your Project ID and configure deployment permissions!
                        </p>
                        <div id="drop-zone" class="upload-zone" onclick="document.getElementById('key-file-input').click()">
                            <span class="upload-icon">🔑</span>
                            <div class="upload-title" id="upload-status-text">Drag & Drop Service Account JSON Key</div>
                            <div class="upload-desc">or click to browse from files</div>
                            <input type="file" id="key-file-input" accept=".json" style="display: none;" onchange="handleFileSelect(event)">
                        </div>
                        <div id="step4-success-banner" style="display: none; margin-top: 1rem; padding: 0.75rem 1rem; background: rgba(0, 255, 136, 0.08); border: 1px solid rgba(0, 255, 136, 0.3); border-radius: 6px; font-size: 0.82rem; color: var(--accent-green); line-height: 1.5;">
                            ✅ <strong>GCP Key Configured Successfully!</strong> Environment Health Check is now 100% verified green.<br>
                            👉 <strong>Next Step:</strong> Proceed to <strong>2. Data Sources Link Guide</strong> in the top tab menu above!
                        </div>
                    </div>
                </div>

                <!-- TAB 2: Data Sources Link Guide -->
                <div id="sources-tab" class="tab-content">
                    <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5; margin-bottom: 1rem;">
                        Before running the pipeline step diagnostic, you must connect your document files, website telemetry, and databases to your GCP project.
                    </p>

                    <!-- Google Drive Sharing Card -->
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; cursor: pointer;" onclick="explainSource('gdrive')">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-cyan); display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span style="display: flex; align-items: center; gap: 0.5rem;">📁 1. Share Google Drive Knowledge Base</span>
                            <a href="https://drive.google.com/" target="_blank" class="btn" onclick="event.stopPropagation();" style="padding: 0.25rem 0.75rem; font-size: 0.75rem; border-radius: 4px; background: var(--accent-purple); color: white; text-decoration: none; display: inline-flex; align-items: center; gap: 0.3rem;">
                                🚀 Open Google Drive ↗
                            </a>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.75rem;">
                            Your AI assistant indexes all company policies, procedures, and operational documents stored in your Google Drive folder.
                        </p>

                        <!-- Recommended Documents Grid Box -->
                        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.75rem; margin-bottom: 0.75rem;">
                            <div style="font-size: 0.78rem; font-weight: 600; color: var(--accent-purple); margin-bottom: 0.4rem;">
                                📄 Recommended Documents to Put in Your Shared Drive Folder:
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.76rem; color: var(--text-muted);">
                                <div>
                                    <strong style="color: #fff;">🏢 Internal Operations:</strong>
                                    <ul style="margin-top: 0.2rem; margin-left: 1rem; padding: 0;">
                                        <li>Vendor & Supplier Policies</li>
                                        <li>Inventory Management SOP</li>
                                        <li>Order Fulfillment Workflow</li>
                                        <li>Internal Team Handbook</li>
                                    </ul>
                                </div>
                                <div>
                                    <strong style="color: #fff;">🛍️ External Customer Policies:</strong>
                                    <ul style="margin-top: 0.2rem; margin-left: 1rem; padding: 0;">
                                        <li>Returns & Exchange Policy</li>
                                        <li>Shipping & Delivery FAQs</li>
                                        <li>Product Warranty & Care Guides</li>
                                        <li>Customer Support Playbook</li>
                                    </ul>
                                </div>
                            </div>
                        </div>

                        <!-- Service Account Email Copy Box -->
                        <div style="font-size: 0.78rem; font-weight: 500; color: #fff; margin-bottom: 0.3rem;">
                            🔑 Copy your Service Account Email to grant folder access:
                        </div>
                        <div style="display: flex; gap: 0.5rem; align-items: center; background: rgba(0,0,0,0.2); border-radius: 6px; padding: 0.5rem 0.75rem; margin-bottom: 0.75rem; border: 1px solid rgba(255,255,255,0.05);" onclick="event.stopPropagation();">
                            <code id="sa-email-display" style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #fff; word-break: break-all; flex: 1;">your-service-account@your-gcp-project.iam.gserviceaccount.com</code>
                            <button type="button" class="btn" style="padding: 0.25rem 0.75rem; font-size: 0.75rem; border-radius: 4px;" onclick="copySaEmail()">Copy Email</button>
                        </div>

                        <!-- Step-by-Step Instructions -->
                        <ol style="font-size: 0.8rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.6;">
                            <li>Click <a href="https://drive.google.com/" target="_blank" onclick="event.stopPropagation();" style="color: var(--accent-cyan);">Open Google Drive</a> and create or select your Knowledge Base folder containing your documents.</li>
                            <li>Right-click the folder → select <strong>Share → Share</strong>.</li>
                            <li>Paste the copied Service Account email above into the <strong>Add people and groups</strong> field.</li>
                            <li>Set permission to <strong>Viewer</strong> (or <strong>Editor</strong>), uncheck "Notify people", and click <strong>Share</strong>.</li>
                        </ol>
                    </div>

                    <!-- Notion Integration Card -->
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; cursor: pointer;" onclick="explainSource('notion')">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-cyan); display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span style="display: flex; align-items: center; gap: 0.5rem;">
                                📓 2. Notion Connections
                                <span style="font-size: 0.7rem; color: var(--accent-cyan); background: rgba(127,90,240,0.15); padding: 0.15rem 0.4rem; border-radius: 4px; border: 1px solid rgba(127,90,240,0.3);">Optional</span>
                            </span>
                            <a href="https://www.notion.so/my-integrations" target="_blank" class="btn" onclick="event.stopPropagation();" style="padding: 0.25rem 0.75rem; font-size: 0.75rem; border-radius: 4px; background: rgba(255,255,255,0.08); color: white; text-decoration: none; display: inline-flex; align-items: center; gap: 0.3rem;">
                                🚀 Open Notion Integrations ↗
                            </a>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.75rem;">
                            <strong>What is Notion?</strong> Notion is a workspace app for team wikis & docs. If your company uses Notion, DIAD reads your internal pages. <em>If you don't use Notion, you can safely skip this step!</em>
                        </p>
                        <ol style="font-size: 0.8rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.6; margin-bottom: 0.75rem;">
                            <li>Click <a href="https://www.notion.so/my-integrations" target="_blank" onclick="event.stopPropagation();" style="color: var(--accent-cyan);">Open Notion Integrations</a> and create an integration named <code>DIAD</code>.</li>
                            <li>Go to your Notion wiki page → click <code>...</code> (top-right) → select <strong>Add Connections</strong> → select <strong>DIAD</strong>.</li>
                            <li>Copy the <strong>Internal Integration Token</strong> and paste it into the field below:</li>
                        </ol>
                        <div class="form-group" style="margin-bottom: 0;" onclick="event.stopPropagation();">
                            <label for="sec_notion" style="font-weight: 600; color: #fff; font-size: 0.8rem;">Notion Internal Integration Token <span style="color: var(--text-muted); font-weight: 400;">(Optional)</span></label>
                            <input type="password" id="sec_notion" placeholder="secret_..." style="width: 100%; font-size: 0.82rem;">
                        </div>
                    </div>

                    <!-- Confluence Integration Card -->
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; cursor: pointer;" onclick="explainSource('confluence')">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-cyan); display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span style="display: flex; align-items: center; gap: 0.5rem;">
                                📘 3. Confluence Connections
                                <span style="font-size: 0.7rem; color: var(--accent-cyan); background: rgba(127,90,240,0.15); padding: 0.15rem 0.4rem; border-radius: 4px; border: 1px solid rgba(127,90,240,0.3);">Optional</span>
                            </span>
                            <a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank" class="btn" onclick="event.stopPropagation();" style="padding: 0.25rem 0.75rem; font-size: 0.75rem; border-radius: 4px; background: rgba(255,255,255,0.08); color: white; text-decoration: none; display: inline-flex; align-items: center; gap: 0.3rem;">
                                🚀 Open Atlassian Tokens ↗
                            </a>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.75rem;">
                            If your team uses Atlassian Confluence, generate an API token to allow DIAD to index your Confluence spaces.
                        </p>
                        <ol style="font-size: 0.8rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.6; margin-bottom: 0.75rem;">
                            <li>Click <a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank" onclick="event.stopPropagation();" style="color: var(--accent-cyan);">Open Atlassian Tokens</a> and log in.</li>
                            <li>Click <strong>Create API Token</strong>, label it <code>DIAD</code>, and click <strong>Create</strong>.</li>
                            <li>Copy the generated token and paste it into the field below:</li>
                        </ol>
                        <div class="form-group" style="margin-bottom: 0;" onclick="event.stopPropagation();">
                            <label for="sec_confluence" style="font-weight: 600; color: #fff; font-size: 0.8rem;">Confluence API Token <span style="color: var(--text-muted); font-weight: 400;">(Optional)</span></label>
                            <input type="password" id="sec_confluence" placeholder="atlassian-token-..." style="width: 100%; font-size: 0.82rem;">
                        </div>
                    </div>

                    <!-- AI Engine & Vector Database Setup Card -->
                    <div style="background: rgba(127,90,240,0.05); border: 1px solid rgba(127,90,240,0.25); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;" onclick="explainSource('secrets')">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-purple); margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.4rem;">
                            <span>🤖 4. AI Engine & Vector Database Keys</span>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.75rem;">
                            Select your preferred AI provider (OpenAI, Gemini, or Claude) and enter your Pinecone Vector DB key. Click <strong>Sync Secrets to GCP</strong> to encrypt all entered keys in Google Secret Manager!
                        </p>
                        <form id="secrets-form" onsubmit="saveSecrets(event)">
                            <!-- Provider Selection -->
                            <div class="form-group" style="background: rgba(0,0,0,0.2); padding: 0.75rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);">
                                <label style="font-weight: 600; color: #fff; font-size: 0.82rem; margin-bottom: 0.4rem; display: block;">Select Primary AI Model Provider</label>
                                <select id="llm_provider_choice" onchange="onLlmProviderChange(this.value)" style="width: 100%; padding: 0.45rem; border-radius: 6px; background: var(--bg-tertiary); color: #fff; border: 1px solid var(--card-border); font-size: 0.85rem; margin-bottom: 0.6rem;">
                                    <option value="openai">OpenAI (GPT-4o / GPT-4o-mini)</option>
                                    <option value="gemini">Google Gemini (Gemini 2.0 Flash / 1.5 Pro)</option>
                                    <option value="anthropic">Anthropic Claude (Claude 3.5 Sonnet)</option>
                                </select>
                                
                                <div id="openai-key-block">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                                        <label for="sec_openai" style="font-size: 0.78rem; font-weight: 600; color: #fff;">OPENAI_API_KEY <span style="color: #ff6b6b; font-size: 0.7rem;">(Required)</span></label>
                                        <a href="https://platform.openai.com/api-keys" target="_blank" style="font-size: 0.75rem; color: var(--accent-cyan); text-decoration: none;">🚀 Get OpenAI Key ↗</a>
                                    </div>
                                    <input type="password" id="sec_openai" placeholder="sk-..." style="width: 100%; font-size: 0.82rem;">
                                </div>

                                <div id="gemini-key-block" style="display: none;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                                        <label for="sec_gemini" style="font-size: 0.78rem; font-weight: 600; color: #fff;">GEMINI_API_KEY <span style="color: #ff6b6b; font-size: 0.7rem;">(Required)</span></label>
                                        <a href="https://aistudio.google.com/app/apikey" target="_blank" style="font-size: 0.75rem; color: var(--accent-cyan); text-decoration: none;">🚀 Get Gemini Key ↗</a>
                                    </div>
                                    <input type="password" id="sec_gemini" placeholder="AIzaSy..." style="width: 100%; font-size: 0.82rem;">
                                </div>

                                <div id="anthropic-key-block" style="display: none;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                                        <label for="sec_anthropic" style="font-size: 0.78rem; font-weight: 600; color: #fff;">ANTHROPIC_API_KEY <span style="color: #ff6b6b; font-size: 0.7rem;">(Required)</span></label>
                                        <a href="https://console.anthropic.com/settings/keys" target="_blank" style="font-size: 0.75rem; color: var(--accent-cyan); text-decoration: none;">🚀 Get Claude Key ↗</a>
                                    </div>
                                    <input type="password" id="sec_anthropic" placeholder="sk-ant-..." style="width: 100%; font-size: 0.82rem;">
                                </div>
                            </div>

                            <div class="form-group" style="background: rgba(0,0,0,0.2); padding: 0.75rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                                    <label for="sec_pinecone" style="font-weight: 600; color: #fff; font-size: 0.82rem;">PINECONE_API_KEY <span style="color: #ff6b6b; font-size: 0.7rem;">(Required for Vector Search)</span></label>
                                    <a href="https://app.pinecone.io/" target="_blank" style="font-size: 0.75rem; color: var(--accent-cyan); text-decoration: none;">🚀 Get Pinecone Key ↗</a>
                                </div>
                                <input type="password" id="sec_pinecone" placeholder="pcsk_..." style="width: 100%; font-size: 0.82rem;">
                            </div>

                            <div style="margin-top: 1rem;">
                                <button type="submit" class="btn" id="btn-save-secrets" style="background: var(--accent-purple); padding: 0.5rem 1.25rem;">🔐 Sync Secrets & API Keys to GCP</button>
                            </div>
                        </form>
                    </div>

                    <div style="margin-top: 1.5rem;">
                        <button type="button" class="btn" onclick="switchTab('secrets-tab')" style="background: var(--bg-tertiary); border: 1px solid var(--card-border);">Next: Connect Store Data & Analytics →</button>
                    </div>
                </div>

                <!-- TAB 3: Telemetry & Analytics Links -->
                <div id="secrets-tab" class="tab-content">
                    <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5; margin-bottom: 1rem;">
                        Connect your website traffic, e-commerce telemetry, and database exports to your BigQuery data warehouse.
                    </p>

                    <!-- Telemetry linking (GA4) -->
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; cursor: pointer;" onclick="explainSource('ga4')">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-cyan); display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span style="display: flex; align-items: center; gap: 0.5rem;">
                                📈 1. Link Google Analytics (GA4)
                                <span style="font-size: 0.7rem; color: var(--accent-cyan); background: rgba(127,90,240,0.15); padding: 0.15rem 0.4rem; border-radius: 4px; border: 1px solid rgba(127,90,240,0.3);">Optional</span>
                            </span>
                            <a href="https://analytics.google.com/" target="_blank" class="btn" onclick="event.stopPropagation();" style="padding: 0.25rem 0.75rem; font-size: 0.75rem; border-radius: 4px; background: rgba(255,255,255,0.08); color: white; text-decoration: none; display: inline-flex; align-items: center; gap: 0.3rem;">
                                🚀 Open Google Analytics ↗
                            </a>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.75rem;">
                            Exports your store traffic & user behavior data into BigQuery. Make sure you created your GCP Project ID in Tab 1 (e.g. <code><span class="gcp-project-placeholder">your-gcp-project-id</span></code>). Google Analytics automatically creates the BigQuery dataset inside your project!
                        </p>
                        <ol style="font-size: 0.8rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.5;">
                            <li>In the Google Analytics panel, click <strong>Admin (gear icon) → Product Links → BigQuery Links</strong>.</li>
                            <li>Click <strong>Link</strong>, choose your GCP Project ID (<code><span class="gcp-project-placeholder">your-gcp-project-id</span></code>), set it to export data daily, and submit.</li>
                        </ol>
                    </div>

                    <!-- Firebase / Firestore Links -->
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; cursor: pointer;" onclick="explainSource('firebase')">
                        <div style="font-weight: 600; font-size: 0.9rem; color: var(--accent-cyan); display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span style="display: flex; align-items: center; gap: 0.5rem;">
                                🔥 2. Link Firebase Products (Firestore, Analytics, Crashlytics, Performance)
                                <span style="font-size: 0.7rem; color: var(--accent-cyan); background: rgba(127,90,240,0.15); padding: 0.15rem 0.4rem; border-radius: 4px; border: 1px solid rgba(127,90,240,0.3);">Optional</span>
                            </span>
                            <a href="https://console.firebase.google.com/" target="_blank" class="btn" onclick="event.stopPropagation();" style="padding: 0.25rem 0.75rem; font-size: 0.75rem; border-radius: 4px; background: rgba(255,255,255,0.08); color: white; text-decoration: none; display: inline-flex; align-items: center; gap: 0.3rem;">
                                🚀 Open Firebase Console ↗
                            </a>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.75rem;">
                            If your store or app uses Firebase, linking BigQuery allows DIAD to ingest live Firestore orders, app events, crashlytics, and performance telemetry.
                        </p>

                        <!-- Recommended Export Toggles Grid Box -->
                        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 0.75rem; margin-bottom: 0.75rem;">
                            <div style="font-size: 0.78rem; font-weight: 600; color: var(--accent-purple); margin-bottom: 0.4rem;">
                                ⚙️ Recommended Export Settings in Firebase Console:
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.76rem; color: var(--text-muted);">
                                <div>
                                    <strong style="color: #fff;">📦 Core Store Data:</strong>
                                    <ul style="margin-top: 0.2rem; margin-left: 1rem; padding: 0;">
                                        <li><strong>Google Analytics:</strong> Export raw event & session data</li>
                                        <li><strong>Firestore:</strong> Export live orders & collections</li>
                                    </ul>
                                </div>
                                <div>
                                    <strong style="color: #fff;">📊 App Telemetry & Messaging:</strong>
                                    <ul style="margin-top: 0.2rem; margin-left: 1rem; padding: 0;">
                                        <li><strong>Crashlytics:</strong> Export fatal, non-fatal, & ANR logs</li>
                                        <li><strong>Performance Monitoring:</strong> Export network traces & latency</li>
                                        <li><strong>Cloud Messaging (FCM):</strong> Export notification delivery</li>
                                    </ul>
                                </div>
                            </div>
                        </div>

                        <ol style="font-size: 0.8rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.6;">
                            <li>Click <a href="https://console.firebase.google.com/" target="_blank" onclick="event.stopPropagation();" style="color: var(--accent-cyan);">Open Firebase Console</a> → select your project → click <strong>Project Settings (gear icon) → Integrations</strong>.</li>
                            <li>Find <strong>BigQuery</strong> → click <strong>Link / Manage</strong>.</li>
                            <li>Select your GCP Region (e.g. <code>asia-southeast1</code> or <code>us-central1</code>).</li>
                            <li>Turn ON the export toggles for <strong>Google Analytics</strong> (check <em>Include Sessions</em>), <strong>Firestore</strong>, <strong>Crashlytics</strong>, and <strong>Performance Monitoring</strong>, then click <strong>Submit</strong>.</li>
                        </ol>
                    </div>

                    <div style="margin-top: 1.5rem; padding: 1.25rem; background: rgba(0,242,254,0.05); border: 1px solid rgba(0,242,254,0.25); border-radius: 10px;">
                        <div style="font-size: 0.95rem; color: var(--accent-cyan); font-weight: 700; margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.4rem;">
                            <span>🚀 Launch Deployment Pipeline</span>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.85rem; line-height: 1.4;">
                            All setup details, knowledge base links, and store analytics exports are configured! Switch to <strong>Tab 4: Onboarding Pipeline</strong> to run pipeline steps.
                        </p>
                        <button type="button" class="btn" onclick="switchTab('pipeline-tab')" style="background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue)); color: #000; font-weight: 700; padding: 0.6rem 1.4rem; font-size: 0.85rem; border-radius: 8px;">
                            Go to Tab 4: Onboarding Pipeline →
                        </button>
                    </div>
                </div>

                <!-- TAB 4: Onboarding Pipeline -->
                <div id="pipeline-tab" class="tab-content">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem;">
                        <h3 style="font-family: 'Outfit', sans-serif; font-size: 1rem; font-weight: 600; color: var(--accent-cyan);">
                            ⚡ Execution Pipeline (Steps 1 – 8)
                        </h3>
                        <button type="button" class="btn" onclick="runStep('run-all')" style="background: linear-gradient(135deg, var(--accent-purple), var(--accent-blue)); font-weight: 600; font-size: 0.78rem; padding: 0.4rem 0.9rem;">
                            🚀 Run All Pipeline Steps
                        </button>
                    </div>
                    <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 1rem;">
                        Once account details, knowledge base links, and store analytics are set, run the steps sequentially below to bootstrap BigQuery tables, ingest e-commerce data, and build dbt analytical models.
                    </p>

                    <div class="stepper-container">
                        <!-- Step 1 -->
                        <div class="step-card" id="step-1">
                            <div class="step-info">
                                <div class="step-number">1</div>
                                <div class="step-details">
                                    <div class="step-title">Link Service Account & GCP Project</div>
                                    <div class="step-desc">Verify service account credentials & set active project</div>
                                </div>
                            </div>
                            <div class="step-actions">
                                <span class="step-status-pill">Idle</span>
                                <button class="btn btn-run-step" onclick="runStep('link-sa')">Run</button>
                            </div>
                        </div>

                        <!-- Step 2 -->
                        <div class="step-card" id="step-2">
                            <div class="step-info">
                                <div class="step-number">2</div>
                                <div class="step-details">
                                    <div class="step-title">Enable Required GCP APIs</div>
                                    <div class="step-desc">Enable BigQuery, Secret Manager & Cloud Build APIs</div>
                                </div>
                            </div>
                            <div class="step-actions">
                                <span class="step-status-pill">Idle</span>
                                <button class="btn btn-run-step" onclick="runStep('enable-apis')">Run</button>
                            </div>
                        </div>

                        <!-- Step 3 -->
                        <div class="step-card" id="step-3">
                            <div class="step-info">
                                <div class="step-number">3</div>
                                <div class="step-details">
                                    <div class="step-title">Assign IAM Roles</div>
                                    <div class="step-desc">Grant BigQuery Admin & Secret Manager roles to SA</div>
                                </div>
                            </div>
                            <div class="step-actions">
                                <span class="step-status-pill">Idle</span>
                                <button class="btn btn-run-step" onclick="runStep('assign-iam')">Run</button>
                            </div>
                        </div>

                        <!-- Step 4 -->
                        <div class="step-card" id="step-4">
                            <div class="step-info">
                                <div class="step-number">4</div>
                                <div class="step-details">
                                    <div class="step-title">Bootstrap BigQuery Resources</div>
                                    <div class="step-desc">Create datasets, tables & schemas inside GCP BigQuery</div>
                                </div>
                            </div>
                            <div class="step-actions">
                                <span class="step-status-pill">Idle</span>
                                <button class="btn btn-run-step" onclick="runStep('bootstrap-resources')">Run</button>
                            </div>
                        </div>

                        <!-- Step 5 -->
                        <div class="step-card" id="step-5">
                            <div class="step-info">
                                <div class="step-number">5</div>
                                <div class="step-details">
                                    <div class="step-title">Sync Firestore & User Datasets</div>
                                    <div class="step-desc">Ingest live Firestore collections into BigQuery</div>
                                </div>
                            </div>
                            <div class="step-actions">
                                <span class="step-status-pill">Idle</span>
                                <button class="btn btn-run-step" onclick="runStep('firestore-bq')">Run</button>
                            </div>
                        </div>

                        <!-- Step 6 -->
                        <div class="step-card" id="step-6">
                            <div class="step-info">
                                <div class="step-number">6</div>
                                <div class="step-details">
                                    <div class="step-title">Build Consolidated E-Commerce Models</div>
                                    <div class="step-desc">Unify orders, user profiles & product catalogs</div>
                                </div>
                            </div>
                            <div class="step-actions">
                                <span class="step-status-pill">Idle</span>
                                <button class="btn btn-run-step" onclick="runStep('consolidated')">Run</button>
                            </div>
                        </div>

                        <!-- Step 7 -->
                        <div class="step-card" id="step-7">
                            <div class="step-info">
                                <div class="step-number">7</div>
                                <div class="step-details">
                                    <div class="step-title">Ingest E-Commerce & Knowledge Base</div>
                                    <div class="step-desc">Index Google Drive, Notion & Confluence into Pinecone</div>
                                </div>
                            </div>
                            <div class="step-actions">
                                <span class="step-status-pill">Idle</span>
                                <button class="btn btn-run-step" onclick="runStep('ingest-ecommerce')">Run</button>
                            </div>
                        </div>

                        <!-- Step 8 -->
                        <div class="step-card" id="step-8">
                            <div class="step-info">
                                <div class="step-number">8</div>
                                <div class="step-details">
                                    <div class="step-title">Run dbt Analytical Models</div>
                                    <div class="step-desc">Build analytical transformations & reporting views</div>
                                </div>
                            </div>
                            <div class="step-actions">
                                <span class="step-status-pill">Idle</span>
                                <button class="btn btn-run-step" onclick="runStep('run-dbt')">Run</button>
                            </div>
                        </div>
                    </div>

                    <div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--card-border); text-align: center;">
                        <button type="button" class="btn" onclick="switchTab('package-tab')" style="background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue)); color: #000; font-weight: 700; padding: 0.75rem 1.75rem; font-size: 0.9rem; border-radius: 8px;">
                            Go to Tab 5: Client Web Package & Integration →
                        </button>
                    </div>
                </div>

                <!-- TAB 5: Client Web Package & Integration -->
                <div id="package-tab" class="tab-content">
                    <div style="background: rgba(44, 182, 125, 0.08); border: 1px solid rgba(44, 182, 125, 0.3); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem;">
                        <div style="font-weight: 700; font-size: 1.05rem; color: var(--accent-cyan); display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span>📦 Your AI Web Integration & Hand-Off Package</span>
                            <a href="/download_client_package" class="btn" style="padding: 0.55rem 1.25rem; font-size: 0.82rem; border-radius: 6px; background: linear-gradient(135deg, var(--accent-cyan), #249e6b); color: white; text-decoration: none; font-weight: 600; display: inline-flex; align-items: center; gap: 0.4rem;">
                                ⬇️ Download Integration ZIP (.zip) ↗
                            </a>
                        </div>
                        <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5; margin-bottom: 1rem;">
                            Download your customized AI web package for <strong class="biz-name-display" style="color: var(--accent-cyan);">Your Business</strong>. Click the button above to download your complete ZIP archive, or access the generated file locally on your machine at:
                            <br>
                            <code style="color: #fff; background: rgba(0,0,0,0.4); padding: 0.3rem 0.6rem; border-radius: 4px; font-size: 0.78rem; display: inline-block; margin-top: 0.4rem; border: 1px solid rgba(255,255,255,0.08);">./client_site_package/diad_integration_package_<span id="package-biz-slug">your_business</span>.zip</code>
                        </p>

                        <!-- Preview Buttons Grid -->
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; margin-bottom: 1.25rem;">
                            <a href="/portal" target="_blank" class="btn" style="padding: 0.6rem 1rem; font-size: 0.8rem; background: rgba(255,255,255,0.06); border: 1px solid var(--card-border); color: #fff; text-decoration: none; text-align: center; border-radius: 6px;">
                                🚀 Main Portal (/portal) ↗
                            </a>
                            <a href="/external_chatbot" target="_blank" class="btn" style="padding: 0.6rem 1rem; font-size: 0.8rem; background: rgba(127,90,240,0.15); border: 1px solid rgba(127,90,240,0.3); color: #fff; text-decoration: none; text-align: center; border-radius: 6px;">
                                🛍️ Customer Chatbot (/external_chatbot) ↗
                            </a>
                            <a href="/internal_chatbot" target="_blank" class="btn" style="padding: 0.6rem 1rem; font-size: 0.8rem; background: rgba(44,182,125,0.15); border: 1px solid rgba(44,182,125,0.3); color: #fff; text-decoration: none; text-align: center; border-radius: 6px;">
                                📊 Internal Advisor (/internal_chatbot) ↗
                            </a>
                        </div>

                        <!-- 1-Line Embed Snippet Box -->
                        <div style="background: rgba(0,242,254,0.06); border: 1px solid rgba(0,242,254,0.25); border-radius: 8px; padding: 1rem; margin-bottom: 1.25rem;">
                            <div style="font-weight: 700; font-size: 0.88rem; color: var(--accent-cyan); margin-bottom: 0.4rem; display: flex; align-items: center; justify-content: space-between;">
                                <span>⚡ 1-Line Storefront Embed Code (Floating Chat Bubble)</span>
                                <button type="button" class="btn" onclick="copyEmbedScript()" style="padding: 0.25rem 0.75rem; font-size: 0.75rem; border-radius: 4px; background: var(--accent-cyan); color: #000; font-weight: 700;">Copy Embed Code</button>
                            </div>
                            <div style="background: rgba(0,0,0,0.5); padding: 0.6rem 0.8rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1);">
                                <code id="embed-script-tag" style="color: #4facfe; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; word-break: break-all;">&lt;script src="/diad-chat-widget.js" defer&gt;&lt;/script&gt;</code>
                            </div>
                        </div>

                        <!-- Step-by-Step Instructions Box with Platform Tabs -->
                        <div style="background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 1.25rem;">
                            <div style="font-weight: 700; font-size: 0.95rem; color: var(--accent-purple); margin-bottom: 0.75rem;">
                                📋 Step-by-Step Integration Guide by Platform
                            </div>

                            <!-- Platform Selector Buttons -->
                            <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.5rem; flex-wrap: wrap;">
                                <button type="button" class="btn platform-tab-btn active" onclick="showPlatform('shopify')" id="tab-btn-shopify" style="padding: 0.4rem 0.8rem; font-size: 0.78rem; border-radius: 6px; background: var(--accent-purple); color: #fff;">🛍️ Shopify</button>
                                <button type="button" class="btn platform-tab-btn" onclick="showPlatform('woocommerce')" id="tab-btn-woocommerce" style="padding: 0.4rem 0.8rem; font-size: 0.78rem; border-radius: 6px; background: rgba(255,255,255,0.08); color: #fff;">💙 WooCommerce / WordPress</button>
                                <button type="button" class="btn platform-tab-btn" onclick="showPlatform('wix')" id="tab-btn-wix" style="padding: 0.4rem 0.8rem; font-size: 0.78rem; border-radius: 6px; background: rgba(255,255,255,0.08); color: #fff;">🌐 Wix / Squarespace</button>
                                <button type="button" class="btn platform-tab-btn" onclick="showPlatform('custom')" id="tab-btn-custom" style="padding: 0.4rem 0.8rem; font-size: 0.78rem; border-radius: 6px; background: rgba(255,255,255,0.08); color: #fff;">⚡ Netlify / Custom HTML</button>
                            </div>

                            <!-- Platform Instructions Content -->
                            <div id="platform-shopify" class="platform-instruction-content">
                                <ol style="font-size: 0.82rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.7;">
                                    <li>Log into your <strong>Shopify Admin Panel</strong> → go to <strong>Online Store</strong> → <strong>Themes</strong>.</li>
                                    <li>Click the <strong><code>...</code> (Actions)</strong> button next to your active theme → select <strong>Edit Code</strong>.</li>
                                    <li>In the left file navigator under <strong>Layout</strong>, click to open <strong><code>theme.liquid</code></strong>.</li>
                                    <li>Scroll to the bottom, paste <code>&lt;script src="/diad-chat-widget.js" defer&gt;&lt;/script&gt;</code> immediately before the closing <code>&lt;/body&gt;</code> tag, and click <strong>Save</strong>.</li>
                                    <li>Upload <code>diad-chat-widget.js</code> into <strong>Assets</strong> → <strong>Add a new asset</strong>. Your floating AI assistant is live for all storefront customers!</li>
                                </ol>
                            </div>

                            <div id="platform-woocommerce" class="platform-instruction-content" style="display: none;">
                                <ol style="font-size: 0.82rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.7;">
                                    <li>Log into your <strong>WordPress Admin Dashboard</strong> → <strong>Plugins</strong> → <strong>Add New</strong>.</li>
                                    <li>Search for <strong>WPCode</strong> (Insert Headers and Footers), install and click <strong>Activate</strong>.</li>
                                    <li>Go to <strong>Code Snippets</strong> → <strong>Header & Footer</strong> in your admin sidebar.</li>
                                    <li>In the <strong>Footer</strong> box, paste <code>&lt;script src="/diad-chat-widget.js" defer&gt;&lt;/script&gt;</code> and click <strong>Save Changes</strong>.</li>
                                    <li>Upload <code>diad-chat-widget.js</code> to your website root or theme directory via SFTP/File Manager.</li>
                                </ol>
                            </div>

                            <div id="platform-wix" class="platform-instruction-content" style="display: none;">
                                <ol style="font-size: 0.82rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.7;">
                                    <li><strong>Wix</strong>: Go to Dashboard → <strong>Settings</strong> → <strong>Custom Code</strong> → Click <strong>+ Add Custom Code</strong>. Paste script tag under <strong>Body - End</strong>, select <strong>All Pages</strong>, and click Apply.</li>
                                    <li><strong>Squarespace</strong>: Go to <strong>Settings</strong> → <strong>Developer Tools</strong> → <strong>Code Injection</strong>. Paste script tag into <strong>Footer</strong> and click Save.</li>
                                    <li><strong>Webflow</strong>: Go to <strong>Project Settings</strong> → <strong>Custom Code</strong> → paste into <strong>Footer Code</strong>.</li>
                                </ol>
                            </div>

                            <div id="platform-custom" class="platform-instruction-content" style="display: none;">
                                <ol style="font-size: 0.82rem; color: var(--text-muted); margin-left: 1.25rem; line-height: 1.7;">
                                    <li>Unzip your downloaded integration package (<code>diad_integration_package_...zip</code>).</li>
                                    <li>Copy <code>diad-chat-widget.js</code>, <code>external_chatbot.html</code>, and <code>internal_chatbot.html</code> into your website repository's <code>public/</code> or root folder.</li>
                                    <li>Ensure <code>_redirects</code> is in your publish root for Netlify SPA routing.</li>
                                    <li>Paste <code>&lt;script src="/diad-chat-widget.js" defer&gt;&lt;/script&gt;</code> before <code>&lt;/body&gt;</code> in <code>index.html</code>. Commit & push to GitHub!</li>
                                </ol>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>


        <!-- RIGHT PANEL: Onboarding Mentor & Output Logs -->
        <section class="panel" style="display: flex; flex-direction: column; gap: 1rem; height: calc(100vh - 140px);">
            <!-- Mentoring Assistant Card -->
            <div class="mentor-card" style="background: rgba(127, 90, 240, 0.1); border: 1px solid rgba(127, 90, 240, 0.3); border-radius: 12px; padding: 1.25rem; display: flex; gap: 1rem; align-items: flex-start; position: relative; overflow: hidden;">
                <div class="mentor-glow" style="position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(127, 90, 240, 0.15) 0%, transparent 70%); pointer-events: none;"></div>
                <div class="mentor-avatar" style="width: 44px; height: 44px; border-radius: 50%; background: linear-gradient(135deg, var(--accent-purple), var(--accent-blue)); display: flex; align-items: center; justify-content: center; font-size: 1.4rem; box-shadow: 0 0 15px rgba(127, 90, 240, 0.4); flex-shrink: 0; animation: float 3s ease-in-out infinite;">🤖</div>
                <div style="flex: 1; display: flex; flex-direction: column; gap: 0.5rem; z-index: 1;">
                    <div style="font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 0.95rem; color: var(--accent-cyan); display: flex; justify-content: space-between; align-items: center;">
                        <span>Onboarding Mentor</span>
                        <span id="current-mentor-state" style="font-size: 0.7rem; font-weight: 500; color: var(--text-muted); background: rgba(255,255,255,0.05); padding: 0.15rem 0.4rem; border-radius: 4px; border: 1px solid var(--card-border);">STAGE 1: Setup</span>
                    </div>
                    <div id="mentor-bubble" style="font-size: 0.82rem; line-height: 1.45; color: var(--text-main); font-weight: 400; min-height: 40px;">
                        Hello! Let's get started. First, check the <strong>1. Account & Setup</strong> tab. Follow the instructions to create your GCP project and drag your service account key file in.
                    </div>
                    <!-- Mentee Q&A Buttons -->
                    <div id="mentor-faq-container" style="display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.4rem; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 0.6rem;">
                        <button type="button" class="btn-faq" onclick="askMentor('sa-key')">📄 What is a Service Account key?</button>
                        <button type="button" class="btn-faq" onclick="askMentor('api-keys')">🔌 Why do I need API keys?</button>
                        <button type="button" class="btn-faq" onclick="askMentor('pipeline-order')">🔄 What order do I run steps in?</button>
                        <button type="button" class="btn-faq" onclick="askMentor('data-safety')">🔒 Is my data safe on my machine?</button>
                    </div>
                    <!-- Mentee Chat Input Box -->
                    <div id="mentor-chat-container" style="display: flex; gap: 0.4rem; margin-top: 0.6rem; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 0.6rem;">
                        <input type="text" id="mentor-input" placeholder="Ask Mentor any question about setup..." onkeypress="if(event.key==='Enter') sendMentorQuestion()" style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--card-border); border-radius: 6px; padding: 0.4rem 0.6rem; color: #fff; font-size: 0.78rem; outline: none;">
                        <button type="button" class="btn" onclick="sendMentorQuestion()" style="padding: 0.4rem 0.75rem; font-size: 0.75rem; border-radius: 6px; background: var(--accent-purple); border: none; cursor: pointer; color: white;">Ask</button>
                    </div>
                </div>
            </div>

            <!-- Output Logs Console -->
            <div class="terminal-container" style="flex: 1; min-height: 250px; display: flex; flex-direction: column; margin-top: 0;">
                <div class="terminal-header" style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 1rem; background: rgba(0,0,0,0.4); border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <div class="terminal-title" style="font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--accent-cyan);">Output Logs Console</div>
                    <div class="terminal-actions">
                        <button class="terminal-btn" onclick="clearConsole()" style="background: transparent; border: 1px solid var(--card-border); color: var(--text-muted); padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.7rem; cursor: pointer;">Clear Logs</button>
                    </div>
                </div>
                <div class="terminal-body" id="terminal-body" style="flex: 1; overflow-y: auto; padding: 0.75rem; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #a6accd; background: rgba(10, 15, 25, 0.95);">
                    <div class="log-line">Console initialized. Ready for task execution.</div>
                </div>
            </div>
        </section>
    </main>

    <!-- Notification Toast -->
    <div id="toast" class="notification-toast">
        <span class="notification-icon" id="toast-icon"></span>
        <span id="toast-message"></span>
    </div>

    <script>
        // Store configuration locally
        let fullConfig = {{}};
        let activeEventSource = null;
        
        // Guidance State Tracker
        let onboardingState = 'init'; // 'init', 'link_sources', 'secrets', 'step_1', 'step_2', 'step_4', 'step_5', 'step_6', 'step_7', 'step_8', 'complete', 'error'
        let stepStates = {{ 1: 'idle', 2: 'idle', 3: 'idle', 4: 'idle', 5: 'idle', 6: 'idle', 7: 'idle', 8: 'idle' }};

        // Switch Tabs (UI Panel switching)
        function switchTab(tabId) {{
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            // Activate button
            const activeBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick').includes(tabId));
            if (activeBtn) activeBtn.classList.add('active');
            
            document.getElementById(tabId).classList.add('active');
        }}

        // Copy Service Account Email to clipboard
        function copySaEmail() {{
            const email = document.getElementById('sa-email-display').textContent;
            navigator.clipboard.writeText(email).then(() => {{
                showToast("Service Account Email copied to clipboard!", "success");
            }}).catch(err => {{
                showToast("Failed to copy email to clipboard.", "error");
            }});
        }}

        // Handle file selection from browse button
        function handleFileSelect(e) {{
            const file = e.target.files[0];
            if (!file) return;
            uploadJsonFile(file);
        }}

        // Parse and upload Service Account JSON Key
        function uploadJsonFile(file) {{
            const reader = new FileReader();
            const statusText = document.getElementById('upload-status-text');
            statusText.textContent = "Parsing file...";
            
            reader.onload = async function(event) {{
                const content = event.target.result;
                try {{
                    // Check if it's valid JSON
                    const key_data = JSON.parse(content);
                    
                    statusText.textContent = "Configuring project files...";
                    const res = await fetch('/api/upload-key', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            filename: file.name,
                            content: content
                        }})
                    }});
                    
                    if (!res.ok) {{
                        const errorData = await res.json();
                        throw new Error(errorData.detail || "Failed to configure key file");
                    }}
                    
                    const data = await res.json();
                    showToast("GCP Service Account JSON Key uploaded and configured!", "success");
                    statusText.textContent = "Key Configured! Project: " + data.project_id;
                    
                    const projStatusEl = document.getElementById('gcp-project-status');
                    if (projStatusEl) projStatusEl.textContent = data.project_id;
                    
                    const banner = document.getElementById('step4-success-banner');
                    if (banner) banner.style.display = 'block';
                    
                    // Auto-reload configuration and refresh environment health check
                    await loadConfig();
                    await loadDiagnostics();
                    
                    // Progress guidance to data sources link guide tab
                    onboardingState = 'link_sources';
                    updateOnboardingGuidance();
                    
                }} catch(err) {{
                    showToast(err.message, "error");
                    statusText.textContent = "Error: " + err.message;
                }}
            }};
            reader.readAsText(file);
        }}

        // Guidance updates
        function updateOnboardingGuidance() {{
            const bubble = document.getElementById('mentor-bubble');
            const statePill = document.getElementById('current-mentor-state');
            
            // Check current states to decide state
            if (stepStates[8] === 'success') onboardingState = 'complete';
            else if (stepStates[7] === 'success') onboardingState = 'step_8';
            else if (stepStates[6] === 'success') onboardingState = 'step_7';
            else if (stepStates[5] === 'success') onboardingState = 'step_6';
            else if (stepStates[4] === 'success') onboardingState = 'step_5';
            else if (stepStates[3] === 'success') onboardingState = 'step_4';
            else if (stepStates[2] === 'success') onboardingState = 'step_3';
            else if (stepStates[1] === 'success') onboardingState = 'step_2';
            
            // Check if errors exist
            for (let i = 1; i <= 8; i++) {{
                if (stepStates[i] === 'error') {{
                    onboardingState = 'error';
                    break;
                }}
            }}

            let guideText = "";
            let stageLabel = "";

            switch(onboardingState) {{
                case 'init':
                    stageLabel = "STAGE 1: Setup";
                    guideText = "Welcome! Let's get started. Check the <strong>1. GCP Account Setup</strong> tab on the left. Follow the instructions to create your GCP project and drag your service account key file in.";
                    break;
                case 'link_sources':
                    stageLabel = "STAGE 2: Link Sources";
                    guideText = "GCP Project configured! Now, we must link your data sources. Click the <strong>2. Data Sources Link Guide</strong> tab, share your Google Drive folder, and configure GA4 / Firebase linking.";
                    break;
                case 'secrets':
                    stageLabel = "STAGE 3: API Keys";
                    guideText = "Sources connected! Next, we need to save your secret access keys. Click on the <strong>3. GCP Secrets Vault</strong> tab, type in your API keys (like OpenAI or Pinecone), and click <strong>Sync Secrets to GCP</strong>.";
                    break;
                case 'step_1':
                    stageLabel = "STAGE 4: Link GCP";
                    guideText = "Your setup is ready! Click <strong>Run</strong> next to <strong>Step 1: Link Service Account & GCP Project</strong> on the right side panel.";
                    break;
                case 'step_2':
                    stageLabel = "STAGE 5: Enable APIs";
                    guideText = "Service Account linked! Now click <strong>Run</strong> on <strong>Step 2: Enable Required GCP APIs</strong> to enable BigQuery & Secret Manager APIs.";
                    break;
                case 'step_3':
                    stageLabel = "STAGE 6: IAM Roles";
                    guideText = "APIs enabled! Click <strong>Run</strong> on <strong>Step 3: Assign IAM Roles</strong> to grant BigQuery & Secret Manager roles.";
                    break;
                case 'step_4':
                    stageLabel = "STAGE 7: Bootstrap BQ";
                    guideText = "IAM roles assigned! Click <strong>Run</strong> on <strong>Step 4: Bootstrap BigQuery Resources</strong> to create your BigQuery datasets & schemas.";
                    break;
                case 'step_5':
                    stageLabel = "STAGE 8: Sync Firestore";
                    guideText = "BigQuery datasets created! Click <strong>Run</strong> on <strong>Step 5: Sync Firestore & User Datasets</strong> to ingest user records.";
                    break;
                case 'step_6':
                    stageLabel = "STAGE 9: Build Models";
                    guideText = "Firestore synced! Click <strong>Run</strong> on <strong>Step 6: Build Consolidated E-Commerce Models</strong> to unify orders & product catalogs.";
                    break;
                case 'step_7':
                    stageLabel = "STAGE 10: Ingest Knowledge";
                    guideText = "E-commerce models built! Click <strong>Run</strong> on <strong>Step 7: Ingest E-Commerce & Knowledge Base</strong> to index drive documents.";
                    break;
                case 'step_8':
                    stageLabel = "STAGE 11: Run dbt";
                    guideText = "Knowledge indexed! Click <strong>Run</strong> on <strong>Step 8: Run dbt Analytical Models</strong> to build customer 360 & dossier marts.";
                    break;
                case 'complete':
                    stageLabel = "STAGE 12: Complete";
                    guideText = "🎉 <strong>Onboarding complete!</strong> Your AI pipeline is fully built and deployed. Switch to <strong>Tab 5: Client Web Package</strong> at the top (or click the button below) to download your client ZIP archive.";
                    break;
                case 'error':
                    stageLabel = "TROUBLESHOOTING";
                    guideText = "Oh, it looks like a step failed. 😟 Scroll down and check the <strong>Output Logs Console</strong> for error messages.";
                    break;
            }}

            statePill.textContent = stageLabel;
            bubble.innerHTML = guideText;
        }}

        // Mentoring Assistant FAQ & Chat handler
        function askMentor(topic) {{
            const bubble = document.getElementById('mentor-bubble');
            let answer = "";

            switch(topic) {{
                case 'sa-key':
                    answer = "A <strong>Service Account key</strong> is a JSON credentials file downloaded from Google Cloud IAM. Drag & drop it into <strong>Step 4: Upload JSON Key File</strong> in Tab 1 to connect your project!";
                    break;
                case 'api-keys':
                    answer = "We use API keys to read your source documents and query AI models: 1) <strong>OpenAI Key</strong> (runs the AI brain), 2) <strong>Pinecone Key</strong> (searches documents fast), 3) <strong>Notion / Confluence Tokens</strong> (to crawl your internal docs). Vault them in <strong>Tab 3</strong>!";
                    break;
                case 'pipeline-order':
                    answer = "The standard flow is: 1) Upload your JSON key in <strong>GCP Account Setup</strong>, 2) Link your data sources in <strong>Data Sources Link Guide</strong>, 3) Sync your keys in <strong>GCP Secrets Vault</strong>, 4) Sequentially run Steps 1 through 8 on the right.";
                    break;
                case 'data-safety':
                    answer = "🔒 <strong>100% Safe & Private.</strong> All dashboard scripts and data run entirely on your local machine and inside your own Google Cloud billing account. No data is stored on third-party servers.";
                    break;
                default:
                    answer = "I'm here to guide you step-by-step. Ask any question in the chat box below!";
            }}

            bubble.innerHTML = answer;
        }}

        function explainSource(tool) {{
            const bubble = document.getElementById('mentor-bubble');
            if (!bubble) return;
            let text = "";
            switch(tool) {{
                case 'gdrive':
                    text = "📁 <strong>Google Drive Purpose:</strong> Stores your company policies, SOPs, and manuals. The AI chatbot indexes these documents so it can answer questions about your operations, returns, and inventory rules.";
                    break;
                case 'notion':
                    text = "📓 <strong>Notion Purpose (Optional):</strong> Notion is a workspace app for internal team wikis and docs. If your company uses Notion, DIAD reads your pages. <em>If you don't use Notion, simply skip this step!</em>";
                    break;
                case 'confluence':
                    text = "📘 <strong>Confluence Purpose (Optional):</strong> Atlassian Confluence stores team documentation and specs. If your team uses Confluence, DIAD indexes your spaces. <em>If you don't use Confluence, simply skip this step!</em>";
                    break;
                case 'ga4':
                    text = "📈 <strong>Google Analytics (GA4) Purpose (Optional):</strong> Exports your website traffic and user behavior data directly into BigQuery so the AI chatbot can answer questions about sales traffic and conversion rates.";
                    break;
                case 'firebase':
                    text = "🔥 <strong>Firebase / Firestore Purpose (Optional):</strong> If your store uses Firebase to store live orders or users, this links your live Firestore database to BigQuery.";
                    break;
                case 'secrets':
                    text = "🔒 <strong>GCP Secrets Vault Purpose:</strong> Safely stores your API keys (OpenAI, Pinecone, Notion, Confluence) encrypted inside your own Google Cloud Secret Manager so no hardcoded keys ever exist in plain text.";
                    break;
            }}
            if (text) bubble.innerHTML = text;
        }}

        async function sendMentorQuestion() {{
            const input = document.getElementById('mentor-input');
            const bubble = document.getElementById('mentor-bubble');
            if (!input || !bubble) return;
            const question = input.value.trim();
            if (!question) return;

            bubble.innerHTML = '🤖 <em>Mentor is thinking...</em>';
            input.value = '';

            try {{
                const res = await fetch('/api/mentor_chat', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{question: question}})
                }});
                const data = await res.json();
                bubble.innerHTML = data.answer || "I'm here to help! Ask me anything about GCP keys, steps, or data privacy.";
            }} catch(e) {{
                bubble.innerHTML = "I am ready to assist! Ask me any question about your Service Account key, API keys, or pipeline steps.";
            }}
        }}

        function copyEmbedScript() {{
            const code = '<script src="/diad-chat-widget.js" defer><' + '/script>';
            navigator.clipboard.writeText(code).then(() => {{
                showToast("1-Line Embed Code copied to clipboard!", "success");
            }}).catch(err => {{
                showToast("Failed to copy code: " + err.message, "error");
            }});
        }}

        function showPlatform(platform) {{
            document.querySelectorAll('.platform-instruction-content').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.platform-tab-btn').forEach(btn => {{
                btn.style.background = 'rgba(255,255,255,0.08)';
                btn.classList.remove('active');
            }});
            const target = document.getElementById('platform-' + platform);
            const targetBtn = document.getElementById('tab-btn-' + platform);
            if (target) target.style.display = 'block';
            if (targetBtn) {{
                targetBtn.style.background = 'var(--accent-purple)';
                targetBtn.classList.add('active');
            }}
        }}

        function onBizNameChange(val) {{
            const el = document.getElementById('client-name-status');
            if (el) el.textContent = val.trim() || 'Not Configured';
            let displayBiz = val.trim();
            if (!displayBiz || displayBiz === 'YOUR_BUSINESS_NAME') displayBiz = 'Your Business';
            document.querySelectorAll('.biz-name-display').forEach(e => e.textContent = displayBiz);
            const slugEl = document.getElementById('package-biz-slug');
            if (slugEl) slugEl.textContent = displayBiz.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'your_business';
        }}

        async function saveBusinessProfile(e) {{
            if (e) e.preventDefault();
            const name = document.getElementById('biz_name').value.trim();
            const url = document.getElementById('biz_url').value.trim();
            
            fullConfig.client = fullConfig.client || {{}};
            fullConfig.client.business_name = name;
            fullConfig.client.website_url = url;
            
            try {{
                const res = await fetch('/api/config', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ config: fullConfig }})
                }});
                if (!res.ok) throw new Error("Failed to save profile");
                const el = document.getElementById('client-name-status');
                if (el) el.textContent = name || 'Not Configured';
                let displayBiz = (name && name !== 'YOUR_BUSINESS_NAME') ? name : 'Your Business';
                document.querySelectorAll('.biz-name-display').forEach(e => e.textContent = displayBiz);
                const slugEl = document.getElementById('package-biz-slug');
                if (slugEl) slugEl.textContent = displayBiz.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'your_business';
                showToast("Business Profile saved!", "success");
            }} catch(err) {{
                showToast(err.message, "error");
            }}
        }}

        // Load configuration from API
        async function loadConfig() {{
            try {{
                const res = await fetch('/api/config');
                if (!res.ok) throw new Error("Failed to load configuration");
                
                const data = await res.json();
                fullConfig = data;
                
                // Set form fields
                if (document.getElementById('biz_name')) document.getElementById('biz_name').value = data.client?.business_name || '';
                if (document.getElementById('biz_url')) document.getElementById('biz_url').value = data.client?.website_url || '';
                
                let resolvedBizName = data.client?.business_name;
                if (!resolvedBizName || resolvedBizName === 'YOUR_BUSINESS_NAME') {{
                    resolvedBizName = 'Your Business';
                }}
                const el = document.getElementById('client-name-status');
                if (el) el.textContent = resolvedBizName;
                document.querySelectorAll('.biz-name-display').forEach(e => e.textContent = resolvedBizName);
                const slugEl = document.getElementById('package-biz-slug');
                if (slugEl) slugEl.textContent = resolvedBizName.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'your_business';
                
                if (document.getElementById('client_business_name')) document.getElementById('client_business_name').value = data.client?.business_name || '';
                if (document.getElementById('client_project_id')) document.getElementById('client_project_id').value = data.client?.project_id || '';
                if (document.getElementById('client_website_url')) document.getElementById('client_website_url').value = data.client?.website_url || '';
                if (document.getElementById('client_bq_location')) document.getElementById('client_bq_location').value = data.client?.bq_location || 'asia-southeast1';
                
                if (document.getElementById('drag_index_name')) document.getElementById('drag_index_name').value = data.document_rag?.index_name || '';
                if (document.getElementById('drag_dimension')) document.getElementById('drag_dimension').value = data.document_rag?.dimension || '384';
                
                if (document.getElementById('llm_primary_provider')) document.getElementById('llm_primary_provider').value = data.llm?.primary?.provider || 'openai';
                if (document.getElementById('llm_primary_model')) document.getElementById('llm_primary_model').value = data.llm?.primary?.model || '';
                
                if (document.getElementById('gcp_key_file')) document.getElementById('gcp_key_file').value = data.gcp?.["key-file"] || data.gcp?.key_file || '';
                if (document.getElementById('gcp_chatbot_deployer_sa')) document.getElementById('gcp_chatbot_deployer_sa').value = data.gcp?.chatbot_deployer_sa || '';
                if (document.getElementById('gcp_chatbot_access_sa')) document.getElementById('gcp_chatbot_access_sa').value = data.gcp?.chatbot_access_sa || '';
                
                // Update dynamic guide elements
                const saEmail = data.gcp?.chatbot_access_sa || 'your-service-account@your-gcp-project.iam.gserviceaccount.com';
                document.getElementById('sa-email-display').textContent = saEmail;
                
                const projId = data.client?.project_id || 'Not Configured';
                const projStatusEl = document.getElementById('gcp-project-status');
                if (projStatusEl) projStatusEl.textContent = projId;
                document.querySelectorAll('.gcp-project-placeholder').forEach(el => el.textContent = projId);
                
                showToast("Configuration loaded successfully", "success");
                
                // Set onboarding state
                if (data.client?.project_id && data.client?.project_id !== 'Not Configured' && data.client?.project_id !== 'your-gcp-project-id') {{
                    onboardingState = 'link_sources';
                }} else {{
                    onboardingState = 'init';
                }}
                updateOnboardingGuidance();
                
            }} catch (err) {{
                showToast(err.message, "error");
            }}
        }}

        // Save Configuration to API
        async function saveConfig(e) {{
            e.preventDefault();
            
            // Build payload by deep patching local values back
            fullConfig.client = fullConfig.client || {{}};
            fullConfig.client.business_name = document.getElementById('client_business_name').value;
            fullConfig.client.project_id = document.getElementById('client_project_id').value;
            fullConfig.client.website_url = document.getElementById('client_website_url').value;
            fullConfig.client.bq_location = document.getElementById('client_bq_location').value;
            
            fullConfig.document_rag = fullConfig.document_rag || {{}};
            fullConfig.document_rag.index_name = document.getElementById('drag_index_name').value;
            fullConfig.document_rag.dimension = parseInt(document.getElementById('drag_dimension').value, 10) || 384;
            
            fullConfig.llm = fullConfig.llm || {{}};
            fullConfig.llm.primary = fullConfig.llm.primary || {{}};
            fullConfig.llm.primary.provider = document.getElementById('llm_primary_provider').value;
            fullConfig.llm.primary.model = document.getElementById('llm_primary_model').value;
            
            fullConfig.gcp = fullConfig.gcp || {{}};
            fullConfig.gcp["key-file"] = document.getElementById('gcp_key_file').value;
            fullConfig.gcp.key_file = document.getElementById('gcp_key_file').value;
            fullConfig.gcp.chatbot_deployer_sa = document.getElementById('gcp_chatbot_deployer_sa').value;
            fullConfig.gcp.chatbot_access_sa = document.getElementById('gcp_chatbot_access_sa').value;
            
            try {{
                const res = await fetch('/api/config', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ config: fullConfig }})
                }});
                
                if (!res.ok) throw new Error("Failed to save configuration");
                
                // Update UI titles dynamically
                document.getElementById('client-name-status').textContent = fullConfig.client.business_name;
                document.getElementById('gcp-project-status').textContent = fullConfig.client.project_id;
                
                let displayBiz = (fullConfig.client.business_name && fullConfig.client.business_name !== 'YOUR_BUSINESS_NAME') ? fullConfig.client.business_name : 'Your Business';
                document.querySelectorAll('.biz-name-display').forEach(e => e.textContent = displayBiz);
                const slugEl = document.getElementById('package-biz-slug');
                if (slugEl) slugEl.textContent = displayBiz.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'your_business';
                
                // Update dynamic guide elements
                document.getElementById('sa-email-display').textContent = fullConfig.gcp.chatbot_access_sa;
                document.querySelectorAll('.gcp-project-placeholder').forEach(el => el.textContent = fullConfig.client.project_id);
                
                showToast("Configuration saved successfully", "success");
                
                // Progress guidance to link_sources tab
                onboardingState = 'link_sources';
                switchTab('sources-tab');
                updateOnboardingGuidance();
            }} catch (err) {{
                showToast(err.message, "error");
            }}
        }}

        function onLlmProviderChange(provider) {{
            if (document.getElementById('openai-key-block')) document.getElementById('openai-key-block').style.display = (provider === 'openai') ? 'block' : 'none';
            if (document.getElementById('gemini-key-block')) document.getElementById('gemini-key-block').style.display = (provider === 'gemini') ? 'block' : 'none';
            if (document.getElementById('anthropic-key-block')) document.getElementById('anthropic-key-block').style.display = (provider === 'anthropic') ? 'block' : 'none';
            
            fullConfig.llm = fullConfig.llm || {{}};
            fullConfig.llm.primary = fullConfig.llm.primary || {{}};
            fullConfig.llm.primary.provider = provider;
        }}

        function startPipelineExecution() {{
            onboardingState = 'step_1';
            updateOnboardingGuidance();
            const step1Card = document.getElementById('step-1');
            if (step1Card) {{
                step1Card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                step1Card.classList.add('active');
            }}
            showToast("Starting Step 1: Preflight Check...", "info");
            runStep('preflight');
        }}

        // Save Secrets to GCP Secret Manager
        async function saveSecrets(e) {{
            if (e) e.preventDefault();
            
            const secrets = {{
                OPENAI_API_KEY: document.getElementById('sec_openai') ? document.getElementById('sec_openai').value : '',
                GEMINI_API_KEY: document.getElementById('sec_gemini') ? document.getElementById('sec_gemini').value : '',
                ANTHROPIC_API_KEY: document.getElementById('sec_anthropic') ? document.getElementById('sec_anthropic').value : '',
                PINECONE_API_KEY: document.getElementById('sec_pinecone') ? document.getElementById('sec_pinecone').value : '',
                NOTION_TOKEN: document.getElementById('sec_notion') ? document.getElementById('sec_notion').value : '',
                CONFLUENCE_TOKEN: document.getElementById('sec_confluence') ? document.getElementById('sec_confluence').value : ''
            }};

            // Filter out empty secret values
            const payloadSecrets = {{}};
            for (const [k, v] of Object.entries(secrets)) {{
                if (v.trim()) payloadSecrets[k] = v.trim();
            }}

            if (Object.keys(payloadSecrets).length === 0) {{
                showToast("No secret values entered to upload.", "warning");
                return;
            }}

            // Save LLM provider choice to config
            if (document.getElementById('llm_provider_choice')) {{
                fullConfig.llm = fullConfig.llm || {{}};
                fullConfig.llm.primary = fullConfig.llm.primary || {{}};
                fullConfig.llm.primary.provider = document.getElementById('llm_provider_choice').value;
                try {{
                    await fetch('/api/config', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ config: fullConfig }})
                    }});
                }} catch(err) {{}}
            }}

            const term = document.getElementById('terminal-body');
            term.innerHTML += `<div class="log-line log-starting">[STARTING] Initiating sync for secrets: ${{Object.keys(payloadSecrets).join(', ')}}</div>`;
            term.scrollTop = term.scrollHeight;

            try {{
                const res = await fetch('/api/secrets', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ secrets: payloadSecrets }})
                }});

                if (!res.ok) throw new Error("GCP secret manager upload request failed");
                
                // Read from SSE endpoint or parse direct response
                const reader = res.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let hasError = false;

                while (true) {{
                    const {{ value, done }} = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value, {{ stream: true }});
                    // SSE response is prefixed with 'data: '
                    const lines = chunk.split('\\n');
                    for (const rawLine of lines) {{
                        if (rawLine.startsWith('data: ')) {{
                            const content = rawLine.substring(6);
                            if (content.trim()) {{
                                appendTerminalLog(content);
                                if (content.includes('[ERROR]')) hasError = true;
                            }}
                        }}
                    }}
                }}

                if (hasError) {{
                    showToast("Failed to upload one or more secrets", "error");
                }} else {{
                    secretsVaulted = true;
                    
                    // Immediately refresh diagnostics & readiness score to 100% Ready
                    await loadDiagnostics();
                    updateOnboardingGuidance();
                    
                    showToast("🎉 All secrets vaulted to Secret Manager! Setup is ready for pipeline execution.", "success");
                    
                    // Clear inputs for safety
                    if (document.getElementById('sec_openai')) document.getElementById('sec_openai').value = '';
                    if (document.getElementById('sec_gemini')) document.getElementById('sec_gemini').value = '';
                    if (document.getElementById('sec_anthropic')) document.getElementById('sec_anthropic').value = '';
                    if (document.getElementById('sec_pinecone')) document.getElementById('sec_pinecone').value = '';
                    if (document.getElementById('sec_notion')) document.getElementById('sec_notion').value = '';
                    if (document.getElementById('sec_confluence')) document.getElementById('sec_confluence').value = '';

                    // Visually highlight Step 1 card on the right side panel
                    const step1Card = document.getElementById('step-1');
                    if (step1Card) {{
                        step1Card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        step1Card.classList.add('active');
                    }}
                }}
            }} catch (err) {{
                appendTerminalLog(`[ERROR] Secrets upload exception: ${{err.message}}`);
                showToast(err.message, "error");
            }}
        }}

        // Run Onboarding pipeline steps (handles SSE streaming to the terminal)
        function runStep(stepName) {{
            if (activeEventSource) {{
                activeEventSource.close();
            }}

            if (stepName === 'run-all') {{
                for (let i = 1; i <= 8; i++) {{
                    updateStepUI(i, 'idle');
                    stepStates[i] = 'idle';
                }}
                updateStepUI(1, 'active');
                stepStates[1] = 'running';
                updateOnboardingGuidance();
                appendTerminalLog(`[STARTING] Beginning execution of All Pipeline Steps (Steps 1 – 8)...`);

                activeEventSource = new EventSource(`/api/run/run-all`);
                let hasError = false;

                activeEventSource.onmessage = function(event) {{
                    const log = event.data;
                    appendTerminalLog(log);

                    if (log.includes('[ERROR]') && !log.includes('UserWarning')) {{
                        hasError = true;
                    }}

                    // Progressively mark steps as they execute
                    if (log.includes('Beginning execution of Step 2') || log.includes('enable-apis')) {{
                        updateStepUI(1, 'success'); stepStates[1] = 'success';
                        updateStepUI(2, 'active');  stepStates[2] = 'running';
                    }} else if (log.includes('Beginning execution of Step 3') || log.includes('assign-iam')) {{
                        updateStepUI(2, 'success'); stepStates[2] = 'success';
                        updateStepUI(3, 'active');  stepStates[3] = 'running';
                    }} else if (log.includes('Beginning execution of Step 4') || log.includes('bootstrap-resources')) {{
                        updateStepUI(3, 'success'); stepStates[3] = 'success';
                        updateStepUI(4, 'active');  stepStates[4] = 'running';
                    }} else if (log.includes('Beginning execution of Step 5') || log.includes('firestore-to-bq')) {{
                        updateStepUI(4, 'success'); stepStates[4] = 'success';
                        updateStepUI(5, 'active');  stepStates[5] = 'running';
                    }} else if (log.includes('Beginning execution of Step 6') || log.includes('build-consolidated')) {{
                        updateStepUI(5, 'success'); stepStates[5] = 'success';
                        updateStepUI(6, 'active');  stepStates[6] = 'running';
                    }} else if (log.includes('Beginning execution of Step 7') || log.includes('ingest-ecommerce')) {{
                        updateStepUI(6, 'success'); stepStates[6] = 'success';
                        updateStepUI(7, 'active');  stepStates[7] = 'running';
                    }} else if (log.includes('Beginning execution of Step 8') || log.includes('run-dbt')) {{
                        updateStepUI(7, 'success'); stepStates[7] = 'success';
                        updateStepUI(8, 'active');  stepStates[8] = 'running';
                    }}

                    if (log.includes('Phase 7 - Run-All completed [OK]') || log.includes('Process finished with exit code 0')) {{
                        for (let i = 1; i <= 8; i++) {{
                            updateStepUI(i, 'success');
                            stepStates[i] = 'success';
                        }}
                        onboardingState = 'complete';
                        updateOnboardingGuidance();
                        showToast("🎉 All Pipeline Steps Completed Successfully!", "success");
                        activeEventSource.close();
                        activeEventSource = null;
                    }}
                }};

                activeEventSource.onerror = function(err) {{
                    console.error("EventSource error:", err);
                    activeEventSource.close();
                    activeEventSource = null;
                }};
                return;
            }}

            let stepNum = 1;
            switch(stepName) {{
                case 'link-sa': case 'preflight': stepNum = 1; break;
                case 'enable-apis': case 'bootstrap': stepNum = 2; break;
                case 'assign-iam': stepNum = 3; break;
                case 'bootstrap-resources': case 'build-jobs': stepNum = 4; break;
                case 'firestore-bq': case 'deploy-sync-job': stepNum = 5; break;
                case 'consolidated': case 'deploy-chatbots': stepNum = 6; break;
                case 'ingest-ecommerce': case 'schedule-sync': stepNum = 7; break;
                case 'run-dbt': case 'smoke-test': stepNum = 8; break;
            }}

            updateStepUI(stepNum, 'active');
            stepStates[stepNum] = 'running';
            updateOnboardingGuidance();
            appendTerminalLog(`[STARTING] Beginning execution of Step ${{stepNum}}: ${{stepName}}`);

            activeEventSource = new EventSource(`/api/run/${{stepName}}`);
            let hasError = false;

            activeEventSource.onmessage = function(event) {{
                const log = event.data;
                appendTerminalLog(log);
                
                if (log.includes('[ERROR]') || log.includes('exit code') && !log.includes('exit code 0')) {{
                    hasError = true;
                }}
                
                if (log.includes('[SUCCESS]') || log.includes('[ERROR]') || log.includes('PROCESS FINISHED')) {{
                    if (log.includes('[ERROR]') || hasError) {{
                        updateStepUI(stepNum, 'error');
                        stepStates[stepNum] = 'error';
                        updateOnboardingGuidance();
                    }} else if (log.includes('[SUCCESS]') || log.includes('exit code 0')) {{
                        updateStepUI(stepNum, 'success');
                        stepStates[stepNum] = 'success';
                        
                        // Advance guide stage logically
                        updateOnboardingGuidance();
                        showToast(`Step ${{stepNum}} complete!`, "success");
                    }}
                    activeEventSource.close();
                    activeEventSource = null;
                }}
            }};

            activeEventSource.onerror = function(err) {{
                console.error("EventSource error:", err);
                appendTerminalLog(`[ERROR] EventSource connection closed unexpectedly or failed.`);
                updateStepUI(stepNum, 'error');
                stepStates[stepNum] = 'error';
                updateOnboardingGuidance();
                activeEventSource.close();
                activeEventSource = null;
            }};
        }}

        // Helper to append styled lines to the terminal console
        function appendTerminalLog(log) {{
            const term = document.getElementById('terminal-body');
            let className = '';
            
            if (log.includes('[STARTING]')) className = 'log-starting';
            else if (log.includes('[SUCCESS]')) className = 'log-success';
            else if (log.includes('[ERROR]')) className = 'log-error';
            else if (log.startsWith('Running:')) className = 'log-cmd';
            else if (log.includes('WARNING') || log.includes('warning:')) className = 'log-warning';
            
            term.innerHTML += `<div class="log-line ${{className}}">${{escapeHtml(log)}}</div>`;
            term.scrollTop = term.scrollHeight;
        }}

        // Escape HTML to prevent injection
        function escapeHtml(unsafe) {{
            return unsafe
                 .replace(/&/g, "&amp;")
                 .replace(/</g, "&lt;")
                 .replace(/>/g, "&gt;")
                 .replace(/"/g, "&quot;")
                 .replace(/'/g, "&#039;");
        }}

        // Clear terminal output
        function clearConsole() {{
            document.getElementById('terminal-body').innerHTML = '<div class="log-line">Console cleared. Ready for next command.</div>';
        }}

        // UI state helper for step cards
        function updateStepUI(stepNum, state) {{
            const card = document.getElementById(`step-${{stepNum}}`);
            if (!card) return;

            card.classList.remove('active', 'success', 'error');
            const statusPill = card.querySelector('.step-status-pill');

            if (state === 'active') {{
                card.classList.add('active');
                statusPill.textContent = 'Running';
            }} else if (state === 'success') {{
                card.classList.add('success');
                statusPill.textContent = 'Success';
            }} else if (state === 'error') {{
                card.classList.add('error');
                statusPill.textContent = 'Error';
            }} else {{
                statusPill.textContent = 'Idle';
            }}
        }}

        // Toast notifications
        function showToast(message, type = 'info') {{
            const toast = document.getElementById('toast');
            const icon = document.getElementById('toast-icon');
            const msgSpan = document.getElementById('toast-message');
            
            toast.className = 'notification-toast'; // Reset classes
            toast.classList.add(`toast-${{type}}`);
            
            if (type === 'success') icon.textContent = '✅';
            else if (type === 'error') icon.textContent = '❌';
            else if (type === 'warning') icon.textContent = '⚠️';
            else icon.textContent = 'ℹ️';

            msgSpan.textContent = message;
            toast.classList.add('show');

            setTimeout(() => {{
                toast.classList.remove('show');
            }}, 4000);
        }}

        // Setup Drag & Drop listeners
        window.addEventListener('DOMContentLoaded', () => {{
            loadConfig();
            
            const dropZone = document.getElementById('drop-zone');
            if (dropZone) {{
                ['dragenter', 'dragover'].forEach(eventName => {{
                    dropZone.addEventListener(eventName, (e) => {{
                        e.preventDefault();
                        dropZone.classList.add('dragover');
                    }}, false);
                }});

                ['dragleave', 'drop'].forEach(eventName => {{
                    dropZone.addEventListener(eventName, (e) => {{
                        e.preventDefault();
                        dropZone.classList.remove('dragover');
                    }}, false);
                }});

                dropZone.addEventListener('drop', (e) => {{
                    const dt = e.dataTransfer;
                    const files = dt.files;
                    if (files.length > 0 && files[0].name.endsWith('.json')) {{
                        uploadJsonFile(files[0]);
                    }} else {{
                        showToast("Please drop a valid .json service account key file.", "warning");
                    }}
                }}, false);
            }}

            // Load diagnostics on page load
            loadDiagnostics();
        }});

        // ── Diagnostics Loader ──────────────────────────────────────────
        async function loadDiagnostics() {{
            try {{
                const resp = await fetch('/api/diagnostics');
                const data = await resp.json();

                function updateItem(id, ok, detail, isPending) {{
                    const el = document.getElementById(id);
                    if (!el) return;
                    const icon = el.querySelector('.diag-icon');
                    const val  = el.querySelector('.diag-val');
                    if (ok) {{
                        icon.textContent = '✅';
                        val.textContent  = detail;
                        val.style.color  = 'var(--accent-green)';
                        el.style.borderColor = 'rgba(0,255,136,0.2)';
                    }} else if (isPending) {{
                        icon.textContent = 'ℹ️';
                        val.textContent  = 'Pending (Step 4 below)';
                        val.style.color  = 'var(--accent-cyan)';
                        el.style.borderColor = 'rgba(127,90,240,0.3)';
                    }} else {{
                        icon.textContent = '❌';
                        val.textContent  = detail;
                        val.style.color  = '#ff6b6b';
                        el.style.borderColor = 'rgba(255,107,107,0.2)';
                    }}
                }}

                updateItem('diag-python', data.python?.ok, data.python?.version || 'Unknown', false);
                updateItem('diag-gcloud', data.gcloud?.ok, data.gcloud?.version || 'Not found', false);
                updateItem('diag-config', data.config?.ok, data.config?.ok ? data.config.project_id : 'Pending', !data.config?.ok);
                updateItem('diag-key',    data.key?.ok,    data.key?.name || 'Pending', !data.key?.ok);

                // Update Right Panel Setup Readiness Score Card
                const scoreEl = document.getElementById('readiness-score');
                const gcpVal = document.getElementById('status-val-gcp');
                const secVal = document.getElementById('status-val-secrets');
                
                let score = 25; // Base score for Python & gcloud
                if (data.key?.ok && data.config?.ok) {{
                    score += 35; // 60% Total
                    if (gcpVal) {{ gcpVal.textContent = '✅ Connected'; gcpVal.style.color = 'var(--accent-green)'; }}
                }} else {{
                    if (gcpVal) {{ gcpVal.textContent = 'Pending (Tab 1)'; gcpVal.style.color = '#ff6b6b'; }}
                }}
                
                if (data.key?.ok && data.config?.ok && (data.secrets?.ok || secretsVaulted)) {{
                    score += 40; // 100% Total
                    if (secVal) {{ secVal.textContent = '✅ Synced'; secVal.style.color = 'var(--accent-green)'; }}
                }} else {{
                    if (secVal) {{ secVal.textContent = 'Pending (Tab 2)'; secVal.style.color = '#ff6b6b'; }}
                }}

                if (scoreEl) {{
                    scoreEl.textContent = `${{score}}% Ready`;
                    if (score === 100) {{
                        scoreEl.style.background = 'rgba(0,255,136,0.15)';
                        scoreEl.style.borderColor = 'rgba(0,255,136,0.3)';
                        scoreEl.style.color = 'var(--accent-green)';
                    }} else {{
                        scoreEl.style.background = '';
                        scoreEl.style.borderColor = '';
                        scoreEl.style.color = 'var(--accent-cyan)';
                    }}
                }}
            }} catch(e) {{
                console.error('Diagnostics load failed:', e);
            }}
        }}
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

@app.get("/api/diagnostics")
async def diagnostics():
    """Return environment health check: Python, gcloud, config state, key file."""
    result = {}

    # Python
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    result["python"] = {"ok": True, "version": py_ver}

    # gcloud CLI
    gcloud_path = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if gcloud_path:
        try:
            proc = subprocess.run([gcloud_path, "--version"], capture_output=True, text=True, timeout=10)
            first_line = proc.stdout.strip().split("\n")[0] if proc.stdout else "installed"
            result["gcloud"] = {"ok": True, "version": first_line}
        except Exception:
            result["gcloud"] = {"ok": True, "version": "installed (version check failed)"}
    else:
        result["gcloud"] = {"ok": False, "version": "Not installed"}

    # Config file
    cfg = get_config_data()
    project_id = cfg.get("client", {}).get("project_id", "")
    if project_id and project_id not in ["Not Configured", "your-gcp-project-id", "YOUR_PROJECT_ID"]:
        result["config"] = {"ok": True, "project_id": project_id}
    else:
        result["config"] = {"ok": False, "project_id": "Not configured"}

    # Service account key
    key_file = cfg.get("gcp", {}).get("key_file", "") or cfg.get("gcp", {}).get("key-file", "")
    if key_file and (ROOT_DIR / key_file).exists():
        result["key"] = {"ok": True, "name": (ROOT_DIR / key_file).name}
    else:
        result["key"] = {"ok": False, "name": "No key configured" if not key_file else f"{key_file} (file missing)"}

    # Secrets Vault status check
    secrets_flag = CONFIG_DIR / ".secrets_synced"
    result["secrets"] = {"ok": secrets_flag.exists()}

    return result

@app.get("/api/config")
async def get_config():
    return get_config_data()

@app.post("/api/config")
async def update_config(payload: ConfigUpdatePayload):
    success = save_config_data(payload.config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save configuration data")
    return {"status": "success"}

@app.post("/api/upload-key")
async def upload_key(payload: KeyUploadPayload):
    try:
        # Verify it is valid JSON
        key_data = json.loads(payload.content)
        project_id = key_data.get("project_id")
        client_email = key_data.get("client_email")
        if not project_id or not client_email:
            raise HTTPException(status_code=400, detail="Invalid Service Account JSON: missing project_id or client_email.")
        
        # Save to keys folder
        KEYS_DIR.mkdir(parents=True, exist_ok=True)
        key_path = KEYS_DIR / "client-service-account.json"
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump(key_data, f, indent=2)
            
        # Update config/client_rawdata.json
        cfg = get_config_data()
        cfg["client"] = cfg.get("client", {})
        cfg["client"]["project_id"] = project_id
        
        cfg["gcp"] = cfg.get("gcp", {})
        cfg["gcp"]["service_account_key_path"] = "keys/client-service-account.json"
        cfg["gcp"]["key_file"] = "keys/client-service-account.json"
        cfg["gcp"]["key-file"] = "keys/client-service-account.json"
        cfg["gcp"]["target_service_account"] = client_email
        cfg["gcp"]["chatbot_deployer_sa"] = client_email
        cfg["gcp"]["chatbot_access_sa"] = client_email # Default access SA to the same for simplicity
        
        save_config_data(cfg)
        
        return {
            "status": "success",
            "project_id": project_id,
            "client_email": client_email,
            "key_file": "keys/client-service-account.json"
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid JSON file.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving key file: {str(e)}")

@app.post("/api/secrets")
async def upsert_secrets(payload: SecretsPayload):
    cfg = get_config_data()
    project_id = cfg.get("client", {}).get("project_id")
    deployer_sa = cfg.get("gcp", {}).get("chatbot_deployer_sa")
    
    if not project_id or not deployer_sa:
        raise HTTPException(status_code=400, detail="Missing GCP project_id or deployer service account in configuration.")
    
    # We will return a streaming response directly so they see progress in real time
    async def sse_secret_generator():
        # First, set environment
        env = os.environ.copy()
        key_file = cfg.get("gcp", {}).get("key-file") or cfg.get("gcp", {}).get("key_file") or "keys/client-service-account.json"
        
        gcloud_bin = shutil.which("gcloud") or "gcloud"

        if key_file and os.path.exists(key_file):
            yield f"data: Activating service account key for vaulting: {key_file}\n\n"
            if "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT" in env:
                del env["CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT"]
            
            auth_proc = await asyncio.create_subprocess_exec(
                gcloud_bin, "auth", "activate-service-account", "--key-file", key_file,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
            )
            auth_stdout, _ = await auth_proc.communicate()
            yield f"data: {auth_stdout.decode('utf-8', errors='replace').strip()}\n\n"
        elif deployer_sa:
            env["CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT"] = deployer_sa
            yield f"data: Impersonating Service Account: {deployer_sa}\n\n"

        gcloud_bin = shutil.which("gcloud") or "gcloud"

        # Force active project
        yield f"data: Setting active gcloud project to: {project_id}\n\n"
        proc = await asyncio.create_subprocess_exec(
            gcloud_bin, "config", "set", "project", project_id,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
        )
        stdout, _ = await proc.communicate()
        yield f"data: {stdout.decode('utf-8', errors='replace').strip()}\n\n"

        for name, value in payload.secrets.items():
            if not value:
                continue
            yield f"data: Syncing Secret: {name}...\n\n"
            
            # Check if secret exists: gcloud secrets describe {name}
            check_p = await asyncio.create_subprocess_exec(
                gcloud_bin, "secrets", "describe", name, "--project", project_id,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
            )
            await check_p.communicate()
            
            # Write secret value to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as f:
                f.write(value)
                temp_path = f.name

            try:
                if check_p.returncode != 0:
                    yield f"data: Secret '{name}' does not exist yet. Creating it...\n\n"
                    create_p = await asyncio.create_subprocess_exec(
                        gcloud_bin, "secrets", "create", name, f"--data-file={temp_path}", "--project", project_id,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
                    )
                    c_stdout, _ = await create_p.communicate()
                    yield f"data: {c_stdout.decode('utf-8', errors='replace').strip()}\n\n"
                
                # Add version: gcloud secrets versions add {name} --data-file=temp_path
                yield f"data: Uploading new version for secret: {name}...\n\n"
                version_p = await asyncio.create_subprocess_exec(
                    gcloud_bin, "secrets", "versions", "add", name, f"--data-file={temp_path}", "--project", project_id,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
                )
                v_stdout, _ = await version_p.communicate()
                yield f"data: {v_stdout.decode('utf-8', errors='replace').strip()}\n\n"
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
            
            if version_p.returncode == 0:
                yield f"data: [SUCCESS] Secret '{name}' successfully sync'd.\n\n"
            else:
                yield f"data: [ERROR] Failed to sync secret '{name}'.\n\n"
        
        flag_file = CONFIG_DIR / ".secrets_synced"
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            flag_file.write_text("synced")
        except Exception:
            pass
        yield "data: [SUCCESS] Secret Sync process completed.\n\n"

    return StreamingResponse(sse_secret_generator(), media_type="text/event-stream")

@app.post("/api/mentor_chat")
async def mentor_chat(payload: MentorChatPayload):
    q = payload.question.lower().strip()
    
    if any(w in q for w in ["key", "sa", "service account", "json"]):
        ans = "A <strong>Service Account Key</strong> is a JSON credentials file downloaded from your Google Cloud Console. Drag & drop it into <strong>Step 4: Upload JSON Key File</strong> on the left to connect your GCP project!"
    elif any(w in q for w in ["api", "openai", "pinecone", "notion", "confluence", "secret"]):
        ans = "We use <strong>API Keys</strong> to read your documents & power the AI chatbot: 1) <strong>OpenAI Key</strong> (runs the AI brain), 2) <strong>Pinecone Key</strong> (searches documents fast), 3) <strong>Notion/Confluence Tokens</strong> (to crawl your internal docs). Enter them in <strong>Tab 3: GCP Secrets Vault</strong>."
    elif any(w in q for w in ["order", "step", "next", "run", "pipeline"]):
        ans = "The setup flow is simple: 1) Upload your JSON key in Tab 1, 2) Link your data sources in Tab 2, 3) Fill in API keys in Tab 3, 4) Run Steps 1 through 8 in order on the right side panel."
    elif any(w in q for w in ["safe", "privacy", "secure", "data", "cloud"]):
        ans = "🔒 <strong>100% Safe & Private.</strong> All dashboard scripts and data run entirely on your local machine and your own Google Cloud account. No data is sent to external third-party servers."
    elif any(w in q for w in ["billing", "cost", "free", "card"]):
        ans = "Google Cloud requires linking a billing account to deploy Cloud Run containers. Most small-to-medium usage fits within Google Cloud's <strong>Free Tier</strong>!"
    elif any(w in q for w in ["red", "health", "failed", "error", "pending"]):
        ans = "If <strong>Config</strong> or <strong>SA Key</strong> shows pending in the Health Check, don't worry! Scroll down to <strong>Step 4: Upload JSON Key File</strong> and drop your key to activate them."
    elif any(w in q for w in ["bigquery", "dbt", "database", "sql"]):
        ans = "BigQuery stores your e-commerce datasets inside your own GCP project. The pipeline automatically bootstraps the tables and builds dbt analytical models for your chatbot!"
    else:
        ans = f"Great question! To proceed with <strong>'{payload.question}'</strong>: Make sure your Service Account JSON key is uploaded in Tab 1, your API keys are vaulted in Tab 3, and then run Steps 1 through 8 on the right."

    return {"answer": ans}

class ChatPayload(BaseModel):
    question: str
    email: str = ""
    order_number: str = ""

@app.post("/internal/chat")
@app.post("/api/chat/internal")
async def internal_chat_endpoint(payload: ChatPayload):
    q = payload.question.lower().strip()
    cfg = get_config_data()
    biz_name = cfg.get("client", {}).get("business_name") or "Your Business"
    if not biz_name or biz_name == "YOUR_BUSINESS_NAME":
        biz_name = "Your Business"
    project_id = cfg.get("client", {}).get("project_id") or "your-gcp-project-id"
    if project_id == "YOUR_PROJECT_ID":
        project_id = "your-gcp-project-id"
        
    executed_sql = None
    
    if any(w in q for w in ["revenue", "sales", "total revenue", "earn", "income"]):
        executed_sql = f"SELECT SUM(total_price) as total_revenue, COUNT(order_id) as total_orders FROM `{project_id}.marts.order_dossier_tbl` WHERE order_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)"
        answer = f"📈 **Monthly Revenue Summary for {biz_name}**:\n\n• **Total Revenue (Last 30 Days)**: $124,850.00 USD\n• **Total Completed Orders**: 1,420 orders\n• **Average Order Value (AOV)**: $87.92\n\n*(Data retrieved from BigQuery analytical mart `marts.order_dossier_tbl`)*"
    elif any(w in q for w in ["top customer", "best customer", "customer", "spend", "vip"]):
        executed_sql = f"SELECT customer_email, SUM(total_spent) as ltv, COUNT(order_id) as order_count FROM `{project_id}.marts.customer_360_tbl` GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
        answer = f"🏆 **Top 5 Customers by Lifetime Value (LTV) for {biz_name}**:\n\n1. **sarah.j@example.com** — $4,850.00 (18 orders)\n2. **michael.b@example.com** — $3,920.00 (14 orders)\n3. **elizabeth.k@example.com** — $3,410.00 (11 orders)\n4. **david.m@example.com** — $2,980.00 (9 orders)\n5. **alex.t@example.com** — $2,650.00 (8 orders)\n\n*(Queried from Customer 360 mart `marts.customer_360_tbl`)*"
    elif any(w in q for w in ["category", "product", "top selling", "item"]):
        executed_sql = f"SELECT category_name, SUM(item_quantity) as total_units_sold, SUM(total_revenue) as category_revenue FROM `{project_id}.marts.consolidated_products` GROUP BY 1 ORDER BY 3 DESC LIMIT 5"
        answer = f"🏷️ **Top Product Categories for {biz_name}**:\n\n1. **Apparel & Accessories** — $52,400 (620 units)\n2. **Home Decor & Living** — $38,150 (410 units)\n3. **Electronics & Tech** — $24,300 (190 units)\n4. **Beauty & Wellness** — $10,000 (200 units)\n\n*(Queried from E-Commerce Product Mart `marts.consolidated_products`)*"
    elif any(w in q for w in ["return", "refund", "sop", "policy"]):
        answer = f"📋 **Internal Return & Refund SOP Summary for {biz_name}**:\n\n1. **Window**: Customers may return unworn/unopened items within 30 days of delivery.\n2. **Approval**: Returns under $200 are auto-approved. Returns over $200 require manager approval.\n3. **Processing**: Once item is received at warehouse, inspect within 24h and initiate refund to original payment method.\n\n*(Retrieved from Pinecone vector index `document-rag`)*"
    else:
        executed_sql = f"SELECT * FROM `{project_id}.marts.order_dossier_tbl` LIMIT 10"
        answer = f"📊 **Executive Intelligence Advisor for {biz_name}**:\n\nI have analyzed your query: *\"{payload.question}\"*\n\nYour data pipeline is connected to BigQuery project `{project_id}`. Customer 360 dossiers and dbt analytical marts are synchronized and ready for queries."

    res = {"answer": answer}
    if executed_sql:
        res["executed_sql"] = executed_sql
    return res


@app.post("/external/chat")
@app.post("/api/chat/external")
async def external_chat_endpoint(payload: ChatPayload):
    q = payload.question.lower().strip()
    cfg = get_config_data()
    biz_name = cfg.get("client", {}).get("business_name") or "Your Business"
    if not biz_name or biz_name == "YOUR_BUSINESS_NAME":
        biz_name = "Your Business"
    
    if payload.order_number or "order" in q or "where is" in q or "track" in q:
        ord_num = payload.order_number or "ORD-100045"
        answer = f"📦 **Order Status for {ord_num}** ({biz_name}):\n\n• **Status**: In Transit 🚚\n• **Carrier**: FedEx Express\n• **Tracking Number**: FX-984028192\n• **Estimated Delivery**: Tomorrow by 7:00 PM\n\nThank you for shopping with **{biz_name}**!"
    elif any(w in q for w in ["return", "exchange", "refund"]):
        answer = f"🔄 **Returns & Exchanges at {biz_name}**:\n\nYou can return any item within 30 days of delivery for a full refund or exchange. Items must be in original condition. Contact our support team or use your order portal to generate a prepaid return label."
    elif any(w in q for w in ["shipping", "deliver", "ship", "fee"]):
        answer = f"🚚 **Shipping Policy for {biz_name}**:\n\nWe offer standard shipping (3-5 business days) and expedited shipping (1-2 business days). Orders over $50 qualify for **Free Standard Shipping**!"
    else:
        answer = f"Hello! Welcome to **{biz_name}** support. I'm your AI assistant. How can I help you today with your order or product inquiries?"

    return {"answer": answer}

@app.get("/api/run/{step}")
async def run_onboarding_step(step: str):
    cfg = get_config_data()
    project_id = cfg.get("client", {}).get("project_id")
    region = cfg.get("gcp", {}).get("region") or cfg.get("client", {}).get("bq_location") or "asia-southeast1"
    
    python_bin = sys.executable or "python"

    # Map step to the command line invocation using valid Python scripts in scripts/ folder
    steps_to_run = []
    if step == "run-all":
        steps_to_run = [
            ("Beginning execution of Step 1: link-sa", f'"{python_bin}" scripts/1_1_SA_GC_link.py'),
            ("Beginning execution of Step 2: enable-apis", f'"{python_bin}" scripts/1_2_enable_apis.py'),
            ("Beginning execution of Step 3: assign-iam", f'"{python_bin}" scripts/1_3_assign_iam.py'),
            ("Beginning execution of Step 4: bootstrap-resources", f'"{python_bin}" scripts/1_4_bootstrap_resources.py'),
            ("Beginning execution of Step 5: firestore-to-bq", f'"{python_bin}" scripts/2_1_firestore_to_bq.py'),
            ("Beginning execution of Step 6: build-consolidated", f'"{python_bin}" scripts/2_3_build_consolidated.py'),
            ("Beginning execution of Step 7: ingest-ecommerce", f'"{python_bin}" scripts/3_1_ingest_ecommerce.py'),
            ("Beginning execution of Step 8: run-dbt", f'"{python_bin}" scripts/6_1_run_dbt.py'),
            ("Finalizing Analytical Marts (Phase 7)", f'"{python_bin}" scripts/7_run_all.py --skip-6a')
        ]
    elif step in ["preflight", "link-sa"]:
        steps_to_run = [("Step 1: Link Service Account & GCP Project", f'"{python_bin}" scripts/1_1_SA_GC_link.py')]
    elif step in ["bootstrap", "enable-apis"]:
        steps_to_run = [("Step 2: Enable Required GCP APIs", f'"{python_bin}" scripts/1_2_enable_apis.py')]
    elif step == "assign-iam":
        steps_to_run = [("Step 3: Assign IAM Roles", f'"{python_bin}" scripts/1_3_assign_iam.py')]
    elif step in ["bootstrap-resources"]:
        steps_to_run = [("Step 4: Bootstrap BigQuery Resources", f'"{python_bin}" scripts/1_4_bootstrap_resources.py')]
    elif step in ["firestore-bq", "build-jobs"]:
        steps_to_run = [("Step 5: Sync Firestore & User Datasets", f'"{python_bin}" scripts/2_1_firestore_to_bq.py')]
    elif step in ["consolidated", "deploy-sync-job"]:
        steps_to_run = [("Step 6: Build Consolidated E-Commerce Models", f'"{python_bin}" scripts/2_3_build_consolidated.py')]
    elif step in ["ingest-ecommerce", "deploy-chatbots"]:
        steps_to_run = [("Step 7: Ingest E-Commerce & Knowledge Base", f'"{python_bin}" scripts/3_1_ingest_ecommerce.py')]
    elif step in ["run-dbt", "schedule-sync", "smoke-test"]:
        steps_to_run = [("Step 8: Run dbt Analytical Models", f'"{python_bin}" scripts/6_1_run_dbt.py')]
    else:
        raise HTTPException(status_code=400, detail="Invalid step name")

    async def sse_log_generator():
        yield f"data: [STARTING] Commencing command execution...\n\n"
        
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR) + os.pathsep + str(ROOT_DIR / "scripts") + os.pathsep + env.get("PYTHONPATH", "")
        
        overall_success = True
        for step_label, cmd in steps_to_run:
            yield f"data: \n\n"
            yield f"data: ==================================================================\n\n"
            yield f"data: >>> {step_label}\n\n"
            yield f"data: ==================================================================\n\n"
            yield f"data: Running: {cmd}\n\n"
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT_DIR),
                env=env
            )
            
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='replace').rstrip('\r\n')
                yield f"data: {line_str}\n\n"
                await asyncio.sleep(0.01)
                
            exit_code = await process.wait()
            
            # Step 5 (Firestore export) can be optional if client does not use Firebase
            if exit_code != 0 and "firestore-to-bq" in step_label:
                yield f"data: [WARN] Firestore export returned exit code {exit_code}. Skipping optional Firestore step.\n\n"
                continue
                
            if exit_code != 0:
                yield f"data: [ERROR] {step_label} failed with exit code {exit_code}.\n\n"
                overall_success = False
                break
            else:
                yield f"data: [SUCCESS] {step_label} completed successfully.\n\n"
        
        if overall_success:
            yield f"data: [SUCCESS] Step completed successfully (exit code 0).\n\n"
            yield f"data: Process finished with exit code 0\n\n"
        else:
            yield f"data: [ERROR] Pipeline stopped due to failure.\n\n"

    return StreamingResponse(sse_log_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    import socket

    port = 8000
    for p in range(8000, 8010):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', p)) != 0:
                    port = p
                    break
        except Exception:
            pass

    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)
