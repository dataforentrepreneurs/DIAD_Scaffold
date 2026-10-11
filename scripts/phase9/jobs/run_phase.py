# jobs/run_phase.py
# Generic runner for Cloud Run Jobs containers.
# Usage (ENTRYPOINT): python jobs/run_phase.py --script <path> --args ...

import argparse
import subprocess
import sys

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--script", required=True, help="Path to the DIAD script to run")
    p.add_argument("--args", nargs=argparse.REMAINDER, default=[], help="Arguments passed to the target script")
    ns = p.parse_args()

    cmd = [sys.executable, ns.script] + (ns.args or [])
    print("Running:", " ".join(cmd), flush=True)
    return subprocess.call(cmd)

if __name__ == "__main__":
    raise SystemExit(main())
