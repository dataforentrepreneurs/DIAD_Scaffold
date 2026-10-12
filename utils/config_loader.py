import json
from pathlib import Path

def load_client_config():
    repo_root = Path(__file__).resolve().parents[1]
    cfg_path = repo_root / "config" / "client_rawdata.json"
    if not cfg_path.exists():
        cfg_path = repo_root / "config" / "client_rawdata.json.example"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)
