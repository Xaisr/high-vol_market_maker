# Vol Desk Pro — 7DTE OTM/ATM Market-Making Trainer

European option market-making simulator for practicing volatility quoting,
inventory control, and delta hedging. Desktop GUI for play, headless engine
for batch runs and Docker practice.

* Chain: `98P, 99P, 100C, 100P, 101C, 102C` (tight OTM + ATM straddle)
* Underlying: `S0=100`, `T=7/365` fixed, `r=0`
* Modes per strike: `OFF` (pulled) / `AUTO` (theo ± spread/2) / `MAN` (typed bid/ask)
* Flow: uninformed Poisson-ish + informed toxic sweeps + competitor queue
* Hedge: spot 1:1, auto when `|delta| > limit`
* PnL: `cash + q*fair_theo + hedge_cash + hedge_q*S` (marked at fair, not your quote)

> Educational simulator, not trading advice. No live data, no broker connectivity.

## Quickstart

### Local GUI

```powershell
pip install -r requirements.txt
python app.py
```

Requires Tkinter (bundled on Windows/macOS Python, `apt install python3-tk` on Debian/Ubuntu).

Controls: `IV±` buttons or `Space+click` chain, `[` `]` move curve, double-click row
`OFF → AUTO → MAN`, `+/-` quote size, `R` reload, `Hedge flat` button.

### Headless / Docker

```powershell
python headless_run.py
# Docker Desktop must be running:
docker build -t mm-headless:0.1 .
docker run --rm mm-headless:0.1
docker run --rm -e N_TICKS=1000 mm-headless:0.1
```

Docker image contains only `engine.py + headless_run.py`. GUI (`app.py`)
is intentionally excluded — Tk needs a display server, painful in containers
on Windows.

## Project structure

```text
app.py           Tkinter + matplotlib desk: chain table, risk cards, spot/PnL charts, log
engine.py        UI-free simulation: GBM spot, BS theo/greeks, flow, hedge, PnL
headless_run.py  Batch entrypoint for CI/Docker: runs N_TICKS, prints summary
requirements.txt numpy + scipy + matplotlib (pinned)
Dockerfile       python:3.13-slim headless image
.dockerignore    excludes __pycache__/, .git/
```

## Model

### 1. Spot and fair vol

* Spot: GBM per 1-second tick, `dt = 1/(365·24·3600)` in years.
  `S_{t+1} = S_t·exp((μ − σ²/2)dt + σ√dt·z)`, default `σ=20%`, `μ=0`.
* Fair IV breathes via Ornstein-Uhlenbeck, mean-reverting to `fair_iv=20%`:
  `κ=33/day` (~30-min half-life), `ξ=4 vol-pts/√day`, `ρ=−0.6`
  (spot down → fair up). Clamped `[5%, 60%]`.
* Your quote IV (`iv`) is a single curve number you move. PnL is marked at
  fair, so shifting your curve cannot fake PnL.

### 2. Pricing and smile

Black-Scholes, European, `r=0`, `T_live = 7/365 − tick·dt` floored at 0.
Per-lot = 1 contract on 1 share (no ×100).

Fixed smile in vol points added to both curves (`engine.py: SMILE_VOLPTS`):

| inst | add |
|------|-----|
| 98P | +2.0 |
| 99P | +1.0 |
| 100C/100P | 0.0 |
| 101C | −0.5 |
| 102C | −1.0 |

OTM puts rich, OTM calls cheap — standard equity skew stub.

Greeks per lot: delta `N(d1)` / `N(d1)−1`, gamma `n(d1)/(S·iv·√T)`,
vega per vol-point `S·n(d1)·√T/100`, theta per calendar day.
Expired (`T≤0`): price = intrinsic, delta ∈ `{0,±1}`, rest 0.

### 3. Quotes

* `OFF`: `(None, None)`, no fills.
* `AUTO` (default): `theo ± spread/2 − skew·q`,
  `spread=0.20` default, `skew_per_lot=0.02` (Stoikov-lite: long inventory
  pushes both quotes down, short lifts them).
