"""Headless batch run — no Tkinter/display needed.

Usage:
    python headless_run.py
    N_TICKS=1000 python headless_run.py
"""
import os
from engine import Engine


def main() -> None:
    n_ticks = int(os.getenv("N_TICKS", "300"))
    e = Engine()
    for _ in range(n_ticks):
        e.step()
        if e.settle_if_expired():
            break
    print(f"ticks={e.tick} spot={e.S:.2f} fair_iv={e.fair_iv*100:.2f}")
    print(f"cash={e.cash:+.2f} opt={e.options_value():+.2f} total_pnl={e.total_pnl():+.2f}")
    print(f"greeks={e.portfolio_greeks()} pos={e.q}")


if __name__ == "__main__":
    main()
