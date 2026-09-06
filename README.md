# shazam-chart

Daily snapshot of the official Shazam Israel Top 200 chart (public data, rolling 7-day window).

Files the consumer reads:

- `latest.csv` — the most recent chart, fetched twice daily (02:00 and 05:30 UTC) by GitHub Actions.
- `peaks.csv` — per song: `Artist,Title,CurrentRank,PeakRank,PeakDate,DaysSeen,PrevWeekPeak`.
  `PeakRank` is the best rank over the last 7 days, `PrevWeekPeak` the best over the
  7 days before that (empty if the song did not chart then). `CurrentRank` is `OUT`
  for a song that charted during the window but has since dropped out of the top 200.
  Sorted best peak first.
- `status.json` — fetch health (`fetch_ok`, `source_used`, `chart_date`, `age_days`,
  `stale`, per-attempt tally) plus the peak window (`peak_window_start/end/days`).
- `history/YYYY-MM-DD.csv` — one archived chart per day, filed by chart date, kept 60 days.

Why `peaks.csv` exists: the chart is a rolling 7-day aggregate, so a song that spikes
on Monday is already decaying by Friday and a mid-week entry can be gone entirely.
Measured over 2026-08-30..09-05, 119 of the 200 songs in the Friday chart had ranked
higher earlier that week, and 71 more had charted and dropped out. A weekly report
built on the Friday snapshot alone understates both.

It is rebuilt from scratch on every run by `scripts/build_peaks.py`, so there is no
incremental state to drift and a failed day heals itself on the next good one.

Consumed by a scheduled Claude Code cloud task that cross-checks the Kan 88 weekly
playlist against the chart.
