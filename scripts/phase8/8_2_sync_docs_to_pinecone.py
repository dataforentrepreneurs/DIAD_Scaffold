#!/usr/bin/env python3
"""
8_2_sync_docs_to_pinecone.py

Install packages:
  pip install pinecone-client openai google-api-python-client google-auth-httplib2 google-auth-oauthlib
  # Optional (for local embeddings fallback): pip install sentence-transformers

DIAD Phase 8 — Documentation Crawler
Syncs documents from Google Drive, Notion, and Confluence into Pinecone.
"""
import sys
from pathlib import Path

# Ensure repo root (diad/) is on sys.path so `utils` can be imported
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from dotenv import load_dotenv

from utils.config_loader import load_client_config
load_dotenv(".env.local")

    
import argparse
import json
import logging
import os
import re
import io
import time
from typing import Dict, List, Optional, Callable

import requests
from pinecone import Pinecone

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload



raw_cfg = {}
MAX_DOC_CHARS = 200_000  # safety cap ~200 KB of text

# ------------------------------------------------------
# Logging
# ------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("phase8_docs_sync")


# ------------------------------------------------------
# Utility Helpers
# ------------------------------------------------------

def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def strip_html(html: str) -> str:
    """
    Very simple HTML → text helper for Confluence.
    """
    if not html:
        return ""
    # remove tags
    text = re.sub(r"<[^>]+>", "", html)
    # collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text, max_chunk_size=2000, overlap=200, max_total_chars=MAX_DOC_CHARS):
    """
    Safely chunk a long string into overlapping pieces.

    - Forces `text` to string
    - Caps max length per document (to avoid MemoryError on gigantic pages)
    - Returns a list of chunks
    """
    if text is None:
        return []

    # Ensure it's a string (sometimes APIs can return weird types)
    if not isinstance(text, str):
        text = str(text)

    # Strip leading/trailing whitespace to reduce size a bit
    text = text.strip()

    text_len = len(text)

    # Hard cap extremely large documents
    if text_len > max_total_chars:
        logging.warning(
            "Document is very large (%d chars). Truncating to %d characters for embedding.",
            text_len,
            max_total_chars,
        )
        text = text[:max_total_chars]
        text_len = len(text)

    if text_len == 0:
        return []

    chunks = []
    start = 0

    while start < text_len:
        end = min(start + max_chunk_size, text_len)
        chunks.append(text[start:end])

        if end == text_len:
            break

        # Overlap for context
        start = end - overlap

    return chunks

def print_index_counts(index, namespaces=("gdrive", "notion", "confluence")):
    try:
        stats = index.describe_index_stats()
        ns = stats.get("namespaces", {})
        logger.info("📊 Pinecone counts by namespace:")
        for n in namespaces:
            count = ns.get(n, {}).get("vector_count", 0)
            logger.info("   - %s: %s vectors", n, count)
        logger.info("   - total: %s vectors", stats.get("total_vector_count"))
    except Exception as e:
        logger.warning("⚠ Could not fetch Pinecone index stats: %s", e)

# ------------------------------------------------------
# visibility classifier function
# ------------------------------------------------------

def classify_visibility(
    source: str,
    *,
    drive_folder_id=None,
    notion_page_id=None,
    confluence_space_key=None,
):
    vis_cfg = raw_cfg.get("document_visibility", {})
    defaults = vis_cfg.get("defaults", {})

    source = source.lower()

    # Confluence — always internal for now
    if source == "confluence":
        return "internal"

    # Drive
    if source in ("drive", "gdrive"):
        external_folders = set(vis_cfg.get("drive", {}).get("external_folder_ids", []))
        if drive_folder_id in external_folders:
            return "external"
        return defaults.get("drive", "internal")

    # Notion
    if source == "notion":
        external_pages = set(vis_cfg.get("notion", {}).get("external_page_ids", []))
        if notion_page_id in external_pages:
            return "external"
        return defaults.get("notion", "internal")

    return "internal"



# ------------------------------------------------------
# Google Drive
# ------------------------------------------------------

