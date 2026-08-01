"""Diff two scored-suite runs by decision path, so a proposed config change can
be shown to move exactly the cases claimed and no others.

Usage:
    python scripts/calibration/diff_routing.py before.json after.json
"""

import json
import sys
from pathlib import Path

NO_LLM = {"trivial", "hard_block", "pii_only", "general_knowledge",
          "semantic_confirmed_public"}


def load(p):
    return {r["id"]: r for r in json.loads(Path(p).read_text(encoding="utf-8-sig"))}


def main() -> int:
    a, b = load(sys.argv[1]), load(sys.argv[2])
    moved = []
    for cid in sorted(a, key=lambda x: int(x.lstrip("#"))):
        ra, rb = a[cid], b[cid]
        if ra["path"] != rb["path"]:
            moved.append((cid, ra, rb))

    print(f"cases: {len(a)}   path changes: {len(moved)}")
    for cid, ra, rb in moved:
        print(f"  {cid:5s} {'HUM' if ra['human'] else 'gen'} {ra['expected']:12s} "
              f"{ra['path']} -> {rb['path']}"
              f"   (llm {ra['needs_llm']} -> {rb['needs_llm']})")

    human_moved = [m for m in moved if m[1]["human"]]
    print(f"\nhuman-authored cases whose routing changed: {len(human_moved)}"
          f"{'  ' + str([m[0] for m in human_moved]) if human_moved else '  (none)'}")

    for label, d in (("before", a), ("after", b)):
        llm = [r for r in d.values() if r["path"] not in NO_LLM]
        blk_nollm = [r for r in d.values()
                     if r["expected"] == "BLOCK" and r["path"] not in NO_LLM]
        blk_skipped = [r for r in d.values()
                       if r["expected"] == "BLOCK" and r["path"] in NO_LLM
                       and r["path"] not in ("hard_block", "trivial")]
        print(f"{label:7s}: LLM calls {len(llm)}/{len(d)}   "
              f"BLOCK reaching LLM {len(blk_nollm)}   "
              f"BLOCK silently skipped (non-hard_block) {len(blk_skipped)} "
              f"{[r['id'] for r in blk_skipped]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
