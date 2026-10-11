#!/usr/bin/env python3
"""
8_3_query_docs.py
=======================

DIAD Phase 8.2 – Query Docs (Notion + Confluence + Drive via Pinecone)

Usage examples:

  # Basic
  python scripts/phase8/8_3_query_docs.py --query "What are our Q1 OKRs?"

  # With explicit config + top_k
python scripts/phase8/8_3_query_docs.py `
  --config config/client_rawdata.json `
  --query "How does the external chatbot work?" `
  --top-k 5

"""

from dotenv import load_dotenv
load_dotenv(".env.local")

import argparse
import json
import logging
import os
from typing import Dict, List, Optional, Callable

from openai import OpenAI
from pinecone import Pinecone


# ------------------------------------------------------
# Logging
# ------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("phase8_query_docs")


# ------------------------------------------------------
# Utilities
# ------------------------------------------------------

def _get_matches(res):
    # Pinecone client may return object or dict
    return getattr(res, "matches", None) or res.get("matches", []) or []


def _get_score(m):
    return getattr(m, "score", None) or m.get("score", 0.0) or 0.0

def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def adjust_vector_dim(vec: List[float], target_dim: Optional[int]) -> List[float]:
    """
    Ensure the vector has exactly target_dim dimensions.

    - If target_dim is None, return vec unchanged.
    - If len(vec) < target_dim, pad with zeros.
    - If len(vec) > target_dim, truncate.
    """
    if target_dim is None:
        return vec

    n = len(vec)
    if n == target_dim:
        return vec
    if n < target_dim:
        return vec + [0.0] * (target_dim - n)
    # n > target_dim
    return vec[:target_dim]


# ------------------------------------------------------
# Embeddings — multi-provider with fallback
# (same pattern as 8_1_sync_docs_to_pinecone.py)
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
    #primary_llm = llm_cfg.get("primary", {})

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
                    raise EmbeddingQuotaError(msg)
                raise

        return embedder

    # ---- Azure OpenAI (stub) ----
    if provider == "azure_openai":
        logger.warning("⚠ 'azure_openai' provider requested but not yet implemented. Skipping.")
        return None

    # ---- Vertex AI (stub) ----
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
# Query Logic
# ------------------------------------------------------

def query_docs(config_path: str, query: str, top_k: int):
    cfg = load_json(config_path)
    client_cfg = cfg.get("client", {})
    doc_rag = cfg.get("document_rag", {})
    #creds = client_cfg.get("credentials", {})

    pinecone_index_name = doc_rag.get("index_name")
    if not pinecone_index_name:
        raise ValueError("document_rag.index_name is missing in config!")

    #pinecone_key = creds.get("PINECONE_API_KEY")
    pinecone_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_key:
        raise ValueError("PINECONE_API_KEY missing from environment/.env.local")


    logger.info("Using Pinecone index: %s", pinecone_index_name)

    # Load index + embedder
    index, index_dim = load_pinecone_index(pinecone_key, pinecone_index_name)
    if index_dim is not None:
        logger.info("   ℹ Pinecone index dimension: %s", index_dim)

    embedder = build_embedder(cfg)
    
    # Namespaces to search (Phase 8 writes into these)
    namespaces = doc_rag.get("namespaces") or ["gdrive", "notion", "confluence"]


    logger.info("📥 Query: %s", query)

    # Embed query
    try:
        q_vec = embedder([query])[0]
    except Exception as e:
        logger.error("❌ Failed to embed query: %s", e)
        return

    q_vec_fixed = adjust_vector_dim(q_vec, index_dim)

    # Query Pinecone
    logger.info(f"Query embedding length = {len(q_vec)}")

    logger.info("🔎 Querying Pinecone across namespaces=%s (top_k=%d each) ...", namespaces, top_k)

    all_matches = []
    for ns in namespaces:
        try:
            res = index.query(
                vector=q_vec_fixed,
                top_k=top_k,
                include_metadata=True,
                namespace=ns,
            )
            all_matches.extend(_get_matches(res))
        except Exception as e:
            logger.error("❌ Pinecone query failed for namespace '%s': %s", ns, e)

    # Merge + rank across namespaces
    all_matches.sort(key=_get_score, reverse=True)
    matches = all_matches[:top_k]

    if not matches:
        logger.info("No matches found.")
        return

    print("\n===== Top Matches =====\n")
    for rank, m in enumerate(matches, start=1):
        # Depending on client version, m may be an object or dict
        mid = getattr(m, "id", None) or m.get("id")
        score = getattr(m, "score", None) or m.get("score")
        meta = getattr(m, "metadata", None) or m.get("metadata", {}) or {}

        source = meta.get("source", "?")
        doc_id = meta.get("doc_id", "?")
        chunk_idx = meta.get("chunk", "?")
        text_snippet = meta.get("text", "")

        print(f"#{rank}  score={score:.4f}")
        print(f"   id      : {mid}")
        print(f"   source  : {source}")
        print(f"   doc_id  : {doc_id}")
        print(f"   chunk   : {chunk_idx}")
        print(f"   snippet : {text_snippet}")
        print("")


# ------------------------------------------------------
# CLI
# ------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--config",
        default="config/client_rawdata.json",
        help="Path to DIAD client config JSON (default: config/client_rawdata.json)",
    )
    p.add_argument(
        "--query",
        required=True,
        help="Natural language query to search over docs",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Number of results to return (default: document_rag.top_k or 5)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Load config once to determine default top_k if not passed
    cfg_tmp = load_json(args.config)
    default_top_k = cfg_tmp.get("document_rag", {}).get("top_k", 5)
    top_k = args.top_k or default_top_k

    query_docs(args.config, args.query, top_k)
