#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild peaks.csv from the daily snapshots in history/.

latest.csv is one sample of a chart that is itself a rolling 7-day window, so a
song that spiked on Monday is already decaying by the time the Friday report is
written -- and a song that charted mid-week can be gone entirely. Measured over
2026-08-30..09-05: 119 of the 200 songs in the Friday chart had been higher
earlier that week, and 71 more had been in the top 200 and dropped out.

peaks.csv answers, per song: where it is now, the best rank it reached this
week, and the best it reached last week to compare against. Rebuilt from scratch on
every run -- no incremental state to drift, so a bad day heals itself on the
next good one.
"""
import csv, io, json, os, re, sys, datetime

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST   = os.path.join(ROOT, "history")
STATUS = os.path.join(ROOT, "status.json")
OUT    = os.path.join(ROOT, "peaks.csv")
WINDOW = 7    # days, inclusive, ending at the newest snapshot
KEEP   = 60   # days of snapshots to retain on disk

DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv$")


def read_chart(path):
    """-> [(rank, artist, title)] or None if the file is not a usable chart."""
    with io.open(path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    hi = next((i for i, l in enumerate(lines) if l.startswith("Rank,Artist,Title")), None)
    if hi is None:
        return None
    rows = [(int(r[0]), r[1].strip(), r[2].strip())
            for r in csv.reader(lines[hi + 1:])
            if len(r) >= 3 and r[0].strip().isdigit()]
    return rows or None


def key(artist, title):
    """Conservative identity: case and quote shape only. Anything looser risks
    merging two different songs, and the agent does the real artist/title
    matching against the sheet."""
    def norm(s):
        s = s.replace(u"\u2019", "'").replace(u"\u2018", "'")
        s = s.replace(u"\u201c", '"').replace(u"\u201d", '"')
        return re.sub(r"\s+", " ", s).strip().lower()
    return (norm(artist), norm(title))


def collect(dates):
    """-> {key: [ranks]}, {key: (artist, title)}, [dates actually read]"""
    ranks, display, used = {}, {}, []
    for d in dates:
        rows = read_chart(os.path.join(HIST, d + ".csv"))
        if not rows:
            print("skipping unreadable snapshot %s" % d)
            continue
        used.append(d)
        for rank, artist, title in rows:
            k = key(artist, title)
            display[k] = (artist, title)          # newest spelling wins
            ranks.setdefault(k, []).append((d, rank))
    return ranks, display, used


def main():
    if not os.path.isdir(HIST):
        sys.exit("no history/ directory")
    dates = sorted(m.group(1) for m in
                   (DATED.match(f) for f in os.listdir(HIST)) if m)
    if not dates:
        sys.exit("history/ has no dated snapshots")

    newest = datetime.date.fromisoformat(dates[-1])
    this_start = newest - datetime.timedelta(days=WINDOW - 1)
    prev_start = this_start - datetime.timedelta(days=WINDOW)

    this_days = [d for d in dates if datetime.date.fromisoformat(d) >= this_start]
    prev_days = [d for d in dates
                 if prev_start <= datetime.date.fromisoformat(d) < this_start]

    cur, display, used = collect(this_days)
    prev, _, prev_used = collect(prev_days)
    if not used:
        sys.exit("no readable snapshot in the current window")

    last_day = used[-1]
    current = {k: r for k, r in ((k, dict(v).get(last_day)) for k, v in cur.items())
               if r is not None}

    out = []
    for k, pairs in cur.items():
        artist, title = display[k]
        peak_date, peak = min(((d, r) for d, r in pairs), key=lambda x: x[1])
        p = prev.get(k)
        out.append((artist, title,
                    str(current[k]) if k in current else "OUT",
                    peak, peak_date, len(pairs),
                    min(r for _, r in p) if p else ""))
    # Best of the week first; that is the number Tomer copies into the sheet.
    out.sort(key=lambda r: (r[3], r[0].lower(), r[1].lower()))

    with io.open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Artist", "Title", "CurrentRank", "PeakRank",
                    "PeakDate", "DaysSeen", "PrevWeekPeak"])
        w.writerows(out)

    if os.path.exists(STATUS):
        try:
            with io.open(STATUS, encoding="utf-8") as f:
                st = json.load(f)
            st["peak_window_start"] = used[0]
            st["peak_window_end"]   = used[-1]
            st["peak_window_days"]  = len(used)
            st["prev_window_days"]  = len(prev_used)
            st["peaks_songs"]       = len(out)
            with io.open(STATUS, "w", encoding="utf-8", newline="") as f:
                f.write(json.dumps(st, ensure_ascii=False, indent=2) + "\n")
        except Exception as e:
            print("could not update status.json: %s" % e)

    cutoff = newest - datetime.timedelta(days=KEEP)
    pruned = 0
    for d in dates:
        if datetime.date.fromisoformat(d) < cutoff:
            os.remove(os.path.join(HIST, d + ".csv")); pruned += 1

    print("window   : %s .. %s (%d snapshots)" % (used[0], used[-1], len(used)))
    print("previous : %s (%d snapshots)"
          % ((prev_used[0] + " .. " + prev_used[-1]) if prev_used else "none", len(prev_used)))
    print("songs    : %d (%d charting now, %d dropped out)"
          % (len(out), sum(1 for r in out if r[2] != "OUT"),
             sum(1 for r in out if r[2] == "OUT")))
    print("pruned   : %d snapshot(s) older than %d days" % (pruned, KEEP))


if __name__ == "__main__":
    main()
