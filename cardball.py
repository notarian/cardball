#!/usr/bin/env python3
"""CardBall - a Strat-O-Matic-style baseball sim. Real MLB teams; fictional players, or real players from Retrosheet data (see build_season.py).
Run:  python3 cardball.py     (needs only Python 3 with tkinter)

How a plate appearance works (the card-game way):
  1. Roll a d20: 1-10 -> the BATTER's card is used, 11-20 -> the PITCHER's card.
  2. Roll two d6 to pick one of 36 slots on that card -> the outcome.
  3. Base runners advance with some dice-driven randomness.
"""
import glob
import json
import math
import os
import random
import sys
import zlib
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

TEAMS = [  # (city, nickname, primary color, secondary color)
    ("Baltimore", "Orioles", "#DF4601", "#000000"), ("Boston", "Red Sox", "#BD3039", "#0C2340"),
    ("New York", "Yankees", "#0C2340", "#FFFFFF"), ("Tampa Bay", "Rays", "#092C5C", "#8FBCE6"),
    ("Toronto", "Blue Jays", "#134A8E", "#E8291C"), ("Chicago", "White Sox", "#27251F", "#C4CED4"),
    ("Cleveland", "Guardians", "#00385D", "#E50022"), ("Detroit", "Tigers", "#0C2340", "#FA4616"),
    ("Kansas City", "Royals", "#004687", "#BD9B60"), ("Minnesota", "Twins", "#002B5C", "#D31145"),
    ("Houston", "Astros", "#002D62", "#EB6E1F"), ("Los Angeles", "Angels", "#BA0021", "#003263"),
    ("Sacramento", "Athletics", "#003831", "#EFB21E"), ("Seattle", "Mariners", "#0C2C56", "#005C5C"),
    ("Texas", "Rangers", "#003278", "#C0111F"), ("Atlanta", "Braves", "#CE1141", "#13274F"),
    ("Miami", "Marlins", "#00A3E0", "#EF3340"), ("New York", "Mets", "#002D72", "#FF5910"),
    ("Philadelphia", "Phillies", "#E81828", "#002D72"), ("Washington", "Nationals", "#AB0003", "#14225A"),
    ("Chicago", "Cubs", "#0E3386", "#CC3433"), ("Cincinnati", "Reds", "#C6011F", "#000000"),
    ("Milwaukee", "Brewers", "#12284B", "#FFC52F"), ("Pittsburgh", "Pirates", "#27251F", "#FDB827"),
    ("St. Louis", "Cardinals", "#C41E3A", "#0C2340"), ("Arizona", "Diamondbacks", "#A71930", "#E3D4AD"),
    ("Colorado", "Rockies", "#33006F", "#C4CED4"), ("Los Angeles", "Dodgers", "#005A9C", "#FFFFFF"),
    ("San Diego", "Padres", "#2F241D", "#FFC425"), ("San Francisco", "Giants", "#FD5A1E", "#27251F"),
]
FIRST = ["Jack", "Miguel", "Tommy", "Duke", "Hank", "Rafael", "Chuck", "Dmitri", "Walt", "Cal",
         "Bobby", "Ozzie", "Lefty", "Marco", "Sal", "Terrence", "Eddie", "Nolan", "Pete", "Gus"]
LAST = ["Boudreaux", "Kowalski", "Fitzgerald", "Okafor", "Delgado", "Pemberton", "Nakamura",
        "Brannigan", "Oyelaran", "Castellano", "Hargrove", "Vasquez", "Lindqvist", "Mahoney",
        "Tran", "Rutherford", "Abernathy", "Santoro", "Jablonski", "McBride", "Quigley", "Sorensen"]
HIT_OUTCOMES = ["K", "BB", "HR", "3B", "2B", "1B"]
TEXT = {"K": "strikes out", "BB": "draws a walk", "HR": "HOMERS!", "3B": "triples",
        "2B": "doubles", "1B": "singles", "GO": "grounds out", "FO": "flies out"}


def make_card(rates, rng=None):
    """Build a 36-slot card from outcome rates; remaining slots are outs (GO/FO).
    With rng (real-player mode) slot counts are rounded stochastically, so rates average out correctly."""
    card = []
    for k in HIT_OUTCOMES:
        x = rates[k] * 36
        n = round(x) if rng is None else int(x) + (rng.random() < x - int(x))
        card += [k] * max(0, n)
    r = rng or random
    while len(card) > 36:
        card.remove(max(("K", "1B", "BB"), key=card.count))
    while len(card) < 36:
        card.append("GO" if r.random() < 0.5 else "FO")
    r.shuffle(card)
    return card


