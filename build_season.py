#!/usr/bin/env python3
"""Turn Retrosheet CSV downloads into season_<year>.json for cardball.py.

  1. Download "Main CSV Download" from https://www.retrosheet.org/downloads/csvdownloads.html and unzip it.
  2. python3 build_season.py 1986 /path/to/unzipped_folder
  3. Put the resulting season_1986.json next to cardball.py.

Needs only batting.csv, pitching.csv and allplayers.csv from that download (takes a minute or two).

The information used here was obtained free of charge from and is copyrighted by Retrosheet.
Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict

BAT = ["pa", "ab", "h", "d", "t", "hr", "w", "hbp", "k"]
PIT = ["bfp", "h", "d", "t", "hr", "w", "hbp", "k", "ipouts", "er"]


def n(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def rows(path, year):
    """Yield dict rows for one season's 'value' stat lines (gid looks like BOS198604070)."""
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rd = csv.reader(f)
        head = next(rd)
        gi = head.index("gid")
        si = head.index("stattype") if "stattype" in head else None
        for r in rd:
            if r[gi][3:7] != year or (si is not None and r[si] != "value"):
                continue
            yield dict(zip(head, r))


def pick(by_type, what):
    print(f"{what}: gametypes found -> { {k: len(v) for k, v in by_type.items()} }")
    if "regular" in by_type:
        return by_type["regular"]
    best = max(by_type, key=lambda k: len(by_type[k]))
    print(f"  no 'regular' gametype; using '{best}'")
    return by_type[best]


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    year, folder = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else f"season_{year}.json"
    paths = {k: os.path.join(folder, k + ".csv") for k in ("batting", "pitching", "allplayers")}
    for p in paths.values():
        if not os.path.exists(p):
            sys.exit(f"Missing {p}")

    names = {}
    for r in rows_plain(paths["allplayers"]):
        if r.get("season") == year:
            names[r["id"]] = f"{r['first']} {r['last']}".strip()

    bt = defaultdict(lambda: defaultdict(Counter))
    for r in rows(paths["batting"], year):
        c = bt[r["gametype"]][(r["team"], r["id"])]
        c["g"] += 1
        for k in BAT:
            c[k] += n(r["b_" + k])
        if r["b_seq"] == "1":
            c["starts"] += 1
            c["lp"] += n(r["b_lp"])
    pt = defaultdict(lambda: defaultdict(Counter))
    for r in rows(paths["pitching"], year):
        c = pt[r["gametype"]][(r["team"], r["id"])]
        c["g"] += 1
        c["gs"] += n(r["gs"])
        for k in PIT:
            c[k] += n(r["p_" + k])
    bat, pit = pick(bt, "batting"), pick(pt, "pitching")
    if not bat or not pit:
        sys.exit(f"No {year} data found. Check the year and that these are Retrosheet's CSV files.")

    pitcher_ids = {pid for (t, pid), c in pit.items() if c["gs"] >= 5}
    league_bat = Counter()
    for (t, pid), c in bat.items():
        if pid not in pitcher_ids:
            for k in BAT:
                league_bat[k] += c[k]
    league_pit = Counter()
    for c in pit.values():
        for k in PIT:
            league_pit[k] += c[k]

    def bdict(pid, c):
        return {"id": pid, "name": names.get(pid, pid), **{k: c[k] for k in BAT}}

    def pdict(pid, c):
        return {"id": pid, "name": names.get(pid, pid), "g": c["g"], "gs": c["gs"], **{k: c[k] for k in PIT}}

    teams = {}
    for team in sorted({t for t, _ in bat}):
        cands = [(pid, c) for (t, pid), c in bat.items() if t == team and pid not in pitcher_ids and c["pa"] > 0]
        cands.sort(key=lambda x: (-x[1]["starts"], -x[1]["pa"]))
        lineup = sorted(cands[:9], key=lambda x: x[1]["lp"] / x[1]["starts"] if x[1]["starts"] else 9)
        arms = [(pid, c) for (t, pid), c in pit.items() if t == team and c["bfp"] > 0]
        rotation = sorted(arms, key=lambda x: -x[1]["gs"])
        rotation = [a for a in rotation if a[1]["gs"] >= 8][:5] or rotation[:1]
        rest = [a for a in arms if a not in rotation]
        pen = sorted(rest, key=lambda x: -(x[1]["g"] - x[1]["gs"]))[:3] or rotation[-1:]
        if len(lineup) < 9 or not rotation:
            print(f"  skipping {team}: not enough data")
            continue
        teams[team] = {"lineup": [bdict(*x) for x in lineup],
                       "rotation": [pdict(*x) for x in rotation], "pen": [pdict(*x) for x in pen]}
    data = {"season": int(year), "league": {"bat": dict(league_bat), "pit": dict(league_pit)}, "teams": teams}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"Wrote {out}: {len(teams)} teams")


def rows_plain(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        yield from csv.DictReader(f)


if __name__ == "__main__":
    main()