def build_drive_service(service_account_key_path: str):
    """
    Build a Drive API service using a service account JSON key.
    """
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    credentials = service_account.Credentials.from_service_account_file(
        service_account_key_path,
        scopes=scopes,
    )
    service = build("drive", "v3", credentials=credentials)
    return service


def crawl_drive_folder(service, folder_id: str) -> List[Dict]:
    """
    Crawl a folder in Google Drive and return documents (id, name, mimeType).

    We treat as "eligible docs":
      - Google Docs       : application/vnd.google-apps.document
      - Word DOCX         : application/vnd.openxmlformats-officedocument.wordprocessingml.document
      - Legacy Word DOC   : application/msword
      - PDF               : application/pdf
      - Plain text files  : text/plain
    """
    logger.info(f"📁 Crawling Google Drive folder: {folder_id}")
    docs = []

    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, md5Checksum, version)",
                pageToken=page_token,
            )
            .execute()
        )

        for f in resp.get("files", []):
            file_id = f.get("id")
            name = f.get("name")
            mime = f.get("mimeType", "")

            logger.info("   • Drive file: %s (%s) mime=%s", name, file_id, mime)

            if mime in (
                "application/vnd.google-apps.document",  # Google Doc
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # DOCX
                "application/msword",  # old .doc
                "application/pdf",  # PDF
                "text/plain",  # raw text files
            ):
                docs.append(
                    {
                        "id": file_id,
                        "name": name,
                        "mimeType": mime,
                        "modifiedTime": f.get("modifiedTime"),
                        "md5Checksum": f.get("md5Checksum"),
                        "version": f.get("version"),
                    }
                )

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    logger.info(f"📄 Found {len(docs)} eligible Drive docs (GDoc/DOCX/PDF/TXT)")
    return docs


def export_gdoc_as_text(service, file_id: str) -> str:
    """
    Export a Google Doc as plain text.
    """
    logger.info(f"   ↳ Exporting Google Doc {file_id} as text")
    resp = (
        service.files()
        .export(fileId=file_id, mimeType="text/plain")
        .execute()
    )
    # resp is bytes
    if isinstance(resp, bytes):
        return resp.decode("utf-8", errors="ignore")
    return str(resp)



def download_drive_file_bytes(service, file_id: str, retries: int = 5) -> bytes:
    """
    Download a file from Drive as raw bytes (DOCX/PDF/TXT) with retries.
    """
    logger.info(f"   ↳ Downloading Drive file {file_id} as bytes")

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            fh.seek(0)
            return fh.read()

        except HttpError as e:
            last_err = e
            wait = min(2 ** attempt, 30)
            logger.warning("⚠ Drive download failed (attempt %d/%d) for %s: %s. Retrying in %ss",
                           attempt, retries, file_id, e, wait)
            time.sleep(wait)

        except Exception as e:
            last_err = e
            wait = min(2 ** attempt, 30)
            logger.warning("⚠ Drive download failed (attempt %d/%d) for %s: %s. Retrying in %ss",
                           attempt, retries, file_id, e, wait)
            time.sleep(wait)

    raise RuntimeError(f"Failed to download Drive file after {retries} retries: {file_id}. Last error: {last_err}")


def extract_text_from_docx(data: bytes) -> str:
    """
    Extract text from a DOCX file (bytes) using python-docx.
    """
    try:
        from docx import Document
    except ImportError:
        logger.warning("⚠ python-docx not installed; cannot read DOCX files.")
        return ""

    file_obj = io.BytesIO(data)
    doc = Document(file_obj)
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(paragraphs)


def extract_text_from_pdf(data: bytes) -> str:
    """
    Extract text from a PDF file (bytes) using PyPDF2.
    """
    try:
        import PyPDF2
    except ImportError:
        logger.warning("⚠ PyPDF2 not installed; cannot read PDF files.")
        return ""

    file_obj = io.BytesIO(data)
    reader = PyPDF2.PdfReader(file_obj)

    texts = []
    for page in reader.pages:
        try:
            txt = page.extract_text() or ""
        except Exception as e:
            logger.warning("⚠ Failed to extract text from one PDF page: %s", e)
            txt = ""
        if txt:
            texts.append(txt)

    return "\n".join(texts)


