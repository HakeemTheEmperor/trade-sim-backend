"""Print one row per rate from the k6 summary files that run.sh wrote."""
import json
import sys
from pathlib import Path

results = Path(__file__).resolve().parent / "results"
print(f"{'offered/s':>10} {'achieved/s':>11} {'dropped':>8} {'errors':>7} "
      f"{'median':>8} {'p95':>8} {'p99':>8} {'max':>8}")
for rate in sys.argv[1:]:
    path = results / f"rate_{rate}.json"
    if not path.exists():
        print(f"{rate:>10}  (no result)")
        continue
    m = json.loads(path.read_text())["metrics"]
    trade = m["http_req_duration{kind:trade}"]
    checks = m["checks{check:trade ok}"]
    total = checks["passes"] + checks["fails"]
    print(f"{rate:>10} {m['http_reqs']['rate']:>11.1f} {m.get('dropped_iterations', {}).get('count', 0):>8} "
          f"{checks['fails'] / total * 100 if total else 0:>6.1f}% "
          f"{trade['med']:>6.0f}ms {trade['p(95)']:>6.0f}ms {trade['p(99)']:>6.0f}ms {trade['max']:>6.0f}ms")