class Player:
    def __init__(self, name, card, pitcher=False, info=""):
        self.name, self.card, self.pitcher, self.info = name, card, pitcher, info
        self.reset()

    def reset(self):
        self.ab = self.h = self.hr = self.rbi = self.bb = self.k = 0

    def line(self):
        return f"{self.name:<18}{self.ab:>3}{self.h:>3}{self.hr:>3}{self.rbi:>3}{self.bb:>3}"


def new_name(used):
    while True:
        n = f"{random.choice(FIRST)} {random.choice(LAST)}"
        if n not in used:
            used.add(n)
            return n


def make_team(city, nick, c1, c2):
    used = set()
    lineup = []
    for _ in range(9):
        r = random.uniform
        rates = {"K": r(.12, .28), "BB": r(.05, .13), "HR": r(.01, .07), "3B": r(.002, .012),
                 "2B": r(.035, .07), "1B": r(.12, .2)}
        lineup.append(Player(new_name(used), make_card(rates)))

    def pitcher(strong):
        r = random.uniform
        rates = {"K": r(.18, .30) if strong else r(.14, .24), "BB": r(.04, .09),
                 "HR": r(.01, .035), "3B": .002, "2B": r(.03, .05), "1B": r(.11, .16)}
        return Player(new_name(used), make_card(rates), True)
    return {"city": city, "nick": nick, "c1": c1, "c2": c2, "lineup": lineup, "rotation": [pitcher(True)], "pen": [pitcher(False)]}