def extract_text_from_bytes_as_utf8(data: bytes) -> str:
    """
    Fallback for plain text files.
    """
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def crawl_drive(folder_id: str, service_account_key_path: str) -> List[Dict]:
    """
    Returns a list of documents with keys:
      - source: "gdrive"
      - doc_id
      - name
      - text

    Supports:
      - Google Docs
      - DOCX / DOC
      - PDF
      - Plain text files
    """
    service = build_drive_service(service_account_key_path)
    files = crawl_drive_folder(service, folder_id)
    docs = []

    for f in files:
        file_id = f["id"]
        name = f["name"]
        mime = f["mimeType"]

        logger.info("📥 Processing Drive doc: %s (%s) mime=%s", name, file_id, mime)

        text = ""

        try:
            if mime == "application/vnd.google-apps.document":
                # Native Google Doc → export as text/plain
                text = export_gdoc_as_text(service, file_id)

            elif mime in (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/msword",
            ):
                # Word DOCX/DOC
                data = download_drive_file_bytes(service, file_id)
                text = extract_text_from_docx(data)

            elif mime == "application/pdf":
                # PDF
                data = download_drive_file_bytes(service, file_id)
                text = extract_text_from_pdf(data)

            elif mime == "text/plain":
                # Plain text file
                data = download_drive_file_bytes(service, file_id)
                text = extract_text_from_bytes_as_utf8(data)
            else:
                logger.warning(
                    "⚠ Skipping unsupported Drive mimeType %s for file %s",
                    mime,
                    name,
                )
                continue

        except Exception as e:
            logger.warning(
                "⚠ Failed to extract text from Drive file %s (%s): %s",
                name,
                file_id,
                e,
            )
            continue

        text = (text or "").strip()
        if not text:
            logger.warning("⚠ Extracted empty text from Drive file %s; skipping.", name)
            continue

        docs.append(
            {
                "source": "gdrive",
                "doc_id": file_id,
                "name": name,
                "text": text,
                "folder_id": folder_id,  # 👈 root folder we crawled
                "modifiedTime": f.get("modifiedTime"),
                "md5Checksum": f.get("md5Checksum"),
                "version": f.get("version"),
            }
        )


    logger.info("📄 Collected %d Drive documents with extracted text", len(docs))
    return docs


# ------------------------------------------------------
# Notion
# ------------------------------------------------------

def notion_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def crawl_notion_children(page_id: str, api_key: str) -> List[Dict]:
    """
    Fetch all child pages under a parent Notion page.
    Returns a list of page objects (id, properties, etc.).
    """
    logger.info("📘 Fetching Notion child pages...")
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    results = []
    start_cursor = None

    while True:
        params = {}
        if start_cursor:
            params["start_cursor"] = start_cursor

        resp = requests.get(url, headers=notion_headers(api_key), params=params)
        resp.raise_for_status()
        data = resp.json()

        for block in data.get("results", []):
            if block.get("type") == "child_page":
                results.append(block)

        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")

    logger.info(f"📘 Found {len(results)} Notion child pages")
    return results


def fetch_notion_page_text(page_id: str, api_key: str) -> str:
    """
    Fetch all blocks of a Notion page and return concatenated plain text.
    """
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    texts = []
    start_cursor = None

    while True:
        params = {}
        if start_cursor:
            params["start_cursor"] = start_cursor

        resp = requests.get(url, headers=notion_headers(api_key), params=params)
        resp.raise_for_status()
        data = resp.json()

        for block in data.get("results", []):
            block_type = block.get("type")
            if block_type in ("paragraph", "heading_1", "heading_2", "heading_3"):
                rich = block.get(block_type, {}).get("rich_text", [])
                content = "".join([r.get("plain_text", "") for r in rich])
                texts.append(content)
            # you can extend for bulleted_list_item, numbered_list_item, etc.

        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")

    return "\n".join(t for t in texts if t)


