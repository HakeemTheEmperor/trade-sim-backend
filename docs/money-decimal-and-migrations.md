# Task: Money → Decimal + introduce DB migrations (Flask-Migrate/Alembic)

> **STATUS: IMPLEMENTED (2026-07-05).** Flask-Migrate is wired up; `migrations/`
> holds a baseline revision (`cc30a7d4cdf3`) and the money-to-numeric revision
> (`74b08526d730`). Models, defaults, a global Decimal JSON provider, and the
> service arithmetic are all converted. Verified against a real Postgres 16:
> the money migration preserves values, is reversible (downgrade→upgrade round
> trips), and buy/sell/transfer/portfolio all compute correctly with Decimal.
> `flask db upgrade` runs on startup via `bootstrap.sh`.
>
> **⚠️ One-time step for the EXISTING production DB** (its tables were created by
> the old `create_all()`, so it has no alembic history): before the first deploy
> of this change, stamp it at baseline so `upgrade` only runs the money revision,
> not the table-creating baseline:
> ```
> RUN_BACKGROUND_JOBS=false flask db stamp cc30a7d4cdf3   # one time, existing DB only
> ```
> Fresh databases need nothing — `flask db upgrade` builds the whole schema.

**Why:** Money is currently stored in `Float` columns, which drift on rounding. The
schema is also half-migrated already (stock prices/quantities are `Numeric`, balances
are `Float`), and that mismatch is what caused the `Decimal * float` TypeError in
buy/sell (fixed in commit `8dbb3e6` with an `as_decimal` workaround). Making all money
`Decimal` removes both the precision bug and that workaround. Changing column types
safely requires a migration tool, which the project doesn't have yet (`db.create_all()`).
So this is two linked pieces: **(A) add migrations, then (B) convert the columns.**

---

## Part A — Introduce Flask-Migrate (do first, ship on its own)

1. **Add dependency** `Flask-Migrate` (pulls in Alembic). ⚠️ Same Pipfile.lock churn we hit
   with gunicorn: a full `pipenv lock` here wants to bump ~28 unrelated pins. Options:
   (a) do a deliberate, reviewed `pipenv lock` upgrade as its own commit *(recommended for a
   real runtime dep like this)*, or (b) install it in the Dockerfile like gunicorn.
2. **Wire it up** in `create_app`: `Migrate(app, db)` (import after `db`/models are set up).
3. **Baseline the existing schema** (the DB was built by `create_all()`, so there's no
   migration history):
   - `flask db init` → creates `migrations/`.
   - `flask db migrate -m "baseline schema"` → autogenerate the initial revision from the
     current models. **Review it** — autogenerate misses server defaults, enum tweaks, etc.
   - Existing/deployed DBs: `flask db stamp head` to mark them at baseline *without*
     re-creating tables. Fresh DBs: `flask db upgrade`.
4. **Replace `db.create_all()`** in `create_app` with migrations. Run `flask db upgrade` on
   deploy (e.g. in `bootstrap.sh` before gunicorn starts). Keep `create_all` only for throwaway
   local dev if you like, but prefer `upgrade` everywhere so schema is reproducible.

## Part B — Float → Numeric columns

Concrete changes (everything else money-ish is already `Numeric`):

| Model.column                     | now       | → to             | notes                          |
|----------------------------------|-----------|------------------|--------------------------------|
| `wallet.balance`                 | Float     | `Numeric(18, 4)` | default `Decimal("100000.00")`  |
| `transactions.total_value`       | Float     | `Numeric(18, 4)` |                                |
| `transactions.price_per_share`   | Float     | `Numeric(15, 6)` | match `StockPrice` precision   |
| `exchangerate.rate`              | Float     | `Numeric(18, 8)` | FX rates need more scale       |

Already `Numeric`, leave alone: `stock_price.*`, `stock_history.cp`,
`user_stock_wallet.quantity`.

**Decision point — share quantity type.** `transactions.quantity` is `Integer` but
`user_stock_wallet.quantity` is `Numeric(15,6)`. Pick one and make them consistent:
- (a) whole shares only → make `user_stock_wallet.quantity` `Integer`; or
- (b) fractional shares → make `transactions.quantity` `Numeric(15,6)`.
Otherwise a fractional buy silently truncates in the transaction row. The validator/UI
currently accept fractional input, so (b) is the likely intent — confirm before choosing.

## Part C — Code changes that MUST ship with the type change

1. **Model defaults** → `Decimal(...)` literals, not floats (e.g. `default=Decimal("100000.00")`).
2. **JSON serialization.** Flask's JSON provider can't encode `Decimal` (it raises). There's
   already a pattern for this: `StockPrice.to_dict` does `float(self.current_price)  # Convert
   Decimal to float`. Two ways to extend it:
   - **Per-field cast** in `Wallet.to_dict` (balance), `Transaction.to_dict` (total_value,
     price_per_share), and the hand-built dict in `transactions_service.get_transaction_details`
     (total_value, pps). Easy to miss a spot.
   - **Global (recommended):** register a custom Flask `JSONProvider` that serializes `Decimal`
     once. Use `float` (keeps the current API shape — numbers stay JSON numbers) rather than
     `str` (exact but changes the contract). Then drop the ad-hoc `float()` casts.
3. **Simplify the arithmetic.** Once `wallet.balance` and `exchangerate.rate` are `Numeric`,
   the whole money path is Decimal end-to-end, so:
   - Remove the `as_decimal` split from `validate_positive_number` — return `Decimal` for all
     money/quantity, drop the `float(total_cost)` casts and `int(amount)` in the services.
   - Wrap the external FX `conversion_rate` in `Decimal(str(...))` in
     `wallet_service.fetch_from_api`.
   Prices ingested in `data_seed`/`websocket_listener` already use `Decimal(str(...))` — keep.

## Migration ordering & safety

1. Ship **Part A** alone; deploy; confirm `stamp`/`upgrade` work on a copy of prod.
2. Make the model + code changes (B/C) together; `flask db migrate -m "money to numeric"`.
   **Review the script:** Postgres `float → numeric` needs a `USING` cast; make sure Alembic
   emits `alter column ... type numeric ... postgresql_using: 'balance::numeric'` (add it if not).
3. **Back up the DB first** — a column type change rewrites the column.
4. Test buy / sell / transfer / portfolio end-to-end on a data copy; diff balances before/after
   (the float→numeric conversion can surface pre-existing rounding).

## Acceptance checklist

- [ ] No `db.Float` remains for any money column.
- [ ] API response shapes unchanged (amounts still serialize as JSON numbers).
- [ ] buy / sell / transfer / portfolio correct; no Decimal/float TypeErrors; no rounding drift.
- [ ] Migrations reproducible: fresh DB via `flask db upgrade`; existing DB via `stamp` + `upgrade`.
- [ ] `as_decimal` workaround removed once the schema is fully Decimal.
