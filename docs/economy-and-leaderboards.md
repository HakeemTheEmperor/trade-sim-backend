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

Rankings live in **named leagues people opt into with a join code**. There is no
global board.

This replaced an earlier design that built a board from your accepted
`ShadowLink` connections. That version computed a different cohort per viewer,
so no two people saw the same table and nobody could talk about "the standings"
— there weren't any. A league is a shared object: every member sees an identical
ranking. The shadow graph keeps its actual job (trade notifications); only the
ranking moved.

**The privacy trade-off this accepts.** The shadow board only ever exposed your
return to people you had mutually agreed to link with. A join code exposes it to
whoever holds the code — and someone will eventually post one publicly.
Percentages only, never balances, and joining is an explicit act. The caps below
are what bound the damage.

| Setting | Default | Why |
|---|---|---|
| `MAX_LEAGUE_MEMBERS` | 50 | Covers any real friend group, course or office team; keeps the table to one screen (no pagination to build); bounds how far a leaked code spreads your return |
| `MAX_LEAGUES_PER_USER` | 5 | A member cap alone doesn't stop one person joining hundreds, each a set of strangers who can see their return |

Neither is a performance limit — a snapshot-backed table would serve far more.
They are product decisions.

**Join codes** are 8 characters from a 31-character alphabet with the ambiguous
ones removed (no I/L/O/0/1, because codes get read aloud and retyped from
screenshots). That's ~8.5e11 combinations, which is only out of reach because
the join endpoint is rate limited; an invalid code and a code for a league you
can't see return the same error, so the endpoint can't confirm which codes exist.

**The member cap is enforced under a row lock.** A count is not something a
database constraint can express, so two people joining simultaneously at 49
would both pass an unlocked check. Same pattern as the balance checks in
`transfer_funds` and `buy_stocks`.

**Ownership.** The creator owns the league and can delete it; everyone else can
leave. The owner cannot leave — they delete instead. Transferring ownership on
the way out would be nicer, but it adds a state to reason about for something a
small league handles socially, and an ownerless league can't be deleted by
anyone.

**Metric: percentage return, never absolute equity.** Equity means cash across
all wallets (converted to USD) plus holdings marked to current prices — not
realised P&L, which would reward never selling a loser.

**Seasons** are global, not per-league: every league is ranked over the same
window. Default 90 days (`SEASON_LENGTH_DAYS`). A lifetime board decays into a
measure of who joined earliest, since someone a year ahead has compounded longer
and a newcomer can't catch up by being better, only by waiting.

- **Money persists across seasons.** Only the ranking resets.
- **Baseline is equity at season start**, not the signup grant, so a player
  already up 300% isn't credited with that gain again every season.
- **There is a joining window, then exclusion.** Sign up within
  `SEASON_JOIN_GRACE_DAYS` (30) of a season opening and you're enrolled
  immediately, with your own starting equity as the baseline. Sign up after that
  and you wait for the next season.

  Without the grace the rule was brutally binary: signing up one minute after a
  season opened left you unrankable for the whole quarter — which, for a young
  app, is every new user. The window keeps the fairness intent (someone
  appearing in the closing weeks can't be measured against people who ran the
  full period) while making the common case work. `viewer_ranked` tells the
  client to explain the absence rather than leaving someone to notice they're
  missing from their own league.

  This is about when the *account* was created, not when it joined the league:
  joining a league at any point in a season is fine and ranks you on your season
  performance.
- **The career table** measures against the starting grant, which is only sound
  because that grant is the only money that ever enters an account.

**Tables are served from the daily snapshots**, not valued live. One indexed
query instead of members × holdings × price lookups on every page load — which
is what makes a 50-member league affordable where a 5-person cohort didn't care.
Anyone without a snapshot yet (a new account, or any account on the first day
before the 01:00 job runs) is valued live so they aren't silently missing;
that's bounded by the member cap. Responses carry `as_of` so the client can say
when the standings were taken rather than implying they're live.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/leagues` | Leagues you're in |
| POST | `/api/v1/leagues` | Create one (returns its join code) |
| POST | `/api/v1/leagues/join` | Join with `{code}` |
| GET | `/api/v1/leagues/<id>` | Current-season table |
| GET | `/api/v1/leagues/<id>/career` | All-time table |
| DELETE | `/api/v1/leagues/<id>/leave` | Leave (non-owners) |
| DELETE | `/api/v1/leagues/<id>` | Delete (owner only) |
| GET | `/api/v1/leaderboard/season` | The running season, or `null` |

Entries carry `user_id`, `username`, `return_percent` and `rank` — never a
balance. Reading a table you aren't a member of returns the same error as a
league that doesn't exist, so ids can't be enumerated to discover who is in
what.

## Known gaps

- **Sybil resistance.** One person with many accounts, each concentrated in a
  different stock, guarantees one spectacular winner. Email verification helps;
  account-age minimums and a risk-adjusted metric would help more.
- **Volatility beats skill over a short season.** Ranking purely on return
  rewards concentration. The daily snapshots are the raw material for a
  risk-adjusted secondary metric whenever that's wanted.
