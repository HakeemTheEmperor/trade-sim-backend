#!/bin/sh
# Stepped fixed-rate runs against a seeded stack; one summary JSON per rate in
# loadtest/results/. Usage: loadtest/run.sh 10 20 30 40
#
# Each run is separated by a pause so the server drains any backlog and the
# per-user rate-limit windows (60s) from the previous run do not carry over.
cd "$(dirname "$0")/.." || exit 1
mkdir -p loadtest/results
DURATION="${DURATION:-60s}"
for rate in "$@"; do
  echo "== ${rate} requests/s for ${DURATION}"
  # RESEED=1 starts every run from the same freshly seeded database, so earlier
  # runs' trades and table growth cannot affect the next one.
  if [ -n "$RESEED" ]; then python loadtest/seed.py >/dev/null 2>&1; fi
  k6 run -e RATE="$rate" -e DURATION="$DURATION" \
    --summary-export "loadtest/results/rate_${rate}.json" loadtest/trade.js >/dev/null 2>&1
  sleep "${PAUSE:-45}"
done
python loadtest/summarize.py "$@"
