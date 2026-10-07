"""Vol Desk Pro — European OTM/ATM market-making trainer (7DTE, 98-102).
Run:  python app.py   (stdlib tkinter + matplotlib only)
"""
import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from engine import Engine, INSTRUMENTS

VOL_STEPS = [0.1, 0.2, 0.3, 0.5]
FONT = ("Segoe UI", 9)
MONO = ("Consolas", 10)
MONO_BIG = ("Consolas", 13, "bold")
NAVY = "#0f2a44"
BG = "#f4f6f9"
ACCENT = "#1f7aed"
GREEN = "#107c41"
RED = "#c0392b"


class Desk(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vol Desk Pro — 7DTE OTM/ATM trainer (98–102)")
        self.geometry("1320x780")
        self.configure(bg=BG)
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self.style.configure("Header.TLabel", background=NAVY, foreground="white", font=("Segoe UI", 10))
        self.style.configure("HeaderBig.TLabel", background=NAVY, foreground="white", font=("Consolas", 16, "bold"))
        self.style.configure("TLabel", font=FONT)
        self.style.configure("TLabelframe", background=BG, font=("Segoe UI", 9, "bold"))
        self.style.configure("TLabelframe.Label", background=BG)
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        self.style.configure("Treeview", font=("Consolas", 10), rowheight=24)
        self.eng = Engine()
        self.running = False
        self.space_down = False
        self.hist_S, self.hist_pnl, self.hist_fair = [], [], []
        self._build()
        self.refresh_labels()

    # ---------- layout ----------
    def _build(self):
        # header bar
        hdr = tk.Frame(self, bg=NAVY, padx=12, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="SPOT", bg=NAVY, fg="#9fb3c8", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        self.spot_v = tk.Label(hdr, text="100.00", bg=NAVY, fg="white", font=("Consolas", 18, "bold"))
        self.spot_v.grid(row=1, column=0, padx=(0, 18), sticky="w")
        tk.Label(hdr, text="QUOTE IV  (FAIR)", bg=NAVY, fg="#9fb3c8", font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w")
        self.iv_v = tk.Label(hdr, text="20.0  (20.0)", bg=NAVY, fg="white", font=("Consolas", 18, "bold"))
        self.iv_v.grid(row=1, column=1, padx=(0, 18), sticky="w")
        tk.Label(hdr, text="TOTAL P&L", bg=NAVY, fg="#9fb3c8", font=("Segoe UI", 8, "bold")).grid(row=0, column=2, sticky="w")
        self.pnl_v = tk.Label(hdr, text="+0.00", bg=NAVY, fg="#7CFC98", font=("Consolas", 18, "bold"))
        self.pnl_v.grid(row=1, column=2, padx=(0, 18), sticky="w")
        tk.Label(hdr, text="TICK", bg=NAVY, fg="#9fb3c8", font=("Segoe UI", 8, "bold")).grid(row=0, column=3, sticky="w")
        self.tick_v = tk.Label(hdr, text="0", bg=NAVY, fg="white", font=("Consolas", 14, "bold"))
        self.tick_v.grid(row=1, column=3, sticky="w")
        hdr.grid_columnconfigure(4, weight=1)
        self.btn_run = ttk.Button(hdr, text="▶  Start", command=self.toggle, width=12)
        self.btn_run.grid(row=0, column=5, rowspan=2, padx=4)
        ttk.Button(hdr, text="Reset", command=self.reset, width=10).grid(row=0, column=6, rowspan=2, padx=4)

        # control groups
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")

        g1 = ttk.Labelframe(bar, text=" Vol curve ")
        g1.pack(side="left", padx=4)
        ttk.Button(g1, text="IV −", width=6, command=lambda: self.bump_iv(-1)).grid(row=0, column=0, padx=2, pady=2)
        ttk.Button(g1, text="IV +", width=6, command=lambda: self.bump_iv(+1)).grid(row=0, column=1, padx=2, pady=2)
        ttk.Label(g1, text="step").grid(row=0, column=2, padx=(6, 2))
        self.step_cb = ttk.Combobox(g1, values=[str(s) for s in VOL_STEPS], width=5, state="readonly")
        self.step_cb.set("0.1")
        self.step_cb.grid(row=0, column=3, padx=2)

        g2 = ttk.Labelframe(bar, text=" Market ")
        g2.pack(side="left", padx=4)
        ttk.Label(g2, text="sigma%").grid(row=0, column=0, padx=2)
        self.sig = tk.Spinbox(g2, from_=5, to=80, increment=1, width=5, command=self.sync_params, font=MONO)
        self.sig.delete(0, "end"); self.sig.insert(0, "20")
        self.sig.grid(row=0, column=1, padx=2)

        g3 = ttk.Labelframe(bar, text=" Quotes ")
        g3.pack(side="left", padx=4)
        ttk.Label(g3, text="spread").grid(row=0, column=0, padx=2)
        self.spr = tk.Spinbox(g3, from_=0.02, to=2.0, increment=0.01, width=6, command=self.sync_params, font=MONO)
        self.spr.delete(0, "end"); self.spr.insert(0, str(self.eng.cfg.spread))
        self.spr.grid(row=0, column=1, padx=2)
        ttk.Label(g3, text="toxic%").grid(row=0, column=2, padx=(6, 2))
        self.tox = tk.Spinbox(g3, from_=0, to=80, increment=5, width=5, command=self.sync_params, font=MONO)
        self.tox.delete(0, "end"); self.tox.insert(0, "30")
        self.tox.grid(row=0, column=3, padx=2)
        ttk.Label(g3, text="skw").grid(row=0, column=4, padx=(6, 2))
        self.skw = tk.Spinbox(g3, from_=0.0, to=0.10, increment=0.005, width=5, command=self.sync_params, font=MONO)
        self.skw.delete(0, "end"); self.skw.insert(0, str(self.eng.cfg.skew_per_lot))
        self.skw.grid(row=0, column=5, padx=2)

        g4 = ttk.Labelframe(bar, text=" Risk ")
        g4.pack(side="left", padx=4)
        ttk.Label(g4, text="dLim").grid(row=0, column=0, padx=2)
        self.dlim = tk.Spinbox(g4, from_=0.5, to=20, increment=0.5, width=5, command=self.sync_params, font=MONO)
        self.dlim.delete(0, "end"); self.dlim.insert(0, str(self.eng.cfg.delta_limit))
        self.dlim.grid(row=0, column=1, padx=2)
        ttk.Label(g4, text="maxQ").grid(row=0, column=2, padx=(6, 2))
        self.maxq = tk.Spinbox(g4, from_=1, to=50, increment=1, width=5, command=self.sync_params, font=MONO)
        self.maxq.delete(0, "end"); self.maxq.insert(0, str(self.eng.cfg.max_q))
        self.maxq.grid(row=0, column=3, padx=2)
        self.ah = tk.BooleanVar(value=True)
        ttk.Checkbutton(g4, text="hedge", variable=self.ah, command=self.sync_params).grid(row=0, column=4, padx=6)
        self.af = tk.BooleanVar(value=True)
        ttk.Checkbutton(g4, text="autofill", variable=self.af, command=self.sync_params).grid(row=0, column=5, padx=2)

        g5 = ttk.Labelframe(bar, text=" Actions ")
        g5.pack(side="left", padx=4)
        ttk.Button(g5, text="Hedge flat", command=self.hedge_flat, width=10).grid(row=0, column=0, padx=2)
        ttk.Button(g5, text="Reload (R)", command=self.reload_all, width=10).grid(row=0, column=1, padx=2)
        ttk.Button(g5, text="Flatten opts", command=self.flatten_opts, width=11).grid(row=0, column=2, padx=2)
        ttk.Button(g5, text="Edit MAN", command=self.edit_selected_man, width=9).grid(row=0, column=3, padx=2)

        # chain table
        cols = ("inst", "iv", "theo", "bid", "ask", "bL", "aL", "size", "mode", "q", "delta", "sprd", "net")
        heads = ("Instrument", "IV%", "Theo", "Bid", "Ask", "BidL", "AskL", "Size", "Mode", "Pos", "Δ pos", "Sprd", "Net")
        widths = (80, 60, 70, 70, 70, 50, 50, 50, 62, 52, 72, 70, 70)
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for k, h, w in zip(cols, heads, widths):
            self.tree.heading(k, text=h)
            self.tree.column(k, width=w, anchor="center")
        self.tree.pack(fill="x", padx=8, pady=(2, 4))
        self.tree.bind("<Button-1>", lambda e: self.chain_click(e, -1))
        self.tree.bind("<Button-3>", lambda e: self.chain_click(e, +1))
        self.bind_all("<KeyPress-space>", self._space_on)
        self.bind_all("<KeyRelease-space>", self._space_off)
        self.bind_all("<bracketleft>", lambda e: self.bump_iv(-1))
        self.bind_all("<bracketright>", lambda e: self.bump_iv(+1))
        self.bind_all("<r>", lambda e: self.reload_all())
        self.bind_all("<R>", lambda e: self.reload_all())
        self.tree.bind("<Double-Button-1>", self.toggle_mode)
        self.bind("<plus>", lambda e: self.adj_lots(+1))
        self.bind("<minus>", lambda e: self.adj_lots(-1))

        # risk + pnl cards
        cards = ttk.Frame(self, padding=(8, 0))
        cards.pack(fill="x")
        self.risk_v = ttk.Label(cards, font=("Consolas", 11), padding=6, background="white", relief="solid", borderwidth=1)
        self.risk_v.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.money_v = ttk.Label(cards, font=("Consolas", 11, "bold"), padding=6, background="white", relief="solid", borderwidth=1)
        self.money_v.pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Label(self, text="Hold SPACE (IV glows) + click chain  •  [ ] move curve  •  Double-click: OFF → AUTO → MAN  •  +/− size  •  R reload  •  T=7d fixed r=0 hedge=spot",
                  foreground="#6b7280", background=BG, font=("Segoe UI", 8)).pack(fill="x", padx=8, pady=(4, 0))

        # charts
        fig = Figure(figsize=(11, 3.0), dpi=100)
        fig.patch.set_facecolor(BG)
        self.ax1 = fig.add_subplot(121); self.ax2 = fig.add_subplot(122)
        for ax in (self.ax1, self.ax2):
            ax.set_facecolor("white"); ax.grid(True, alpha=0.25); ax.tick_params(labelsize=8)
        self.ax1.set_title("Spot", fontsize=10, fontweight="bold")
        self.ax2.set_title("Total P&L", fontsize=10, fontweight="bold")
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=4)

        self.log = tk.Text(self, height=4, font=("Consolas", 9), bg="#0f2a44", fg="#d1fae5",
                           insertbackground="white", relief="flat")
        self.log.pack(fill="x", padx=8, pady=(0, 8))

    # ---------- controls ----------
    def vol_step(self):
        try:
            return float(self.step_cb.get())
        except Exception:
            return 0.1

    def bump_iv(self, d):
        self.eng.cfg.iv = max(0.01, self.eng.cfg.iv + d * self.vol_step() / 100.0)
        self.eng.refresh_theos()
        self.refresh_labels()

    def _space_on(self, ev=None):
        self.space_down = True
        try:
            self.iv_v.config(bg="#107c41")
        except Exception:
            pass

    def _space_off(self, ev=None):
        self.space_down = False
        try:
            self.iv_v.config(bg=NAVY)
        except Exception:
            pass

    def chain_click(self, ev, d):
        if self.space_down:
            self.bump_iv(d)
            return "break"

    def toggle_mode(self, ev):
        row = self.tree.identify_row(ev.y)
        if not row:
            return
        name = self.tree.item(row)["values"][0]
        cur = self.eng.cfg.modes[name]
        nxt = {"OFF": "AUTO", "AUTO": "MAN", "MAN": "OFF"}.get(cur, "AUTO")
        self.eng.cfg.modes[name] = nxt
        if nxt == "MAN":
            t = self.eng.theo[name]
            h = self.eng.cfg.spread / 2.0
            self.eng.cfg.man_bid[name] = round(max(t - h, 0.01), 2)
            self.eng.cfg.man_ask[name] = round(t + h, 2)
            self.edit_manual(name)
        self.refresh_labels()

    def edit_selected_man(self):
        n = self.sel_name()
        if self.eng.cfg.modes.get(n) != "MAN":
            self.log.insert("end", f"{n} is {self.eng.cfg.modes.get(n)} — double-click twice to get MAN first\n")
            self.log.see("end")
            return
        self.edit_manual(n)

    def edit_manual(self, name):
        pop = tk.Toplevel(self)
        pop.title(f"Manual quote {name}  (theo {self.eng.theo[name]:.2f})")
        pop.configure(bg="white")
        ttk.Label(pop, text="bid", background="white").grid(row=0, column=0, padx=8, pady=6)
        ttk.Label(pop, text="ask", background="white").grid(row=1, column=0, padx=8, pady=6)
        b = ttk.Entry(pop); a = ttk.Entry(pop)
        b.insert(0, str(self.eng.cfg.man_bid.get(name, "")))
        a.insert(0, str(self.eng.cfg.man_ask.get(name, "")))
        b.grid(row=0, column=1, padx=8); a.grid(row=1, column=1, padx=8)

        def save():
            try:
                bb, aa = float(b.get()), float(a.get())
                if bb > 0 and aa > bb:
                    self.eng.cfg.man_bid[name] = bb
                    self.eng.cfg.man_ask[name] = aa
                    pop.destroy()
                    self.refresh_labels()
            except Exception:
                pass
        ttk.Button(pop, text="Save quote", command=save).grid(row=2, column=0, columnspan=2, pady=8)

    def sel_name(self):
        s = self.tree.selection()
        if s:
            return self.tree.item(s[0])["values"][0]
        return "101C"

    def adj_lots(self, d):
        n = self.sel_name()
        self.eng.cfg.lots[n] = max(0, min(5, int(self.eng.cfg.lots.get(n, 1)) + d))
        if self.eng.cfg.autofill:
            self.eng.reload_lots(n)
        self.refresh_labels()

    def reload_all(self):
        self.eng.reload_lots()
        self.refresh_labels()

    def flatten_opts(self):
        n0 = sum(abs(v) for v in self.eng.q.values())
        self.eng.flatten_options()
        self.log.insert("end", f"TICK {self.eng.tick:5d} | flatten: closed {n0} lots at fair touch (paid spread+fee)\n")
        self.log.see("end")
        self.refresh_labels()

    def sync_params(self):
        c = self.eng.cfg
        try:
            c.sigma = float(self.sig.get()) / 100.0
            c.spread = float(self.spr.get())
            c.p_informed = float(self.tox.get()) / 100.0
            c.delta_limit = float(self.dlim.get())
            c.auto_hedge = bool(self.ah.get())
            c.autofill = bool(self.af.get())
            c.max_q = max(1, int(float(self.maxq.get())))
            c.skew_per_lot = max(0.0, float(self.skw.get()))
        except Exception:
            pass

    def toggle(self):
        self.running = not self.running
        self.btn_run.config(text="⏸  Pause" if self.running else "▶  Start")
        if self.running:
            self.after(1000, self.loop)

    def hedge_flat(self):
        e = self.eng
        d = e.portfolio_greeks()["delta"] + e.hedge_q
        if abs(d) < 1e-9:
            return
        cost = e.cfg.hedge_slip * abs(d)
        e.hedge_q -= d
        e.hedge_cash += d * e.S - cost
        self.log.insert("end", f"TICK {e.tick:5d} | manual hedge {-d:+.2f} @ {e.S:.2f} (slip {cost:.2f})\n")
        self.log.see("end")
        self.refresh_labels()

    def reset(self):
        import random
        self.running = False
        self.btn_run.config(text="▶  Start")
        seed = random.randint(0, 999999)
        self.eng.reset(seed=seed)
        self.hist_S.clear(); self.hist_pnl.clear(); self.hist_fair.clear()
        self.log.delete("1.0", "end")
        self.log.insert("end", f"TICK {0:5d} | reset: seed={seed}  sigma={self.eng.cfg.sigma:.0%}  fair=20.0\n")
        self.refresh_labels(); self.draw()

    # ---------- loop ----------
    def loop(self):
        if not self.running:
            return
        self.sync_params()
        fills, hmsg = self.eng.step()
        for f in fills:
            toxic = "*" in str(f[1])
            tag = "TOXIC" if toxic else "flow"
            side = "BUY" if "BUY" in str(f[1]) else "SELL"
            self.log.insert("end", f"TICK {self.eng.tick:5d} | {f[0]:5s} {tag:5s} {side} x{f[2]} @ {f[3]:.2f}\n")
        if hmsg:
            self.log.insert("end", f"TICK {self.eng.tick:5d} | {hmsg}\n")
        if self.eng.settle_if_expired():
            self.log.insert("end", f"TICK {self.eng.tick:5d} | EXPIRED — settled to intrinsic, book flat. Reset for a fresh week.\n")
            self.running = False
            self.btn_run.config(text="▶  Start")
        self.log.see("end")
        while int(self.log.index("end-1c").split(".")[0]) > 400:
            self.log.delete("1.0", "2.0")
        self.hist_S.append(self.eng.S)
        self.hist_pnl.append(self.eng.total_pnl())
        self.hist_fair.append(self.eng.fair_iv * 100.0)
        self.refresh_labels(); self.draw()
        self.after(1000, self.loop)

    def refresh_labels(self):
        e = self.eng
        tot = e.total_pnl()
        self.spot_v.config(text=f"{e.S:.2f}")
        self.iv_v.config(text=f"{e.cfg.iv*100:.1f}  ({e.fair_iv*100:.1f})")
        self.pnl_v.config(text=f"{tot:+.2f}", fg="#7CFC98" if tot >= 0 else "#ff9d9d")
        self.tick_v.config(text=f"{e.tick}  T-{e.T_live()*365:.2f}d")
        for i in self.tree.get_children():
            self.tree.delete(i)
        for name, K, cp in INSTRUMENTS:
            bid, ask = e.quotes(name)
            g = e.fair_greeks[name]
            q = e.q[name]
            pos_d = q * g["delta"]
            mode = e.cfg.modes.get(name)
            iv_show = f"{e.quote_iv(name)*100:.1f}" if mode != "MAN" else "man"
            bl, al = e.work_bid.get(name, 0), e.work_ask.get(name, 0)
            if mode == "OFF":
                b_show = a_show = "—"
            else:
                b_show = f"{bid:.2f}" if bid else "—"
                a_show = f"{ask:.2f}" if ask else "—"
            self.tree.insert("", "end", values=(
                name, iv_show, f"{e.theo[name]:.2f}", b_show, a_show,
                bl, al, e.cfg.lots.get(name, 1), mode, q, f"{pos_d:+.2f}",
                f"{e.spread_by.get(name, 0.0):+.2f}", f"{e.strike_full_pnl(name):+.2f}"))
            if mode == "OFF":
                tag = "off"
            elif abs(q) >= e.cfg.max_q and q != 0:
                tag = "capped"
            else:
                tag = "flat" if q == 0 else ("long" if q > 0 else "short")
            kids = self.tree.get_children()
            self.tree.item(kids[-1], tags=(tag,))
        self.tree.tag_configure("flat", background="white", foreground="#111827")
        self.tree.tag_configure("long", background="#e6f4ea", foreground="#14532d")
        self.tree.tag_configure("short", background="#fdecea", foreground="#7f1d1d")
        self.tree.tag_configure("capped", background="#fff3cd", foreground="#92400e")
        self.tree.tag_configure("off", background="#f3f4f6", foreground="#9ca3af")
        pg = e.portfolio_greeks()
        net_d = pg["delta"] + e.hedge_q
        self.risk_v.config(
            text=(f"HEDGE {e.hedge_q:+.1f}   NET Δ {net_d:+.2f} (opt {pg['delta']:+.2f})   "
                  f"Γ {pg['gamma']:+.2f}   ν {pg['vega']:+.2f}   θ {pg['theta']:+.2f}/d"))
        hv = e.hedge_cash + e.hedge_q * e.S
        self.money_v.config(
            text=(f"CASH {e.cash:+.2f}   OPT {e.options_value():+.2f}   HEDGE {hv:+.2f}   TOTAL {tot:+.2f}"))

    def draw(self):
        self.ax1.clear(); self.ax2.clear()
        self.ax1.set_title("Spot", fontsize=10, fontweight="bold")
        self.ax2.set_title("Total P&L", fontsize=10, fontweight="bold")
        if self.hist_S:
            self.ax1.plot(self.hist_S, color=ACCENT, lw=1.6)
            self.ax1.ticklabel_format(useOffset=False)
            n = len(self.hist_pnl)
            self.ax2.plot(self.hist_pnl, color=GREEN if self.hist_pnl[-1] >= 0 else RED, lw=1.6)
            self.ax2.axhline(0, color="black", lw=0.8, alpha=0.6)
            self.ax2.set_xlim(0, max(n, 50))
        self.canvas.draw()


if __name__ == "__main__":
    Desk().mainloop()