class Game:
    def __init__(self, away, home):
        self.t = [away, home]
        for t in self.t:
            for p in t["lineup"] + t["rotation"] + t["pen"]:
                p.reset()
        self.line = [[0], []]
        self.inning, self.top, self.outs = 1, True, 0
        self.bases = [None] * 3
        self.spot = [0, 0]
        self.starter = [random.choice(t["rotation"]) for t in self.t]
        self.pit = list(self.starter)
        self.pen_i = [0, 0]
        self.bf = [0, 0]          # batters faced by current pitcher
        self.pruns = [0, 0]       # runs allowed by current pitcher
        self.hits = [0, 0]
        self.over = False
        self.last_roll = ""
        self.last = None

    @property
    def bat(self):
        return 0 if self.top else 1

    def runs(self, i):
        return sum(self.line[i])

    def step(self):
        """Play one plate appearance. Returns list of log lines."""
        b, f = self.bat, 1 - self.bat
        log = []
        team_f = self.t[f]
        cur = self.pit[f]
        tired = (self.bf[f] >= 27 or self.pruns[f] >= 6) if cur is self.starter[f] else self.bf[f] >= 12
        if tired and self.pen_i[f] < len(team_f["pen"]):
            self.pit[f] = cur = team_f["pen"][self.pen_i[f]]
            self.pen_i[f] += 1
            self.bf[f] = self.pruns[f] = 0
            log.append(f"-- {team_f['nick']} bring in {cur.name} from the bullpen.")
        batter = self.t[b]["lineup"][self.spot[b]]
        self.spot[b] = (self.spot[b] + 1) % 9
        self.bf[f] += 1

        d20 = random.randint(1, 20)
        d1, d2 = random.randint(1, 6), random.randint(1, 6)
        use_bat = d20 <= 10
        card = (batter if use_bat else cur).card
        res = card[(d1 - 1) * 6 + (d2 - 1)]
        self.last_roll = (f"d20={d20} -> {'batter' if use_bat else 'pitcher'} card | "
                          f"2d6={d1}+{d2} -> {res}")
        self.last = {"d20": d20, "d1": d1, "d2": d2, "use_bat": use_bat, "res": res,
                     "idx": (d1 - 1) * 6 + (d2 - 1), "batter": batter, "pitcher": cur, "bt": b}
        runs, desc = self.resolve(res, batter)
        batter.rbi += runs if desc != "dp" else 0
        if res != "BB":
            batter.ab += 1
        if res in ("1B", "2B", "3B", "HR"):
            batter.h += 1
            self.hits[b] += 1
        if res == "HR":
            batter.hr += 1
        if res == "BB":
            batter.bb += 1
        if res == "K":
            batter.k += 1
        self.line[b][-1] += runs
        self.pruns[f] += runs
        txt = "grounds into a double play" if desc == "dp" else TEXT[res]
        log.append(f"{batter.name} {txt}." + (f"  {runs} run{'s' if runs > 1 else ''} score." if runs else ""))

        # walk-off
        if (not self.top and self.inning >= 9 and self.runs(1) > self.runs(0)):
            self.over = True
            log.append(f"*** FINAL: {self.t[1]['nick']} win on a walk-off! ***")
            return log
        if self.outs >= 3:
            self.end_half(log)
        return log

    def end_half(self, log):
        self.outs, self.bases = 0, [None] * 3
        if self.top:
            if self.inning >= 9 and self.runs(1) > self.runs(0):
                self.over = True
            else:
                self.top = False
                self.line[1].append(0)
        else:
            if self.inning >= 9 and self.runs(0) != self.runs(1):
                self.over = True
            else:
                self.inning += 1
                self.top = True
                self.line[0].append(0)
        if self.over:
            a, h = self.runs(0), self.runs(1)
            w = self.t[0 if a > h else 1]
            log.append(f"*** FINAL: {self.t[0]['nick']} {a}, {self.t[1]['nick']} {h}. "
                       f"{w['city']} {w['nick']} win! ***")
        else:
            log.append(f"=== {'Top' if self.top else 'Bottom'} of inning {self.inning} ===")

    def resolve(self, res, batter):
        bs, new, runs, R = self.bases, [None] * 3, 0, random.random
        if res == "HR":
            runs = 1 + sum(x is not None for x in bs)
        elif res == "3B":
            runs = sum(x is not None for x in bs)
            new[2] = batter
        elif res == "2B":
            runs = (bs[1] is not None) + (bs[2] is not None)
            if bs[0]:
                if R() < .4:
                    runs += 1
                else:
                    new[2] = bs[0]
            new[1] = batter
        elif res == "1B":
            runs = bs[2] is not None
            if bs[1]:
                if R() < .6:
                    runs += 1
                else:
                    new[2] = bs[1]
            if bs[0]:
                if new[2] is None and R() < .25:
                    new[2] = bs[0]
                else:
                    new[1] = bs[0]
            new[0] = batter
        elif res == "BB":
            new = list(bs)
            if bs[0]:
                if bs[1]:
                    runs += bs[2] is not None
                    new[2] = bs[1]
                new[1] = bs[0]
            new[0] = batter
        elif res == "K":
            self.outs += 1
            new = list(bs)
        elif res == "GO":
            if bs[0] and self.outs < 2 and R() < .55:
                self.outs += 2
                if self.outs < 3:
                    runs = bs[2] is not None
                    new[2] = bs[1]
                self.bases = new
                return int(runs), "dp"
            self.outs += 1
            new = list(bs)
            if self.outs < 3:
                if bs[0]:
                    new[0] = None
                    if bs[1]:
                        runs += bs[2] is not None
                        new[2] = bs[1]
                    new[1] = bs[0]
                elif bs[2] and R() < .6:
                    runs, new[2] = 1, None
                elif bs[1] and not bs[2] and R() < .4:
                    new[2], new[1] = bs[1], None
        elif res == "FO":
            self.outs += 1
            new = list(bs)
            if self.outs < 3:
                if bs[2] and R() < .65:
                    runs, new[2] = 1, None
                elif bs[1] and not bs[2] and R() < .2:
                    new[2], new[1] = bs[1], None
        self.bases = new
        return int(runs), ""


# ----------------------------------------------------------------------------- real seasons
CREDIT = ("The information used here was obtained free of charge from and is copyrighted by Retrosheet. "
          "Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.")
