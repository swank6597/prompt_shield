"""End-to-end suite runner: Presidio -> pre-classifier -> ECI/LLM -> policy.

Replicates routes.py::scan_prompt() stage for stage, minus API-key auth and the
audit-log write, so it can be run from the command line without a live server and
without leaving rows in audit_log.db.

MAKES REAL LLM CALLS for any case the pre-classifier routes to review. Use
--only to limit the run; the default is the 15 human-authored baseline cases,
which is what plan task 6.3 measured (14/15, with #5 failing because Groq
returned 6 `reasoning` bullets against ai/schema.json's maxItems: 5 and fell to
_fallback_result - unrelated to any threshold).

Pass criteria, from the suite's Expected column mapped through
routes.DECISION_TO_STATUS:
    BLOCK        -> status must be BLOCK
    ALLOW        -> status must be SAFE
    ALLOW / WARN -> status may be SAFE or SANITIZE

Usage:
    backend/venv/Scripts/python.exe scripts/calibration/run_suite_e2e.py \
        [--cases suite_cases.json] [--only human|all|1,2,3] [--sleep 2.5]
"""

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parents[1] / "backend"
for _d in (_BACKEND, _BACKEND / "ai", _BACKEND / "policy"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import config  # noqa: E402
from presidio.presidio_engine import analyze_text  # noqa: E402
from pre_classifier import pre_classify  # noqa: E402
from semantic_classifier import classify as classify_context  # noqa: E402
from policy_engine import decide as decide_policy  # noqa: E402

DECISION_TO_STATUS = {
    "ALLOW": "SAFE",
    "WARN": "SANITIZE",
    "MASK": "SANITIZE",
    "BLOCK": "BLOCK",
}

ACCEPTED = {
    "BLOCK": {"BLOCK"},
    "ALLOW": {"SAFE"},
    "ALLOW / WARN": {"SAFE", "SANITIZE"},
}


def scan(prompt: str) -> dict:
    """One pass of the real pipeline. Mirrors routes.py::scan_prompt()."""
    presidio = analyze_text(prompt)
    pre = pre_classify(prompt, presidio["maskedText"], presidio)

    if not pre["needs_llm"]:
        eci = pre["pre_eci"]
        llm_used = False
    else:
        semantic_chunks = None
        sr = pre.get("semantic_result")
        if sr and isinstance(sr, dict):
            semantic_chunks = sr.get("top_chunks") or None
        eci = classify_context(
            presidio["maskedText"],
            entity_count=presidio["entityCount"],
            semantic_chunks=semantic_chunks,
        )
        llm_used = True

    eci = dict(eci)
    provider = eci.pop("_llm_provider", None)
    model = eci.pop("_llm_model", None)

    detection = {
        "entityCount": presidio["entityCount"],
        "entityTypes": [e["entity_type"] for e in presidio["entities"]],
    }
    policy = decide_policy(detection, eci)
    status = DECISION_TO_STATUS.get(policy["decision"], "SANITIZE")

    fallback = (eci.get("confidence") == 0.0
                and any("fallback" in str(r).lower() for r in eci.get("reasoning", [])))

    return {
        "status": status,
        "decision": policy["decision"],
        "risk": policy["riskScore"],
        "rules": policy["matchedRules"],
        "path": pre["decision_path"],
        "hybrid": pre.get("hybrid_score"),
        "llm_used": llm_used,
        "llm": f"{provider}/{model}" if provider else None,
        "fallback": fallback,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", default=str(_HERE / "suite_cases.json"))
    ap.add_argument("--only", default="human",
                    help="'human', 'all', or a comma-separated list of case numbers")
    ap.add_argument("--sleep", type=float, default=2.5,
                    help="seconds between LLM calls (Groq free tier ~30 req/min)")
    ap.add_argument("--out", default=str(_HERE / "e2e_results.json"))
    args = ap.parse_args(argv)

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8-sig"))
    if args.only == "human":
        cases = [c for c in cases if c["human"]]
    elif args.only != "all":
        wanted = {int(x) for x in args.only.split(",") if x.strip()}
        cases = [c for c in cases if c["num"] in wanted]

    print(f"config: HYBRID_PUBLIC={config.HYBRID_PUBLIC_THRESHOLD} "
          f"HYBRID_ENTERPRISE={config.HYBRID_ENTERPRISE_THRESHOLD} "
          f"TFIDF=[{config.TFIDF_PUBLIC_THRESHOLD}, {config.TFIDF_ENTERPRISE_THRESHOLD}) "
          f"K={config.LEXICAL_SATURATION_K}")
    print(f"llm: strategy={config.LLM_STRATEGY} provider={config.LLM_CLOUD_PROVIDER}")
    print(f"running {len(cases)} case(s)\n")

    results = []
    passed = 0
    for i, c in enumerate(cases):
        r = scan(c["text"])
        ok = r["status"] in ACCEPTED.get(c["expected"], set())
        passed += ok
        r.update({"id": c["id"], "num": c["num"], "expected": c["expected"],
                  "human": c["human"], "pass": ok, "text": c["text"]})
        results.append(r)
        print(f"{c['id']:5s} exp={c['expected']:12s} got={r['status']:9s} "
              f"{'PASS' if ok else 'FAIL'}  path={r['path']:32s} "
              f"risk={r['risk']:3d} llm={r['llm'] or '-'}"
              f"{'  [FALLBACK]' if r['fallback'] else ''}")
        if r["llm_used"] and i < len(cases) - 1 and args.sleep > 0:
            time.sleep(args.sleep)

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(f"\n{passed}/{len(results)} pass")
    fails = [r for r in results if not r["pass"]]
    if fails:
        print("failures:")
        for r in fails:
            print(f"  {r['id']} expected {r['expected']}, got {r['status']} "
                  f"(decision={r['decision']}, rules={r['rules']}, "
                  f"fallback={r['fallback']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
