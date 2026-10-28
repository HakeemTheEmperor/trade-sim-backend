// Fixed-rate load on the trade endpoints.
//
//   k6 run -e RATE=100 -e DURATION=60s loadtest/trade.js
//
// constant-arrival-rate starts RATE requests a second no matter how slowly the
// server answers, so latency shows up as latency (and, past saturation, as
// dropped iterations) instead of quietly lowering the offered load, which is
// what a fixed number of virtual users would do.
//
// Each iteration picks the next user in turn. The first pass through the users
// buys one share, the second sells it, and so on, so every user trades one share
// of one symbol back and forth. With U users the per-user rate is RATE/U; the buy
// route allows 30 a minute per user, so keep RATE/U comfortably under 0.5.
import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';
import { SharedArray } from 'k6/data';

const seed = new SharedArray('seed', () => [JSON.parse(open('./users.json'))])[0];
const BASE = __ENV.BASE_URL || 'http://localhost:5001';
const RATE = parseInt(__ENV.RATE || '100');

export const options = {
  scenarios: {
    trades: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: __ENV.DURATION || '60s',
      preAllocatedVUs: Math.max(50, Math.ceil(RATE / 2)),
      maxVUs: 2000,
    },
  },
  thresholds: {
    'http_req_duration{kind:trade}': ['p(95)<500'],
    'checks{check:trade ok}': ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const i = exec.scenario.iterationInTest;
  const n = seed.users.length;
  const user = seed.users[i % n];
  const side = Math.floor(i / n) % 2 === 0 ? 'buy' : 'sell';
  const symbol = seed.symbols[(i % n) % seed.symbols.length];

  const response = http.post(
    `${BASE}/api/v1/stocks/${side}`,
    JSON.stringify({ symbol, quantity: 1, wallet_id: user.wallet_id }),
    {
      headers: {
        'Content-Type': 'application/json',
        Cookie: `access_token_cookie=${user.token}`,
        'X-CSRF-TOKEN': user.csrf,
      },
      tags: { kind: 'trade' },
    },
  );
  const ok = check(response, { 'trade ok': (r) => r.status === 200 }, { check: 'trade ok' });
  if (!ok && __ENV.DEBUG) {
    console.log(`${side} ${symbol} -> ${response.status} ${String(response.body).slice(0, 160)}`);
  }
}