ERA_TEAMS = {  # Retrosheet id -> (city, nickname, primary, secondary), 1986-era names
    "BAL": ("Baltimore", "Orioles", "#DF4601", "#000000"), "BOS": ("Boston", "Red Sox", "#BD3039", "#0C2340"),
    "CAL": ("California", "Angels", "#BA0021", "#003263"), "CHA": ("Chicago", "White Sox", "#0C2340", "#C8102E"),
    "CLE": ("Cleveland", "Indians", "#E31937", "#0C2340"), "DET": ("Detroit", "Tigers", "#0C2340", "#FA4616"),
    "KCA": ("Kansas City", "Royals", "#004687", "#BD9B60"), "MIL": ("Milwaukee", "Brewers", "#12284B", "#FFC52F"),
    "MIN": ("Minnesota", "Twins", "#002B5C", "#D31145"), "NYA": ("New York", "Yankees", "#0C2340", "#FFFFFF"),
    "OAK": ("Oakland", "Athletics", "#003831", "#EFB21E"), "SEA": ("Seattle", "Mariners", "#0C2C56", "#FFC425"),
    "TEX": ("Texas", "Rangers", "#003278", "#C0111F"), "TOR": ("Toronto", "Blue Jays", "#134A8E", "#E8291C"),
    "ATL": ("Atlanta", "Braves", "#CE1141", "#13274F"), "CHN": ("Chicago", "Cubs", "#0E3386", "#CC3433"),
    "CIN": ("Cincinnati", "Reds", "#C6011F", "#000000"), "HOU": ("Houston", "Astros", "#F4871E", "#002D62"),
    "LAN": ("Los Angeles", "Dodgers", "#005A9C", "#FFFFFF"), "MON": ("Montreal", "Expos", "#003DA5", "#E31937"),
    "NYN": ("New York", "Mets", "#002D72", "#FF5910"), "PHI": ("Philadelphia", "Phillies", "#E81828", "#002D72"),
    "PIT": ("Pittsburgh", "Pirates", "#27251F", "#FDB827"), "SDN": ("San Diego", "Padres", "#4B2E1E", "#FEC325"),
    "SFN": ("San Francisco", "Giants", "#FD5A1E", "#27251F"), "SLN": ("St. Louis", "Cardinals", "#C41E3A", "#0C2340"),
}


def _rates(d, n):
    n = max(n, 1)
    return {"K": d["k"] / n, "BB": (d["w"] + d["hbp"]) / n, "HR": d["hr"] / n, "3B": d["t"] / n,
            "2B": d["d"] / n, "1B": (d["h"] - d["d"] - d["t"] - d["hr"]) / n}


def _real_player(p, league, pitcher):
    n = p["bfp"] if pitcher else p["pa"]
    pr, m = _rates(p, n), (150 if pitcher else 60)       # regress small samples toward league average
    rates = {k: (pr[k] * n + m * league[k]) / (n + m) for k in pr}
    card = make_card(rates, random.Random(zlib.crc32(p["id"].encode())))
    if pitcher:
        info = f"{p['er'] * 27 / max(p['ipouts'], 1):.2f} ERA"
    else:
        info = f"{p['h'] / max(p['ab'], 1):.3f}".lstrip("0") + f", {p['hr']} HR"
    return Player(p["name"], card, pitcher, info)


def load_season(path):
    data = json.load(open(path, encoding="utf-8"))
    lb, lp = data["league"]["bat"], data["league"]["pit"]
    lbr, lpr = _rates(lb, lb["pa"]), _rates(lp, lp["bfp"])
    teams = []
    for tid, t in data["teams"].items():
        city, nick, c1, c2 = ERA_TEAMS.get(tid, (tid, tid, "#555555", "#FFFFFF"))
        teams.append({"city": city, "nick": nick, "c1": c1, "c2": c2,
                      "lineup": [_real_player(p, lbr, False) for p in t["lineup"]],
                      "rotation": [_real_player(p, lpr, True) for p in t["rotation"]],
                      "pen": [_real_player(p, lpr, True) for p in t["pen"]]})
    teams.sort(key=lambda t: (t["city"], t["nick"]))
    return teams, data["season"]


def load_teams():
    """Use season_*.json next to this script (or given on the command line); else fictional players."""
    here = os.path.dirname(os.path.abspath(__file__))
    paths = sys.argv[1:2] or sorted(glob.glob(os.path.join(here, "season_*.json")))
    if paths:
        return load_season(paths[0])
    return [make_team(*t) for t in TEAMS], None


# ----------------------------------------------------------------------------- GUI
def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda v: v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)


def _ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + .05) / (lo + .05)


def ctext(c1, c2):
    """Readable text color on c1: the team's secondary if contrast is good, else black/white."""
    if _ratio(c1, c2) >= 3.5:
        return c2
    return "#ffffff" if _ratio(c1, "#ffffff") >= _ratio(c1, "#000000") else "#000000"


