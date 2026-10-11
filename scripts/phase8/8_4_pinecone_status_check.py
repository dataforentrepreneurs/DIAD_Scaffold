# 8_4_pinecone_status_check.py
#!/usr/bin/env python3

from pinecone import Pinecone
import os

from dotenv import load_dotenv
import os

load_dotenv(".env.local")

# pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
# index = pc.Index("diad-docs-index")

# stats = index.describe_index_stats()
# print(stats)

# import os
# from pinecone import Pinecone

INDEX = os.environ.get("PINECONE_INDEX", "diad-docs-index")

pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index = pc.Index(INDEX)

stats = index.describe_index_stats()
print(stats)

dim = stats["dimension"]

doc_ids_by_source = {}

for namespace in stats.get("namespaces", {}):
    res = index.query(
        vector=[0.0] * dim,
        top_k=10000,                  # adjust if needed
        include_metadata=True,
        namespace=namespace
    )

    for m in res["matches"]:
        md = m.get("metadata", {})
        doc_id = md.get("doc_id")
        source = md.get("source", namespace)

        if not doc_id:
            continue

        doc_ids_by_source.setdefault(source, set()).add(doc_id)

print("📄 Document counts:")
for src, ids in doc_ids_by_source.items():
    print(f"  - {src}: {len(ids)} documents")
