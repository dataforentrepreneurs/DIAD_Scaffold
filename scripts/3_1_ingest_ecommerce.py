
"""
Orchestrate Phase 3 ingest via separate scripts:
1) generate_seed.py
2) create_datasets_and_tables.py
3) upload_to_gcs.py
4) load_raw_and_transform.py
"""
import subprocess, sys, pathlib

BASE = pathlib.Path(__file__).parent / "phase3"

steps = [
    ("Generate seed",         [sys.executable, str(BASE / "generate_seed.py")]),
    ("Create datasets/tables",[sys.executable, str(BASE / "create_datasets_and_tables.py")]),
    ("Upload to GCS",         [sys.executable, str(BASE / "upload_to_gcs.py")]),
    ("Load RAW -> Canonical",  [sys.executable, str(BASE / "load_raw_and_transform.py")]),
]

for name, cmd in steps:
    print("\n=== STEP:", name, "===\n")
    rc = subprocess.call(cmd)
    if rc != 0:
        raise SystemExit(f"Step failed: {name} (exit {rc})")

print("\nAll Phase 3 steps completed successfully.")
