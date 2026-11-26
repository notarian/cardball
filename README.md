# CardBall

A Strat-O-Matic-style baseball simulation that runs locally in a tkinter window.
Roll a d20 to pick the batter's or pitcher's card, then two d6 to pick a slot on that card.

![python](https://img.shields.io/badge/python-3.9%2B-blue)

## Run it

```
python3 cardball.py
```

Needs Python 3 with tkinter. With no data file it plays real MLB teams and colors with fictional players.

## Real players (Retrosheet 1986)

1. Download the "Main CSV Download" from https://www.retrosheet.org/downloads/csvdownloads.html and unzip it.
2. `python3 build_season.py 1986 /path/to/unzipped_folder`
3. Keep the resulting `season_1986.json` next to `cardball.py`.

Cards are built from each player's season rates (small samples are regressed toward the league average).

## Controls

Next Batter, Finish Half-Inning, Auto-Play, Sim To End. Size -/+ buttons or Cmd/Ctrl +/- scale the whole window.

## Data credit

The information used here was obtained free of charge from and is copyrighted by Retrosheet.
Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.
Team names and colors belong to their respective owners; this is a personal, non-commercial project.
