#!/usr/bin/env python3
import sys
from pathlib import Path

# Ensure repo root is on PYTHONPATH so `utils` can be imported
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
    
import os
from pinecone import Pinecone
from dotenv import load_dotenv
from utils.config_loader import load_client_config


# Load environment variables from .env.local
load_dotenv(".env.local")

CFG = load_client_config()

# Secrets come from env
API_KEY = os.environ["PINECONE_API_KEY"]

# Architecture comes from JSON
DOC_RAG = CFG["document_rag"]
INDEX_NAME = DOC_RAG["index_name"]
DIMENSION  = DOC_RAG["dimension"]
METRIC     = DOC_RAG.get("metric", "cosine")

pc = Pinecone(api_key=API_KEY)

existing = [i["name"] for i in pc.list_indexes()]
if INDEX_NAME in existing:
    print(f"Index exists: {INDEX_NAME}")
else:
    print(f"Creating index: {INDEX_NAME} (dim={DIMENSION})")
    pc.create_index(
        name=INDEX_NAME,
        dimension=DIMENSION,
        metric=METRIC,
        spec={
            "serverless": {
                "cloud": "aws",
                "region": "us-east-1"
            }
        }
    )

print("Done.")