def crawl_notion(parent_page_id: str, api_key: str) -> List[Dict]:
    """
    Returns documents:
      - source: "notion"
      - doc_id
      - name
      - text
    """
    child_pages = crawl_notion_children(parent_page_id, api_key)
    docs = []

    for block in child_pages:
        page_id = block.get("id")
        name = block.get("child_page", {}).get("title", "Untitled")
        logger.info(f"📘 Notion page: {name} ({page_id})")

        text = fetch_notion_page_text(page_id, api_key)
        docs.append(
            {
                "source": "notion",
                "doc_id": page_id,
                "name": name,
                "text": text,
                "parent_page_id": parent_page_id,  # 👈 the top-level page we crawled
            }
        )


    return docs


# ------------------------------------------------------
# Confluence
# ------------------------------------------------------

def crawl_confluence_children(
    parent_page_id: str,
    base_url: str,
    username: str,
    api_token: str,
) -> List[Dict]:
    """
    Fetch direct child pages from Confluence for a given parent page.
    """
    logger.info("📄 Fetching Confluence child pages...")

    url = f"{base_url}/rest/api/content/{parent_page_id}/child/page"
    auth = (username, api_token)
    params = {"limit": 100}  # adjust if needed

    resp = requests.get(url, auth=auth, params=params)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for p in data.get("results", []):
        results.append(
            {
                "id": p.get("id"),
                "title": p.get("title"),
            }
        )

    logger.info(f"📄 Found {len(results)} Confluence child pages")
    return results


def fetch_confluence_page_html(
    page_id: str,
    base_url: str,
    username: str,
    api_token: str,
) -> str:
    """
    Fetch Confluence page content (storage format) and return HTML string.
    """
    url = f"{base_url}/rest/api/content/{page_id}"
    auth = (username, api_token)
    params = {"expand": "body.storage"}

    resp = requests.get(url, auth=auth, params=params)
    resp.raise_for_status()
    data = resp.json()

    html = (
        data.get("body", {})
        .get("storage", {})
        .get("value", "")
    )
    return html


def crawl_confluence(
    parent_page_id: str,
    base_url: str,
    username: str,
    api_token: str,
) -> List[Dict]:
    """
    Returns:
      - source: "confluence"
      - doc_id
      - name
      - text
    """
    child_pages = crawl_confluence_children(
        parent_page_id,
        base_url,
        username,
        api_token,
    )
    docs = []

    for page in child_pages:
        page_id = page["id"]
        title = page["title"]
        logger.info(f"📄 Confluence page: {title} ({page_id})")

        html = fetch_confluence_page_html(
            page_id, base_url, username, api_token
        )
        text = strip_html(html)
        docs.append(
            {
                "source": "confluence",
                "doc_id": page_id,
                "name": title,
                "text": text,
                "confluence_parent_id": parent_page_id,
            }
        )

    return docs


# ------------------------------------------------------
# Embeddings — multi-provider with fallback
# ------------------------------------------------------

class EmbeddingQuotaError(Exception):
    """Raised when the embedding provider reports insufficient quota."""
    pass


