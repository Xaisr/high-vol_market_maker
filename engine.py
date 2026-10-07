"""v0 engine: GBM spot + BS theo + mixed taker flow + portfolio m2m + delta hedge.
UI-free. All prices in points. S0=100. T=7/365 fixed. r=0.
Instruments: 98P,99P,100C,100P,101C,102C (tight OTM + ATM straddle).
Modes per strike: OFF (pulled, no fills) / AUTO (theo +/- spread/2) / MAN (your typed bid/ask).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import numpy as np
from scipy.stats import norm

YEAR = 365.0
T_FIX = 7.0 / YEAR  # 7 DTE

INSTRUMENTS = [
    ("98P", 98, "P"),
    ("99P", 99, "P"),
    ("100C", 100, "C"),
    ("100P", 100, "P"),
    ("101C", 101, "C"),
    ("102C", 102, "C"),
]

# fixed smile in vol points: OTM puts rich, OTM calls cheap; your curve shifts it whole
SMILE_VOLPTS = {
    "98P": +2.0,
    "99P": +1.0,
    "100C": 0.0,
    "100P": 0.0,
    "101C": -0.5,
    "102C": -1.0,
}


def bs_price(S, K, T, r, iv, cp: str) -> float:
    if T <= 0 or iv <= 0 or S <= 0:
        return max(S - K, 0.0) if cp == "C" else max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if cp == "C":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_greeks(S, K, T, r, iv, cp: str) -> dict:
    """Per 1 lot = 1 contract on 1 share (no x100 multiplier in v0)."""
    if T <= 0 or iv <= 0 or S <= 0:
        # expired: delta is 0/1 payoff slope, rest 0
        if cp == "C":
            d = 1.0 if S > K else 0.0
        else:
            d = -1.0 if S < K else 0.0
        px = max(S - K, 0.0) if cp == "C" else max(K - S, 0.0)
        return {"price": px, "delta": d, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    sqT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * sqT)
    d2 = d1 - iv * sqT
    nd1 = norm.pdf(d1)
    price = bs_price(S, K, T, r, iv, cp)
    delta = norm.cdf(d1) if cp == "C" else norm.cdf(d1) - 1.0
    gamma = nd1 / (S * iv * sqT)
    vega = S * nd1 * sqT / 100.0  # per 1 vol point
    # theta per calendar day
    term1 = -(S * nd1 * iv) / (2 * sqT)
    if cp == "C":
        term2 = r * K * math.exp(-r * T) * norm.cdf(d2)
        theta_ann = term1 - term2
    else:
        term2 = r * K * math.exp(-r * T) * norm.cdf(-d2)
        theta_ann = term1 + term2
    theta = theta_ann / YEAR
    return {"price": price, "delta": delta, "gamma": gamma, "vega": vega, "theta": theta}


@dataclass
class EngineConfig:
    S0: float = 100.0
    sigma: float = 0.20      # GBM annual vol of spot
    mu: float = 0.0
    iv: float = 0.20         # YOUR quote curve (moves with spacebar)
    fair_iv: float = 0.20    # long-run fair + starting fair (fair itself breathes via OU)
    spread: float = 0.20     # full bid-ask width in points
    lots: dict = field(default_factory=lambda: {n: 1 for n, _, _ in INSTRUMENTS})  # reload size per strike (your quote size, 1-5)
    modes: dict = field(default_factory=lambda: {n: "AUTO" for n, _, _ in INSTRUMENTS})
    man_bid: dict = field(default_factory=dict)  # MAN mode: your typed bid
    man_ask: dict = field(default_factory=dict)  # MAN mode: your typed ask
    autofill: bool = True     # True: taken lots auto-reload to `lots`. False: side stays 0 until you Reload
    A: float = 0.02          # customer flow: base fill prob per side per tick
    k: float = 8.0            # spread sensitivity
    p_informed: float = 0.20  # share of ticks with informed sweep
    informed_mult: int = 3    # informed want = lots * mult (sweeps what's showing)
    streak_p: float = 0.60    # prob toxic repeats last direction (runs of 3-5)
    hedge_slip: float = 0.05  # per-share slippage crossing futures touch
    fill_fee: float = 0.02    # per option fill fee
    max_q: int = 10           # per-strike bag cap: blocks fills that grow |q| past this
    win_rate: float = 0.25    # competition: you win only this share of touches
    queue_win: float = 0.5    # queue: coin-flip you were first at the touch
    skew_per_lot: float = 0.02  # Stoikov-lite: quotes shift by -skew*q (shorts lift)
    fair_kappa_day: float = 33.0  # OU pull (~30-min half-life)
    fair_xi_volpts: float = 4.0   # vol-of-vol in vol points / sqrt(day)
    fair_rho: float = -0.6        # spot down -> fair up
    delta_limit: float = 2.0  # auto-hedge threshold (shares)
    auto_hedge: bool = True
    dt_days: float = 1.0 / (YEAR * 24 * 3600)  # 1 second in years


@dataclass
class Engine:
    cfg: EngineConfig = field(default_factory=EngineConfig)
    S: float = 100.0
    tick: int = 0
    cash: float = 0.0
    q: dict = field(default_factory=lambda: {n: 0 for n, _, _ in INSTRUMENTS})
    hedge_q: float = 0.0
    hedge_cash: float = 0.0
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng())
    seed: int | None = None
    fair_iv: float = 0.20      # live breathing fair (OU state, m2m uses this)
    streak: int | None = None  # last toxic direction (+1 up / -1 down) for runs
    work_bid: dict = field(default_factory=lambda: {n: 1 for n, _, _ in INSTRUMENTS})  # lots showing now
    work_ask: dict = field(default_factory=lambda: {n: 1 for n, _, _ in INSTRUMENTS})
    cash_by: dict = field(default_factory=dict)    # realized cash flow per strike (incl fees)
    spread_by: dict = field(default_factory=dict)  # spread captured vs fair at fill time
    theo: dict = field(default_factory=dict)       # YOUR quote theos (from iv)
    greeks: dict = field(default_factory=dict)
    fair_theo: dict = field(default_factory=dict)  # TRUE fair theos (from live fair_iv)
    fair_greeks: dict = field(default_factory=dict)

    def __post_init__(self):
        self.S = self.cfg.S0
        if self.seed is not None:
            self.rng = np.random.default_rng(self.seed)
        self.fair_iv = self.cfg.fair_iv
        self.streak = None
        for n, _, _ in INSTRUMENTS:
            self.work_bid[n] = int(self.cfg.lots.get(n, 1))
            self.work_ask[n] = int(self.cfg.lots.get(n, 1))
            self.cash_by[n] = 0.0
            self.spread_by[n] = 0.0
        self.refresh_theos()

    def reload_lots(self, name=None):
        """Refill working lots to quote size (manual reload when autofill off)."""
        names = [name] if name else [n for n, _, _ in INSTRUMENTS]
        for n in names:
            self.work_bid[n] = int(self.cfg.lots.get(n, 1))
            self.work_ask[n] = int(self.cfg.lots.get(n, 1))

    def _take(self, name, taker_side, want, price):
        """Fill against working lots. Blocks fills that grow |q| past max_q (closing ok)."""
        if taker_side == "BUY":  # lifts our ask -> our q goes down
            avail = self.work_ask.get(name, 0)
            fill = min(avail, want)
            if fill <= 0:
                return 0
            new_q = self.q[name] - fill
            if abs(new_q) > self.cfg.max_q and abs(new_q) > abs(self.q[name]):
                return 0  # over bag cap: don't open more, closing fills still pass
            self.work_ask[name] = avail - fill
            self.q[name] = new_q
            self.cash += price * fill - self.cfg.fill_fee
            self.cash_by[name] = self.cash_by.get(name, 0.0) + price * fill - self.cfg.fill_fee
            self.spread_by[name] = self.spread_by.get(name, 0.0) + (price - self.fair_theo[name]) * fill
            if self.cfg.autofill:
                self.work_ask[name] = int(self.cfg.lots.get(name, 1))
            return fill
        else:  # SELL hits our bid -> our q goes up
            avail = self.work_bid.get(name, 0)
            fill = min(avail, want)
            if fill <= 0:
                return 0
            new_q = self.q[name] + fill
            if abs(new_q) > self.cfg.max_q and abs(new_q) > abs(self.q[name]):
                return 0
            self.work_bid[name] = avail - fill
            self.q[name] = new_q
            self.cash -= price * fill + self.cfg.fill_fee
            self.cash_by[name] = self.cash_by.get(name, 0.0) - price * fill - self.cfg.fill_fee
            self.spread_by[name] = self.spread_by.get(name, 0.0) + (self.fair_theo[name] - price) * fill
            if self.cfg.autofill:
                self.work_bid[name] = int(self.cfg.lots.get(name, 1))
            return fill

    def strike_full_pnl(self, name):
        """Full per-strike m2m: realized cash flow + position at live fair."""
        return self.cash_by.get(name, 0.0) + self.q.get(name, 0) * self.fair_theo.get(name, 0.0)

    def flatten_options(self):
        """Close all option bags at fair touch (pay half-spread + fee). Returns cash delta."""
        total = 0.0
        for name, _, _ in INSTRUMENTS:
            q = self.q[name]
            if q == 0:
                continue
            f = self.fair_theo[name]
            h = self.cfg.spread / 2.0
            if q > 0:  # long -> sell at fair bid
                px = max(f - h, 0.01)
                self.cash += q * px - self.cfg.fill_fee
                total += q * px
            else:  # short -> buy at fair ask
                px = f + h
                self.cash -= (-q) * px + self.cfg.fill_fee
                total -= (-q) * px
            self.q[name] = 0
        self.reload_lots()
        return total

    def T_live(self):
        return max(T_FIX - self.tick * self.cfg.dt_days, 0.0)

    # ---- market ----
    def refresh_theos(self):
        T = self.T_live()
        for name, K, cp in INSTRUMENTS:
            qiv = self.cfg.iv + SMILE_VOLPTS.get(name, 0.0) / 100.0
            g = bs_greeks(self.S, K, T, 0.0, max(qiv, 0.01), cp)
            self.theo[name] = g["price"]
            self.greeks[name] = g
            fiv = self.fair_iv + SMILE_VOLPTS.get(name, 0.0) / 100.0
            fg = bs_greeks(self.S, K, T, 0.0, max(fiv, 0.01), cp)
            self.fair_theo[name] = fg["price"]
            self.fair_greeks[name] = fg

    def quote_iv(self, name):
        return self.cfg.iv + SMILE_VOLPTS.get(name, 0.0) / 100.0

    def quotes(self, name):
        """(bid, ask) or (None,None) if OFF. AUTO = smile theo +/- spread/2, skewed by -skew*q."""
        mode = self.cfg.modes.get(name, "AUTO")
        if mode == "OFF":
            return None, None
        if mode == "MAN":
            b = self.cfg.man_bid.get(name)
            a = self.cfg.man_ask.get(name)
            if b is None or a is None:  # not set yet -> fall back to AUTO once
                t = self.theo[name]
                h = self.cfg.spread / 2.0
                sk = self.cfg.skew_per_lot * self.q.get(name, 0)
                return max(t - h - sk, 0.01), t + h - sk
            return b, a
        t = self.theo[name]
        h = self.cfg.spread / 2.0
        sk = self.cfg.skew_per_lot * self.q.get(name, 0)
        return max(t - h - sk, 0.01), t + h - sk

    def _wins_touch(self):
        if self.rng.random() > self.cfg.win_rate:
            return False
        return self.rng.random() < self.cfg.queue_win

    def settle_if_expired(self):
        """Cash-settle at intrinsic when clock hits zero. Returns True if expired."""
        if self.T_live() > 0:
            return False
        for name, K, cp in INSTRUMENTS:
            q = self.q.get(name, 0)
            if q == 0:
                continue
            intrinsic = max(self.S - K, 0.0) if cp == "C" else max(K - self.S, 0.0)
            self.cash += q * intrinsic
            self.q[name] = 0
        self.reload_lots()
        return True

    def step(self):
        """Advance 1 tick: OU fair, GBM spot (corr), taker fills with fees, auto-hedge with slip."""
        c = self.cfg
        dt = c.dt_days
        dt_day = 1.0 / (24 * 3600)
        # correlated shocks: z drives spot, w drives extra vol noise
        z = self.rng.standard_normal()
        w = self.rng.standard_normal()
        rho = c.fair_rho
        z_vol = rho * z + math.sqrt(max(1 - rho * rho, 0.0)) * w
        # 3) fair IV breathes: OU, mean-reverting to cfg.fair_iv (benign tape)
        self.fair_iv = max(0.05, min(0.60, self.fair_iv
            + c.fair_kappa_day * (c.fair_iv - self.fair_iv) * dt_day
            + (c.fair_xi_volpts / 100.0) * math.sqrt(dt_day) * z_vol))
        # GBM spot step
        S_prev = self.S
        self.S = S_prev * math.exp((c.mu - 0.5 * c.sigma**2) * dt + c.sigma * math.sqrt(dt) * z)
        self.tick += 1
        self.refresh_theos()
        fills = []
        base_up = self.S >= S_prev
        # streak override: toxic repeats last direction with streak_p
        if self.streak is not None and self.rng.random() < c.streak_p:
            up = self.streak > 0
        else:
            up = base_up
        for name, K, cp in INSTRUMENTS:
            if c.modes.get(name) == "OFF":
                continue
            bid, ask = self.quotes(name)
            size = int(c.lots.get(name, 1))
            if size <= 0:
                continue
            # --- 1) uninformed: wins touch vs competitors, then fills what's showing ---
            p_side = c.A * math.exp(-c.k * (c.spread / 2.0))
            for side in ("BUY", "SELL"):  # side from taker's view; BUY lifts our ask
                if self.rng.random() < p_side:
                    if not self._wins_touch():
                        continue
                    got = self._take(name, side, size, ask if side == "BUY" else bid)
                    if got:
                        fills.append((name, side, got, ask if side == "BUY" else bid))
            # --- 2) informed: snipes ONLY when your curve is behind fair ---
            # calls into an up move: your theo <= fair theo (cheap vol, ask is a gift)
            # puts into a down move: your theo >= fair theo (rich vol, bid is a gift)
            wants = (up and cp == "C") or ((not up) and cp == "P")
            if wants and self.rng.random() < c.p_informed / len(INSTRUMENTS):
                got = 0
                fair = self.fair_theo[name]
                theo = self.theo[name]
                stale = (up and theo <= fair + 1e-9) or ((not up) and theo >= fair - 1e-9)
                if stale and self._wins_touch():
                    isz = size * c.informed_mult
                    if up:  # lifts your cheap ask
                        got = self._take(name, "BUY", isz, ask)
                        if got:
                            fills.append((name, "BUY*", got, ask))
                    else:  # hits your rich bid
                        got = self._take(name, "SELL", isz, bid)
                        if got:
                            fills.append((name, "SELL*", got, bid))
                if got:
                    self.streak = +1 if up else -1
                elif self.rng.random() < 0.10:
                    self.streak = None
            elif self.rng.random() < 0.10:
                self.streak = None
        # --- auto delta hedge to flat if beyond limit, with slippage ---
        hmsg = ""
        if c.auto_hedge:
            d = self.portfolio_greeks()["delta"] + self.hedge_q
            if abs(d) > c.delta_limit:
                dq = -d  # hedge to 0
                cost = c.hedge_slip * abs(dq)
                self.hedge_q += dq
                self.hedge_cash -= dq * self.S + cost
                hmsg = f"hedge {dq:+.2f} @ {self.S:.2f} (slip {cost:.2f})"
        return fills, hmsg

    # ---- accounting ----
    def settle_theos(self):
        return dict(self.theo)

    def portfolio_greeks(self):
        # marked at FAIR vol, not your quote vol — moving your curve can't fake PnL
        tot = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
        for name, _, _ in INSTRUMENTS:
            q = self.q[name]
            g = self.fair_greeks[name]
            tot["delta"] += q * g["delta"]
            tot["gamma"] += q * g["gamma"]
            tot["vega"] += q * g["vega"]
            tot["theta"] += q * g["theta"]
        return tot

    def options_value(self):
        # m2m at FAIR theo
        return sum(self.q[n] * self.fair_theo[n] for n, _, _ in INSTRUMENTS)

    def total_pnl(self):
        return self.cash + self.options_value() + self.hedge_cash + self.hedge_q * self.S

    def reset(self, seed=None):
        self.S = self.cfg.S0
        self.tick = 0
        self.cash = 0.0
        self.hedge_q = 0.0
        self.hedge_cash = 0.0
        self.fair_iv = self.cfg.fair_iv
        self.streak = None
        for n, _, _ in INSTRUMENTS:
            self.q[n] = 0
            self.cash_by[n] = 0.0
            self.spread_by[n] = 0.0
        self.reload_lots()
        if seed is not None:
            self.seed = seed
            self.rng = np.random.default_rng(seed)
        elif self.seed is None:
            # fresh random path every Reset so you don't replay the same fall
            self.rng = np.random.default_rng()
        self.refresh_theos()
