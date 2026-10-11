"""Resume la forma de los JSON en _raw/ (claves y primer elemento de cada lista)."""
import json
import sys
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "_raw"


def shape(v, depth=0):
    pad = "  " * depth
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, (dict, list)):
                n = len(x)
                print(f"{pad}{k}: {type(x).__name__}[{n}]")
                if depth < 3:
                    shape(x, depth + 1)
            else:
                print(f"{pad}{k}: {str(x)[:80]!r}")
    elif isinstance(v, list) and v:
        print(f"{pad}[0]:")
        shape(v[0], depth + 1)


pattern = sys.argv[1] if len(sys.argv) > 1 else "*"
for f in sorted(RAW.glob(pattern + ".json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    print(f"\n=== {f.name} ({d['status']})")
    shape(d["data"])
