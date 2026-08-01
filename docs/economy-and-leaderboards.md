# Economy and leaderboards

## Why the economy is closed

The app is a skill simulator: how much money you have in real life must not
affect how you rank. Three rules make that true, and all three are load-bearing —
remove any one and the leaderboard stops meaning anything.

1. **There is no way to add funds.** `DEPOSIT` and `WITHDRAWAL` exist in
   `TransactionCategory` but are referenced nowhere. Money enters an account
   exactly once, as the `100000.00` default on `Wallet.balance` at signup.
   Wallets created afterwards start at `0`.
2. **Transfers are own-wallet only.** `transfer_funds` checks that *both*
   wallets belong to the caller. Previously it validated only the sender, which
   made cross-user transfer the single hole in an otherwise closed economy — and
   with a leaderboard, an obvious collusion route (several accounts funnelling
   into one).
3. **Trading costs money.** See below. This is realism, but it also removes any
   incentive to grind a loop for free value.

Both transfer failures return the same message as an unknown wallet, so the
endpoint can't be used to probe which wallet ids exist or who owns them.

## Costs

Configured in [`app/utils/fees.py`](../app/utils/fees.py), env-overridable.

| Cost | Default | Applies to |
|---|---|---|
| `TRADE_HALF_SPREAD` | `0.0005` (5bp) | Buys execute above the quote, sells below |
| `FX_SPREAD` | `0.005` (0.5%) | Cross-currency transfers only |

**Why a spread rather than a commission.** Flat commissions are largely gone
from US retail — Robinhood, Schwab and Fidelity charge $0 on US stock trades.
The cost that is *always* present is the bid-ask spread: you buy at the ask and
sell at the bid, so you are slightly down the instant you own something. That is
the cost retail traders least understand, which makes it the one worth teaching.
5bp per side is wider than a real large-cap spread (a cent or two on a $200 share
is ~0.005%), but a real retail order also pays slippage and the market maker's
edge via payment for order flow — and a visible cost teaches better than an
invisible one.

**Why 0.5% on FX.** Currency conversion is where brokers and money apps make
serious margin, and it is invisible because it is baked into the rate shown.
Retail lands around 0.3–0.6% (Wise, Revolut) up to 1.5% (some brokers); only
near-wholesale desks go lower. Same-currency transfers convert nothing and are
therefore free, which matches the real world and keeps moving your own money
around costless.

**Percentage, not flat.** A flat minimum fee would exceed the proceeds of a
small sale and drive a balance negative. A percentage cannot.

**Where it's recorded.** `Transaction.fee` holds the cost, which is already
reflected in `total_value` rather than charged on top: a trade executes at the
spread-adjusted price and a transfer credits the converted amount less the
markup. Recording it separately means the app can *show* the cost
("market $200.00, you paid $200.10") instead of hiding it the way a real broker
does. `price_per_share` stores the executed price, not the quote.

**Two traps worth knowing about, both guarded:**

- Buy affordability is checked against the post-spread cost. Testing against the
  pre-spread figure lets a full-balance buy overdraw by exactly the spread.
- A sale whose proceeds round to zero is rejected. Crediting nothing while
  destroying the shares would be theft.

**Consequence:** the economy is deflationary. Money leaves on every trade and
never returns, so a user who churns can grind toward zero with no way back.
That's realistic, and it's the strongest argument for seasons — but if it turns
out to be common, a floor or a seasonal reset is the answer.

## Leaderboards

Friend boards only. There is no global board, by design: the shadow feature is
deliberately privacy-preserving (`is_shadow_discoverable` defaults `False`,
`SHADOW_TRADE` notifications carry no amounts), and a public board showing
balances would contradict it.

**Cohort.** You plus everyone you hold an `ACCEPTED` `ShadowLink` with, in
either direction. Mutual by construction — you only appear on a board with
someone who agreed to the link. `PENDING` links don't count.

**Metric: percentage return, never absolute equity.** The two are equivalent
today, but absolute breaks the moment baselines differ, and publishing balances
would breach the privacy rule above. Equity means cash across all wallets
(converted to USD) plus holdings marked to current prices — not realised P&L,
which would reward never selling a loser.

**Seasons.** Default 90 days (`SEASON_LENGTH_DAYS`). A lifetime board decays
into a measure of who joined earliest: someone a year ahead has compounded
longer and a newcomer can't catch up by being better, only by waiting. Quarterly
gives four fresh starts a year; a year is too long for a friend group's
attention and too long to recover from a bad start.

- **Money persists across seasons.** Only the ranking resets.
- **Baseline is equity at season start**, not the signup grant, so a player
  already up 300% isn't credited with that gain again every season.
- **Mid-season joiners are excluded.** Participant rows are written once, when
  the season opens, for accounts that already exist. No row means not ranked —
  a late joiner measured over a shorter window isn't comparable. They're
  enrolled automatically at the next boundary, and `viewer_ranked` in the
  response tells the client to explain why they aren't listed.
- **The career board** covers the same cohort measured against the starting
  grant, which is only sound because that grant is the only money that ever
  enters an account.

**Snapshots.** `equity_snapshots` holds one row per user per day, written by the
scheduler at 01:00 — after the nightly price refresh, so equity is valued
against the prices that job just wrote. Ranking needs cash plus holdings for
every user; computing that per request would be users × holdings × price lookups
on every page load. The unique constraint on `(user_id, captured_on)` makes the
job idempotent, so a retry updates rather than duplicates.

`ensure_season` runs daily at 01:30 and on boot, and is a no-op while a season
is running. The boot call matters for the first deploy: without it there is no
season, and every existing account would otherwise be treated as a mid-season
joiner and excluded from the first one.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/leaderboard/friends` | Current season ranking across the cohort |
| GET | `/api/v1/leaderboard/friends/career` | All-time ranking across the cohort |
| GET | `/api/v1/leaderboard/season` | The running season, or `null` |

Entries carry `user_id`, `username`, `return_percent` and `rank` — never a
balance.

## Known gaps

- **Sybil resistance.** One person with many accounts, each concentrated in a
  different stock, guarantees one spectacular winner. Email verification helps;
  account-age minimums and a risk-adjusted metric would help more.
- **Volatility beats skill over a short season.** Ranking purely on return
  rewards concentration. The daily snapshots are the raw material for a
  risk-adjusted secondary metric whenever that's wanted.