* `MAN`: your typed `man_bid/man_ask`, no skew.

`theo` uses your `iv`; `fair_theo` uses live `fair_iv`. Spread captured
is measured vs fair at fill time.

### 4. Taker flow

Per strike per tick:

* **Uninformed:** per side `p = A·exp(−k·spread/2)`, `A=0.02`, `k=8.0`.
  Wider spread → exponentially fewer fills. Fill size = showing lots.
* **Competition/queue:** on a touch you win only `win_rate=25%` of touches,
  then `queue_win=50%` coin-flip for being first. ~12.5% effective hit rate
  forces realistic spread economics.
* **Informed (toxic):** with prob `p_informed/len(INSTRUMENTS)` per strike,
  if direction matches type (up→calls, down→puts) **and** your theo is stale
  vs fair (cheap ask / rich bid), sweep `lots·informed_mult` (`3×`).
  Tagged `BUY*`/`SELL*` in log. `streak_p=60%` repeats last toxic direction
  (runs of 3–5), 10% chance to clear streak each quiet tick.

Why these choices: `A,k` give spread-elastic retail flow; low win-rate
prevents scalping every touch; toxic-only-when-stale punishes lagging the
fair-vol move, the core MM skill being trained.

### 5. Inventory and hedge

* `lots` 0–5 per strike (your showing size), `autofill=True` reloads after
  each fill; `False` leaves side at 0 until manual Reload.
* `max_q=10` per-strike cap: blocks fills that grow `|q|` past cap,
  closing fills always pass.
* `fill_fee=0.02` per option fill, `hedge_slip=0.05`/share.
* Auto-hedge to flat when `|opt_delta + hedge_q| > delta_limit (2.0)`.
  Manual `Hedge flat` button + `Flatten opts` (close options at fair touch,
  paying half-spread + fee).

### 6. Settlement and PnL

* `options_value = Σ q·fair_theo`, `total = cash + options_value + hedge_cash + hedge_q·S`.
* `strike_full_pnl = cash_by[strike] + q·fair_theo` (realized + live fair).
* Expiry (`T_live=0`): cash-settle all `q` to intrinsic, flatten book.

### Config reference (`EngineConfig`)

| param | default | meaning |
|-------|---------|---------|
| `S0, sigma, mu` | `100, 0.20, 0.0` | GBM spot |
| `iv, fair_iv` | `0.20, 0.20` | your curve / true fair |
| `spread` | `0.20` | full bid-ask width (pts) |
| `lots, modes` | `1, AUTO` | per-strike size / OFF-AUTO-MAN |
| `autofill` | `True` | auto-reload showing lots |
| `A, k` | `0.02, 8.0` | uninformed intensity / spread sensitivity |
| `p_informed, informed_mult, streak_p` | `0.20, 3, 0.60` | toxic share / sweep size / momentum |
| `win_rate, queue_win` | `0.25, 0.50` | competition / queue position |
| `skew_per_lot` | `0.02` | inventory skew |
| `fair_kappa_day, fair_xi_volpts, fair_rho` | `33.0, 4.0, −0.6` | OU fair-vol dynamics |
| `delta_limit, auto_hedge` | `2.0, True` | hedge threshold / enable |
| `hedge_slip, fill_fee, max_q` | `0.05, 0.02, 10` | frictions / cap |
| `dt_days` | `1/(365·24·3600)` | 1-second tick |

## Limitations / next steps

* Fixed 7DTE clock, no term structure; single-spot, no dividends/jumps.
* Fill size = showing lots; no partial depth or limit-order-book.
* ~50 ms/tick (SciPy `norm` per strike) — fine for GUI, slow for large batches.
* Ideas: vectorized greeks, intraday `T` decay to 0DTE, limit-book depth,
  vol-surface (strike+tenor), trade log CSV, pytest for `engine.py`.

## License

MIT — see `LICENSE`.
