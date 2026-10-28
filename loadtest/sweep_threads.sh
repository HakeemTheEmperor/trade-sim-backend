#!/bin/sh
# Compare gunicorn thread counts under the same fixed-rate load.
#   loadtest/sweep_threads.sh "4 8 16 32" "50 60 70"
# For each thread count: recreate the app container with GUNICORN_THREADS set
# (the connection pool follows it), then run loadtest/run.sh with a fresh
# database per run, and keep the summaries in loadtest/results/threads_<n>/.
cd "$(dirname "$0")/.." || exit 1
COMPOSE="docker compose -f loadtest/docker-compose.loadtest.yml"
THREADS="${1:-4 8 16 32}"
RATES="${2:-50 60 70}"
for t in $THREADS; do
  echo "######## GUNICORN_THREADS=$t"
  GUNICORN_THREADS="$t" $COMPOSE up -d --force-recreate --wait app >/dev/null 2>&1 || { echo "app failed to start"; exit 1; }
  sleep 20
  mkdir -p "loadtest/results/threads_$t"
  RESEED=1 PAUSE="${PAUSE:-45}" sh loadtest/run.sh $RATES
  for r in $RATES; do cp "loadtest/results/rate_$r.json" "loadtest/results/threads_$t/"; done
done