def _build_single_provider_embedder(provider: str, cfg) -> Optional[Callable[[List[str]], List[List[float]]]]:
    """
    Build an embedder for a single provider.
    Returns a function(chunks) -> List[embedding] or None if not configured/available.
    """
    provider = (provider or "").lower()
    doc_rag = cfg.get("document_rag", {})
    llm_cfg = cfg.get("llm", {})
    primary_llm = llm_cfg.get("primary", {})

    model_name = doc_rag.get("embedding_model", "text-embedding-3-small")

    # ---- OpenAI ----
    if provider == "openai":
        #api_key = primary_llm.get("api_key")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("⚠ No OpenAI API key configured. Skipping 'openai' embedding provider.")
            return None

        client = OpenAI(api_key=api_key)

        def embedder(chunks: List[str]) -> List[List[float]]:
            if not chunks:
                return []
            try:
                resp = client.embeddings.create(
                    model=model_name,
                    input=chunks,
                    timeout=60,
                )
                return [d.embedding for d in resp.data]
            except Exception as e:
                msg = str(e)
                if "insufficient_quota" in msg or "You exceeded your current quota" in msg:
                    # paid tier exhausted
                    raise EmbeddingQuotaError(msg)
                raise

        return embedder

    # ---- Azure OpenAI (stub for future) ----
    if provider == "azure_openai":
        logger.warning("⚠ 'azure_openai' provider requested but not yet implemented. Skipping.")
        return None

    # ---- Vertex AI (stub for future) ----
    if provider == "vertex":
        logger.warning("⚠ 'vertex' provider requested but not yet implemented. Skipping.")
        return None

    # ---- HuggingFace / Local sentence-transformers (free, local CPU) ----
    if provider in ("huggingface", "local"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning(
                "⚠ sentence-transformers not installed. "
                "Run `pip install sentence-transformers` to enable the '%s' provider.",
                provider,
            )
            return None

        hf_model_name = doc_rag.get(
            "huggingface_model",
            "sentence-transformers/all-MiniLM-L6-v2",
        )
        logger.info("   ℹ Using local HuggingFace model: %s", hf_model_name)
        model = SentenceTransformer(hf_model_name)

        def embedder(chunks: List[str]) -> List[List[float]]:
            if not chunks:
                return []
            embeddings = model.encode(chunks, convert_to_numpy=False)
            return [emb.tolist() if hasattr(emb, "tolist") else list(emb) for emb in embeddings]

        return embedder

    logger.warning("⚠ Unknown embedding provider '%s'. Skipping.", provider)
    return None


def build_embedder(cfg):
    """
    Build an embedder(chunks) -> List[List[float]] with optional automatic fallback.

    Config:
      - document_rag.embedding_provider:
          "openai" | "vertex" | "azure_openai" | "huggingface" | "local" | "auto"
      - document_rag.embedding_fallback_order (optional, used when provider == "auto"):
          e.g. ["openai", "azure_openai", "vertex", "huggingface", "local"]
    """
    doc_rag = cfg.get("document_rag", {})
    provider_mode = doc_rag.get("embedding_provider", "openai")
    fallback_order = doc_rag.get("embedding_fallback_order")

    # Single provider mode
    if provider_mode != "auto":
        embedder = _build_single_provider_embedder(provider_mode, cfg)
        if embedder is None:
            raise ValueError(
                f"❌ Embedding provider '{provider_mode}' is not properly configured. "
                "Please check your config and credentials."
            )
        logger.info("   ℹ Using single embedding provider: %s", provider_mode)
        return embedder

    # Auto mode with fallback chain
    default_chain = ["openai", "azure_openai", "vertex", "huggingface", "local"]
    providers_chain = fallback_order or default_chain

    provider_fns = []
    for p_name in providers_chain:
        fn = _build_single_provider_embedder(p_name, cfg)
        if fn is not None:
            provider_fns.append((p_name, fn))

    if not provider_fns:
        raise ValueError(
            "❌ No embedding providers are available in 'auto' mode. "
            "Please configure at least one provider (e.g., OpenAI API key or local HuggingFace model)."
        )

    logger.info(
        "   ℹ Auto embedding mode enabled. Provider order: %s",
        " -> ".join([name for name, _ in provider_fns]),
    )

    def multi_embedder(chunks: List[str]) -> List[List[float]]:
        last_err = None
        for name, fn in provider_fns:
            try:
                logger.info("   ➤ [Embeddings] Trying provider '%s' ...", name)
                return fn(chunks)
            except EmbeddingQuotaError as e:
                logger.warning(
                    "   ⚠ Provider '%s' quota exhausted (%s). Trying next provider in chain...",
                    name,
                    e,
                )
                last_err = e
                continue
            except Exception as e:
                logger.error(
                    "   ❌ Provider '%s' failed with error: %s. Trying next provider (if any)...",
                    name,
                    e,
                )
                last_err = e
                continue

        if last_err is None:
            raise RuntimeError("All embedding providers failed for unknown reasons.")
        if isinstance(last_err, EmbeddingQuotaError):
            raise last_err
        raise RuntimeError(f"All embedding providers failed. Last error: {last_err}")

    return multi_embedder


# ------------------------------------------------------
# Pinecone
# ------------------------------------------------------

def load_pinecone_index(api_key: str, index_name: str):
    """
    Return (index, dimension) for the given Pinecone index.
    """
    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    # Describe the index to get the dimension
    try:
        desc = pc.describe_index(index_name)
        dim = desc.dimension
    except Exception as e:
        logger.warning(
            "⚠ Could not determine index dimension from Pinecone. "
            "Defaulting to None. Original error: %s",
            e,
        )
        dim = None

    return index, dim


# ------------------------------------------------------
# Main Sync Logic
# ------------------------------------------------------

def sync_documents(config_path: str, source: str = "all", incremental: bool = False, force: bool = False):
    cfg = load_json(config_path)

    client_cfg = cfg.get("client", {})

    # Make document_visibility available to classify_visibility()
    global raw_cfg
    raw_cfg = client_cfg

    doc_sources = client_cfg.get("doc_sources", {}) or {}

    # ---- Drive roots (can be single string or list) ----
    drive_ids = doc_sources.get("google_drive_folder_ids")
    if isinstance(drive_ids, str):
        drive_ids = [drive_ids]
    elif drive_ids is None:
        # Backward-compatible single key
        single_drive = doc_sources.get("google_drive_folder_id")
        drive_ids = [single_drive] if single_drive else []

    # ---- Notion roots (can be single string or list) ----
    notion_ids = doc_sources.get("notion_parent_page_ids")
    if isinstance(notion_ids, str):
        notion_ids = [notion_ids]
    elif notion_ids is None:
        single_notion = doc_sources.get("notion_parent_page_id")
        notion_ids = [single_notion] if single_notion else []

    # ---- Confluence (single as before) ----
    conf_id = doc_sources.get("confluence_parent_page_id")

    #creds = client_cfg.get("credentials", {})
    integrations = cfg.get("integrations", {}) or {}
    conf_cfg = integrations.get("confluence", {}) or {}

    # Document RAG settings
    doc_rag = cfg.get("document_rag", {})
    
    provider_mode = doc_rag.get("embedding_provider", "openai")
    hf_model = doc_rag.get("huggingface_model")

    logger.info("Embedding provider: %s", provider_mode)
    if provider_mode in ("huggingface", "local"):
        logger.info("HF model: %s", hf_model)
    else:
        logger.info("Embedding model: %s", doc_rag.get("embedding_model"))

    pinecone_index_name = doc_rag.get("index_name")

    if not pinecone_index_name:
        raise ValueError("document_rag.index_name is missing!")

    logger.info(f"Using Pinecone index: {pinecone_index_name}")

    # Extract credentials
    # Extract credentials with resilient fallbacks
    sa_candidates = [
        cfg.get("gcp", {}).get("service_account_key_path"),
        cfg.get("gcp", {}).get("key_file"),
        "keys/client-service-account.json",
        "scaffold/keys/client-service-account.json"
    ]
    sa_json = None
    for cand in sa_candidates:
        if cand and os.path.exists(cand):
            sa_json = cand
            break

    notion_key  = os.getenv("NOTION_API_KEY")
    conf_base   = conf_cfg.get("base_url")
    conf_user   = conf_cfg.get("username")
    conf_token  = os.getenv("CONFLUENCE_API_TOKEN")
    pinecone_key = os.getenv("PINECONE_API_KEY")
    openai_key   = os.getenv("OPENAI_API_KEY")

    if not pinecone_key:
        try:
            import subprocess
            pinecone_key = subprocess.check_output(
                "gcloud secrets versions access latest --secret=PINECONE_API_KEY --project=diamante-diad",
                shell=True
            ).decode().strip()
        except Exception:
            pass

    # Load Pinecone index and embedding provider(s)
    index, index_dim = load_pinecone_index(pinecone_key, pinecone_index_name)
    embedder = build_embedder(cfg)

    if index_dim is not None:
        logger.info("   ℹ Pinecone index `%s` dimension: %s", pinecone_index_name, index_dim)
    else:
        logger.warning("⚠ Pinecone index dimension unknown; embeddings will not be resized.")

    # Incremental state cache
    state_file = Path("logs/docs_sync_state.json")
    sync_state = {}
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                sync_state = json.load(f)
        except Exception:
            sync_state = {}

    all_docs = []
    source = (source or "all").lower()

    # ---- Drive: crawl ALL configured folders if source matches ----
    if source in ("all", "gdrive", "drive"):
        if sa_json:
            for drive_id in drive_ids:
                if not drive_id:
                    continue
                try:
                    logger.info(f"🔍 Crawling Google Drive folder: {drive_id}")
                    all_docs.extend(crawl_drive(drive_id, sa_json))
                except HttpError as e:
                    msg = str(e)
                    logger.warning("⚠ Google Drive crawl failed for folder %s: %s", drive_id, msg)
                    if "accessNotConfigured" in msg:
                        logger.warning(
                            "⚠ Google Drive API is not enabled or not configured for this project. "
                            "Enable it in GCP Console or remove 'google_drive_folder_id(s)' from config to skip Drive."
                        )
                except Exception as e:
                    logger.warning("⚠ Google Drive crawl failed for folder %s with unexpected error: %s", drive_id, e)
        else:
            logger.info("ℹ Skipping Google Drive (no SA key found).")

    # ---- Notion: crawl ALL configured parent pages if source matches ----
    if source in ("all", "notion"):
        if notion_key:
            for notion_id in notion_ids:
                if not notion_id:
                    continue
                logger.info(f"🔍 Crawling Notion parent page: {notion_id}")
                all_docs.extend(crawl_notion(notion_id, notion_key))

    # ---- Confluence: crawl if source matches ----
    if source in ("all", "confluence"):
        if conf_id and conf_base and conf_user and conf_token:
            logger.info(f"🔍 Crawling Confluence under parent page: {conf_id}")
            all_docs.extend(crawl_confluence(conf_id, conf_base, conf_user, conf_token))


    # --------------------------------------------
    # PROCESS DOCUMENTS
    # --------------------------------------------
    logger.info(f"🚀 Starting embedding + upsert for {len(all_docs)} documents...")

    for idx, d in enumerate(all_docs, start=1):
        logger.info(f"\n📄 Document {idx}/{len(all_docs)}")
        logger.info(f"   Source : {d['source']}")
        logger.info(f"   Name   : {d['name']}")
        logger.info(f"   Doc ID : {d['doc_id']}")

        # Decide visibility for this document
        source = d["source"]

        drive_folder_id = d.get("folder_id") if source == "gdrive" else None
        notion_parent_id = d.get("parent_page_id") if source == "notion" else None

        visibility = classify_visibility(
            source=source,
            drive_folder_id=drive_folder_id,
            notion_page_id=notion_parent_id,
            confluence_space_key=None,
        )

        logger.info(f"   Visibility: {visibility}")

        # Check incremental cache
        import hashlib
        doc_hash = hashlib.sha256((d.get("text") or "").encode("utf-8")).hexdigest()
        file_version = d.get("md5Checksum") or d.get("modifiedTime") or d.get("version")
        state_key = f"{d['source']}_{d['doc_id']}"
        prev_state = sync_state.get(state_key, {})
        if incremental and not force:
            if prev_state.get("hash") == doc_hash or (file_version and prev_state.get("version") == file_version):
                logger.info(f"   ⏩ [Incremental] Document unchanged ({d['name']}). Skipping.")
                continue
        chunk_size = int(doc_rag.get("chunk_tokens", 300)) * 4  # rough proxy: 1 token ~ 4 chars
        overlap = int(doc_rag.get("chunk_overlap", 50)) * 4

        chunks = chunk_text(d["text"], max_chunk_size=chunk_size, overlap=overlap)


        logger.info(f"   ➤ Total chunks: {len(chunks)}")

        if len(chunks) == 0:
            logger.warning(f"   ⚠ Skipping document (no text): {d['name']}")
            continue

        # 2️⃣ Embed chunks (with provider fallback)
        try:
            provider_mode_lc = (provider_mode or "openai").lower()
            hf_model_name = doc_rag.get("huggingface_model", "sentence-transformers/all-MiniLM-L6-v2")
            openai_model_name = doc_rag.get("embedding_model", "text-embedding-3-small")

            if provider_mode_lc in ("huggingface", "local"):
                logger.info("   ➤ Embedding %d chunks using HF model: %s ...", len(chunks), hf_model_name)
            else:
                logger.info("   ➤ Embedding %d chunks using OpenAI model: %s ...", len(chunks), openai_model_name)

            vectors = embedder(chunks)
            if index_dim is not None and len(vectors) > 0:
                if len(vectors[0]) != index_dim:
                    raise ValueError(
                        f"Embedding dimension {len(vectors[0])} does not match Pinecone index dimension {index_dim}. "
                        f"Fix by using the correct index_name/dimension in config (e.g., 384 for HF MiniLM)."
                    )
            logger.info("   ✔ Embedding completed.")
        except EmbeddingQuotaError as e:
            logger.error(f"   ❌ Embedding FAILED for document {d['name']}: {e}")
            logger.error("   ❌ Detected insufficient embedding quota across all providers. Aborting remaining documents.")
            break
        except Exception as e:
            logger.error(f"   ❌ Embedding FAILED for document {d['name']}: {e}")
            continue

        # 3️⃣ Upsert to Pinecone
        try:
            logger.info(
                f"   ➤ Upserting {len(vectors)} vectors to Pinecone index `{pinecone_index_name}` ..."
            )

            # Namespace per source so Pinecone can report counts per source
            namespace = (d.get("source") or "__default__").lower()
            namespace = {
                "drive": "gdrive",
                "gdrive": "gdrive",
                "notion": "notion",
                "confluence": "confluence",
            }.get(namespace, "__default__")

            payload = []
            for i, (chunk, emb) in enumerate(zip(chunks, vectors)):
                payload.append(
                    {
                        "id": f"{d['source']}_{d['doc_id']}_{i}",
                        "values": emb,
                        "metadata": {
                            "source": d["source"],
                            "doc_id": d["doc_id"],
                            "doc_name": d.get("name"),
                            "root_id": d.get("folder_id") or d.get("parent_page_id") or d.get("confluence_parent_id"),
                            "client_project_id": client_cfg.get("project_id"),
                            "chunk": i,
                            "text": chunk[:300],   # partial text
                            "visibility": visibility,
                        },
                    }
                )
            logger.info(f"   ➤ Namespace: {namespace}")
            index.upsert(vectors=payload, namespace=namespace)
            logger.info(f"   ✔ Upsert completed for {d['name']}")
            sync_state[state_key] = {
                "hash": doc_hash,
                "version": file_version,
                "last_synced": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "name": d.get("name"),
                "source": d["source"]
            }
        except Exception as e:
            logger.error(f"   ❌ Pinecone upsert FAILED for {d['name']}: {e}")
            continue

    state_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(sync_state, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist sync state cache: {e}")

    logger.info("\n🎉 ALL DOCUMENTS PROCESSED (or aborted on quota).")
    print_index_counts(index)


# ------------------------------------------------------
# CLI
# ------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="DIAD Document Sync to Pinecone")
    p.add_argument("--config", default="config/client_rawdata.json", help="Path to config JSON")
    p.add_argument("--source", default="all", choices=["all", "gdrive", "drive", "notion", "confluence"], help="Filter sync to a specific source")
    p.add_argument("--incremental", action="store_true", default=True, help="Only embed new or modified documents (default: True)")
    p.add_argument("--force", action="store_true", default=False, help="Force re-indexing of all documents")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sync_documents(args.config, source=args.source, incremental=args.incremental, force=args.force)

