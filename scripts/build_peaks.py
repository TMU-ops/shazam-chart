#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild peaks.csv from the daily snapshots in history/.

latest.csv is one sample of a chart that is itself a rolling 7-day window, so a
song that spiked on Monday is already decaying by the time the Friday report is
written -- and a song that charted mid-week can be gone entirely. Measured over
2026-08-30..09-05: 119 of the 200 songs in the Friday chart had been higher
earlier that week, and 71 more had been in the top 200 and dropped out.

peaks.csv answers, per song: where is it now, how high did it get this week, and
when. Rebuilt from scratch on every run -- no incremental state to drift or
corrupt, so a bad day heals itself on the next good one.
"""
import csv, io, json, os, re, sys, datetime

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS = os.path.join(ROOT, "status.json")
HIST   = os.path.join(ROOT, "history")
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
        s = s.replace("\u2019", "'").replace("\u2018", "'")
        s = s.replace("\u201c", '"').replace("\u201d", '"')
        return re.sub(r"\s+", " ", s).strip().lower()
    return (norm(artist), norm(title))


def main():
    if not os.path.isdir(HIST):
        sys.exit("no history/ directory")
    dates = sorted(m.group(1) for m in
                   (DATED.match(f) for f in os.listdir(HIST)) if m)
    if not dates:
        sys.exit("history/ has no dated snapshots")

    newest = datetime.date.fromisoformat(dates[-1])
    start  = newest - datetime.timedelta(days=WINDOW - 1)
    window = [d for d in dates if datetime.date.fromisoformat(d) >= start]

    best, seen, display, current = {}, {}, {}, {}
    used = []
    for d in window:
        rows = read_chart(os.path.join(HIST, d + ".csv"))
        if not rows:
            print("skipping unreadable snapshot %s" % d)
            continue
        used.append(d)
        for rank, artist, title in rows:
            k = key(artist, title)
            display[k] = (artist, title)          # newest spelling wins
            seen[k] = seen.get(k, 0) + 1
            if k not in best or rank < best[k][0]:
                best[k] = (rank, d)
        if d == window[-1]:
            current = {key(a, t): r for r, a, t in rows}

    out = []
    for k, (peak, peak_date) in best.items():
        artist, title = display[k]
        out.append((artist, title,
                    str(current[k]) if k in current else "OUT",
                    peak, peak_date, seen[k]))
    # Best of the week first; that is the number Tomer copies into the sheet.
    out.sort(key=lambda r: (r[3], r[0].lower(), r[1].lower()))

    with io.open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Artist", "Title", "CurrentRank", "PeakRank", "PeakDate", "DaysSeen"])
        w.writerows(out)

    # Prune old snapshots so the folder stays bounded.
    cutoff = newest - datetime.timedelta(days=KEEP)
    pruned = 0
    for d in dates:
        if datetime.date.fromisoformat(d) < cutoff:
            os.remove(os.path.join(HIST, d + ".csv")); pruned += 1

    # The agent already reads status.json for freshness; put the window there
    # too, so peaks.csv can stay pure data with a plain header.
    if os.path.exists(STATUS):
        try:
            with io.open(STATUS, encoding="utf-8") as f:
                st = json.load(f)
            st["peak_window_start"] = used[0]
            st["peak_window_end"]   = used[-1]
            st["peak_window_days"]  = len(used)
            st["peaks_songs"]       = len(out)
            with io.open(STATUS, "w", encoding="utf-8", newline="\n") as f:
                json.dump(st, f, ensure_ascii=False, indent=2)
                f.write("\n")
        except Exception as e:
            print("could not update status.json: %s" % e)

    print("window   : %s .. %s (%d snapshots used)" % (used[0], used[-1], len(used)))
    print("songs    : %d (%d currently charting, %d dropped out)"
          % (len(out), sum(1 for r in out if r[2] != "OUT"),
             sum(1 for r in out if r[2] == "OUT")))
    print("pruned   : %d snapshot(s) older than %d days" % (pruned, KEEP))
    print("PEAK_WINDOW_START=%s" % used[0])
    print("PEAK_WINDOW_END=%s"   % used[-1])
    print("PEAK_WINDOW_DAYS=%d"  % len(used))


if __name__ == "__main__":
    main()