BASE_W, BASE_H = 1130, 700      # design size at 100% scale


class App:
    PIPS = {1: [(1, 1)], 2: [(0, 0), (2, 2)], 3: [(0, 0), (1, 1), (2, 2)],
            4: [(0, 0), (2, 0), (0, 2), (2, 2)], 5: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)],
            6: [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)]}
    COLORS = {"HR": "#e55b5b", "3B": "#f0a04b", "2B": "#e8c84a", "1B": "#7fd06b",
              "BB": "#6bb7e8", "K": "#b0b0b0", "GO": "#d9c3a0", "FO": "#d9c3a0"}

    def __init__(self, root):
        self.root = root
        self.game, self.auto = None, False
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.s = max(1.0, min(3.5, round(min(sw * .94 / BASE_W, sh * .85 / BASE_H), 1)))
        self.teams, self.year = load_teams()
        root.title(f"CardBall {self.year}" if self.year else "CardBall")
        self.names = [f"{t['city']} {t['nick']}".strip() for t in self.teams]
        self.f_ui = tkfont.Font(family="Helvetica", size=11)
        self.f_mono = tkfont.Font(family="Courier", size=12, weight="bold")
        self.f_log = tkfont.Font(family="Helvetica", size=11)
        self.f_box = tkfont.Font(family="Courier", size=10)
        self.f_small = tkfont.Font(family="Helvetica", size=8)
        self.style = ttk.Style()

        top = ttk.Frame(root, padding=6)
        top.pack(fill="x")
        d = [n if n in self.names else self.names[i] for i, n in enumerate(("New York Mets", "Boston Red Sox"))]
        self.away_var, self.home_var = tk.StringVar(value=d[0]), tk.StringVar(value=d[1])
        self.sw = []
        for lbl, var in (("Away:", self.away_var), ("Home:", self.home_var)):
            ttk.Label(top, text=lbl).pack(side="left")
            cb = ttk.Combobox(top, textvariable=var, values=self.names, width=24, state="readonly", font=self.f_ui)
            cb.pack(side="left", padx=(4, 2))
            cb.bind("<<ComboboxSelected>>", lambda e: self.update_swatches())
            pair = [tk.Label(top, width=2) for _ in range(2)]   # primary / secondary color swatches
            for p in pair:
                p.pack(side="left")
            ttk.Label(top, text=" ").pack(side="left")
            self.sw.append(pair)
        ttk.Button(top, text="New Game", command=self.new_game).pack(side="left", padx=6)
        ttk.Button(top, text="Random Matchup" if self.year else "Re-roll Teams", command=self.reroll).pack(side="left")

        sb = tk.Frame(root)
        sb.pack(fill="x", padx=6)
        self.score = [tk.Label(sb, font=self.f_mono, justify="left", anchor="w", bg="#101820", fg="#f2c94c")
                      for _ in range(4)]
        for l in self.score:
            l.pack(fill="x")

        mid = ttk.Frame(root, padding=6)
        mid.pack(fill="both", expand=True)
        left = ttk.Frame(mid)
        left.pack(side="left", anchor="n")
        self.canvas = tk.Canvas(left, bg="#2e6b34", highlightthickness=0)
        self.canvas.pack()
        self.matchup = tk.Label(left, font=self.f_ui, justify="left")
        self.matchup.pack(anchor="w", pady=4)
        self.roll = tk.Label(left, font=self.f_box, fg="#555", justify="left")
        self.roll.pack(anchor="w")

        right = ttk.Frame(mid)
        right.pack(side="left", fill="both", expand=True, padx=8)
        self.log = tk.Text(right, width=44, height=12, wrap="word", font=self.f_log)
        self.log.pack(fill="both", expand=True)
        self.box = tk.Text(right, width=44, height=10, font=self.f_box, bg="#f4f4f4")
        self.box.pack(fill="x", pady=(6, 0))
        self.cards = tk.Canvas(mid, bg="#1d2b22", highlightthickness=0)
        self.cards.pack(side="left", anchor="n")

        bot = ttk.Frame(root, padding=6)
        bot.pack(fill="x")
        for text, cmd in [("Next Batter", self.next_pa), ("Finish Half-Inning", self.half),
                          ("Auto-Play \u25b6/\u23f8", self.toggle_auto), ("Sim To End", self.sim_end)]:
            ttk.Button(bot, text=text, command=cmd).pack(side="left", padx=3)
        ttk.Label(bot, text="Auto speed:").pack(side="left", padx=(12, 2))
        self.speed = tk.Scale(bot, from_=50, to=1000, orient="horizontal", showvalue=False, length=120)
        self.speed.set(350)
        self.speed.pack(side="left")
        ttk.Button(bot, text="Size +", command=lambda: self.change_scale(.2)).pack(side="right", padx=3)
        self.size_lbl = ttk.Label(bot, text="")
        self.size_lbl.pack(side="right")
        ttk.Button(bot, text="Size \u2212", command=lambda: self.change_scale(-.2)).pack(side="right", padx=3)
        if self.year:
            self.credit = tk.Label(root, font=self.f_small, fg="#555", anchor="w", justify="left", text=CREDIT)
            self.credit.pack(fill="x", padx=8, pady=(0, 4))
        for mod in ("Command", "Control"):
            for key, d in (("plus", .2), ("equal", .2), ("minus", -.2)):
                try:
                    root.bind(f"<{mod}-{key}>", lambda e, d=d: self.change_scale(d))
                except tk.TclError:
                    pass
        self.apply_scale()
        self.new_game()

    # ---- scaling
    def F(self, size, bold=False):
        return ("Helvetica", max(6, int(size * self.s)), "bold" if bold else "normal")

    def change_scale(self, d):
        self.s = max(0.7, min(3.5, round(self.s + d, 1)))
        self.apply_scale()
        self.root.geometry("")          # let the window re-fit its contents

    def apply_scale(self):
        s = self.s
        self.f_ui.configure(size=int(11 * s))
        self.f_mono.configure(size=int(12 * s))
        self.f_log.configure(size=int(11 * s))
        self.f_box.configure(size=int(10 * s))
        self.f_small.configure(size=int(8 * s))
        if hasattr(self, "credit"):
            self.credit.config(wraplength=int(1080 * s))
        for st in ("TButton", "TLabel"):
            self.style.configure(st, font=self.f_ui)
        self.style.configure("TButton", padding=int(3 * s))
        self.root.option_add("*TCombobox*Listbox.font", self.f_ui)
        self.canvas.config(width=int(250 * s), height=int(250 * s))
        self.cards.config(width=int(420 * s), height=int(350 * s))
        self.matchup.config(wraplength=int(250 * s))
        self.roll.config(wraplength=int(250 * s))
        self.speed.config(length=int(120 * s), width=int(14 * s), sliderlength=int(24 * s))
        self.size_lbl.config(text=f" {int(s * 100)}% ")
        if self.game:
            self.refresh()

    # ---- game control
    def reroll(self):
        if self.year:
            a, h = random.sample(self.names, 2)
            self.away_var.set(a)
            self.home_var.set(h)
        else:
            self.teams = [make_team(*t) for t in TEAMS]
        self.new_game()

    def team(self, var):
        return self.teams[self.names.index(var.get())]

    def update_swatches(self):
        for var, pair in zip((self.away_var, self.home_var), self.sw):
            t = self.team(var)
            pair[0].config(bg=t["c1"])
            pair[1].config(bg=t["c2"])

    def new_game(self):
        self.auto = False
        a, h = self.team(self.away_var), self.team(self.home_var)
        if a is h:
            self.home_var.set(self.names[(self.names.index(self.away_var.get()) + 1) % len(self.names)])
            h = self.team(self.home_var)
        self.update_swatches()
        self.game = Game(a, h)
        self.log.delete("1.0", "end")
        self.say([f"Play ball! {a['city']} {a['nick']} at {h['city']} {h['nick']}.",
                  f"SP: {self.game.pit[0].name} vs {self.game.pit[1].name}", "=== Top of inning 1 ==="])
        self.refresh()

    def say(self, lines, b=None):
        g = self.game
        for i in (0, 1):
            self.log.tag_configure(f"t{i}", foreground=g.t[i]["c1"])
        self.log.tag_configure("sys", foreground="#777777")
        for l in lines:
            tag = "sys" if l[:2] in ("==", "**", "--") else (f"t{b}" if b is not None else "")
            self.log.insert("end", l + "\n", tag)
        self.log.see("end")

    def next_pa(self):
        g = self.game
        if g.over:
            self.auto = False
            return
        b = g.bat
        self.say(g.step(), b)
        self.refresh()

    def half(self):
        g = self.game
        key = (g.inning, g.top)
        while not g.over and (g.inning, g.top) == key:
            b = g.bat
            self.say(g.step(), b)
        self.refresh()

    def sim_end(self):
        while not self.game.over:
            b = self.game.bat
            self.say(self.game.step(), b)
        self.refresh()

    def toggle_auto(self):
        self.auto = not self.auto
        if self.auto:
            self.tick()

    def tick(self):
        if self.auto and not self.game.over:
            self.next_pa()
            self.root.after(self.speed.get(), self.tick)

    # ---- drawing
    def refresh(self):
        g = self.game
        n = max(9, len(g.line[0]), len(g.line[1]) if g.line[1] else 0)
        hdr = f"{'':<22}" + "".join(f"{i + 1:>3}" for i in range(n)) + "   R  H"
        rows = []
        for i in (0, 1):
            cells = "".join(f"{(g.line[i][k] if k < len(g.line[i]) else ''):>3}" for k in range(n))
            rows.append(f"{g.t[i]['nick'][:20]:<22}{cells}  {g.runs(i):>2} {g.hits[i]:>2}")
        state = "FINAL" if g.over else f"{'Top' if g.top else 'Bot'} {g.inning}  Outs: {g.outs}"
        for lab, txt in zip(self.score, [hdr] + rows + [state]):
            lab.config(text=txt)
        for i in (0, 1):
            self.score[1 + i].config(bg=g.t[i]["c1"], fg=ctext(g.t[i]["c1"], g.t[i]["c2"]))
        self.draw_field()
        self.draw_card()
        b, f = g.bat, 1 - g.bat
        if not g.over:
            nb = g.t[b]["lineup"][g.spot[b]]
            self.matchup.config(text=f"At bat: {nb.name}  {nb.info}\nPitching: {g.pit[f].name}  {g.pit[f].info}  (BF {g.bf[f]}, R {g.pruns[f]})")
        else:
            self.matchup.config(text="Game over.")
        self.roll.config(text=g.last_roll)
        self.box.delete("1.0", "end")
        for i in (0, 1):
            t = g.t[i]
            self.box.tag_configure(f"t{i}", background=t["c1"], foreground=ctext(t["c1"], t["c2"]))
            self.box.insert("end", f"{t['city'] + ' ' + t['nick']:<44}\n", f"t{i}")
            self.box.insert("end", f"{'':<18}{'AB':>3}{'H':>3}{'HR':>3}{'RBI':>3}{'BB':>3}\n")
            for p in g.t[i]["lineup"]:
                self.box.insert("end", p.line() + "\n")
        self.box.see("1.0")

    def draw_field(self):
        c, s = self.canvas, self.s
        c.delete("all")
        base = {"home": (125, 215), "1": (205, 135), "2": (125, 55), "3": (45, 135)}
        pts = {k: (x * s, y * s) for k, (x, y) in base.items()}
        c.create_polygon(*pts["home"], *pts["1"], *pts["2"], *pts["3"], fill="#b5793e",
                         outline="white", width=max(1, int(2 * s)))
        for i, k in enumerate(("1", "2", "3")):
            x, y = pts[k]
            occ = self.game.bases[i]
            r = 10 * s
            bt = self.game.t[self.game.bat]
            c.create_rectangle(x - r, y - r, x + r, y + r, fill=bt["c1"] if occ else "white",
                               outline=bt["c2"] if occ else "black", width=max(1, int(3 * s)) if occ else 1)
            if occ:
                c.create_text(x, y - 22 * s, text=occ.name.split()[-1], fill="white", font=self.F(9, True))
        c.create_polygon(125 * s, 205 * s, 135 * s, 215 * s, 125 * s, 225 * s, 115 * s, 215 * s, fill="white")
        for i in range(3):
            c.create_oval((10 + i * 22) * s, 10 * s, (28 + i * 22) * s, 28 * s,
                          fill="red" if i < self.game.outs else "#222", outline="white")
        c.create_text(60 * s, 40 * s, text="OUTS", fill="white", font=self.F(8))

    def die(self, c, x, y, v, size=46):
        s = self.s
        x, y, size = x * s, y * s, size * s
        c.create_rectangle(x, y, x + size, y + size, fill="white", outline="black", width=max(1, int(2 * s)))
        for px, py in self.PIPS[v]:
            cx, cy = x + size * (0.25 + 0.25 * px), y + size * (0.25 + 0.25 * py)
            r = 4 * s
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="black")

    def grid(self, c, x0, y0, player, title, used, hit, team):
        s = self.s
        X, Y, cell = x0 * s, y0 * s, 28 * s
        fg = ctext(team["c1"], team["c2"])
        c.create_rectangle(X, Y - 36 * s, X + 6 * cell, Y - 3 * s, fill=team["c1"] if used else "#33403a",
                           outline=team["c2"] if used else "#33403a", width=max(1, int(2 * s)))
        c.create_text(X + 5 * s, Y - 26 * s, anchor="w", text=f"{title} \u00b7 {team['nick']}",
                      fill=fg if used else "#8a8a8a", font=self.F(9, True))
        c.create_text(X + 5 * s, Y - 12 * s, anchor="w", text=player.name + ("  \u25c0 USED" if used else ""),
                      fill=fg if used else "#8a8a8a", font=self.F(9))
        for i in range(6):   # headers: rows = first d6, columns = second d6
            c.create_text(X - 9 * s, Y + i * cell + cell / 2, text=str(i + 1), fill="#aaa", font=self.F(8))
            c.create_text(X + i * cell + cell / 2, Y + 6 * cell + 8 * s, text=str(i + 1), fill="#aaa", font=self.F(8))
        for i, res in enumerate(player.card):
            r, col = divmod(i, 6)
            x, y = X + col * cell, Y + r * cell
            c.create_rectangle(x, y, x + cell, y + cell, fill=self.COLORS[res] if used else "#3a4a40",
                               outline="#1d2b22")
            c.create_text(x + cell / 2, y + cell / 2, text=res, font=self.F(9, True),
                          fill="black" if used else "#7d8c82")
        if used and hit is not None:
            r, col = divmod(hit, 6)
            x, y = X + col * cell, Y + r * cell
            c.create_rectangle(x, y, x + cell, y + cell, outline="#ff1744", width=max(2, int(4 * s)))

    def draw_card(self):
        c, g, s = self.cards, self.game, self.s
        c.delete("all")
        last = g.last
        if last:
            batter, pitcher = last["batter"], last["pitcher"]
        else:
            b, f = g.bat, 1 - g.bat
            batter, pitcher = g.t[b]["lineup"][g.spot[b]], g.pit[f]
        cx, cy = 40 * s, 36 * s
        pts = [(cx + 28 * s * math.cos(math.radians(60 * k + 30)), cy + 28 * s * math.sin(math.radians(60 * k + 30)))
               for k in range(6)]
        c.create_polygon(pts, fill="#7e57c2", outline="white", width=max(1, int(2 * s)))
        c.create_text(cx, cy, text=str(last["d20"]) if last else "d20", fill="white", font=self.F(16, True))
        self.die(c, 100, 13, last["d1"] if last else 1)
        self.die(c, 156, 13, last["d2"] if last else 1)
        if last:
            who = "BATTER" if last["use_bat"] else "PITCHER"
            c.create_text(215 * s, 22 * s, anchor="w", fill="white", font=self.F(10, True),
                          text=f"d20 = {last['d20']}  \u2192  {who} card")
            c.create_text(215 * s, 42 * s, anchor="w", fill="#f2c94c", font=self.F(10),
                          text=f"2d6 = {last['d1']} + {last['d2']}  (row {last['d1']}, col {last['d2']})")
        else:
            c.create_text(215 * s, 32 * s, anchor="w", fill="#ccc", font=self.F(10), text="Click Next Batter to roll")
        hit = last["idx"] if last else None
        use_bat = last["use_bat"] if last else None
        bt = last["bt"] if last else g.bat
        self.grid(c, 24, 110, batter, "BATTER", use_bat is True, hit, g.t[bt])
        self.grid(c, 228, 110, pitcher, "PITCHER", use_bat is False, hit, g.t[1 - bt])
        c.create_text(210 * s, 336 * s, fill="white", font=self.F(11, True),
                      text=f"{last['batter'].name}: {TEXT[last['res']]}" if last else
                      "Rows = first d6, columns = second d6")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
