# Hypotheses above Kholo Creek

Maritime Safety Queensland (MSQ) publishes tide figures only as far up the river as
Kholo Creek (km 75.8). The project's predictions stop there. Above Kholo, from the
Kholo Creek line to the old weir ruin (km 87.4), anything the project says about the
tide is a **hypothesis under test**: a claim written down *before* the data that tests
it, so that the data can prove it wrong.

How this works:

- Each hypothesis has a date. Git history shows it was written before the observations
  that test it. Observations used to *form* a hypothesis never count as tests of it.
- Each hypothesis says in advance what result would prove it wrong, and which days or
  observations don't count.
- The reports page shows each hypothesis with its running tally, for example
  "consistent with 4 of 4 tests since 2026-11-14".
- A hypothesis may be shown on the Predictions page as an **experimental estimate**
  only after at least 10 tests, made on at least 3 different days, covering both
  spring and neap tides, with none against it. That threshold is a judgement call, not
  a statistical rule.
- A hypothesis that fails stays in this file, marked *refuted*, with the results that
  refuted it. A replacement gets a new number and a new date.

Confidence along the river, as the pages show it:

| Reach | Basis |
|---|---|
| Bar to Indooroopilly (km 0–37.6) | MSQ published ratios |
| Indooroopilly to Kholo Creek (km 37.6–75.8) | MSQ spring and neap figures, averaged by this project |
| Above Kholo Creek (km 75.8–87.4) | Hypotheses under test (this file) |

---

## H1: High water timing up to Colleges Crossing

**Status:** under test, from 2026-11-14.

### Claim

Between Kholo Creek (km 75.8) and just below the Colleges Crossing gravel run (km 83.7),
high water comes **2 ± 1 minutes per km later** than MSQ's Kholo Creek high water, which
is 150 minutes after predicted high water at the Brisbane Bar.

So at a place *d* km above Kholo, high water comes between **150 + 1·*d*** and
**150 + 3·*d*** minutes after predicted Bar high water. For example:

| Place | km | *d* | High water after Bar HW (min) |
|---|---|---|---|
| Kholo Creek | 75.8 | 0 | 150 (MSQ) |
| Halfway | 79.8 | 4.0 | 154–162 |
| Just below the Colleges Crossing run | 83.7 | 7.9 | 158–174 |

### Where the numbers come from

They come from the MSQ high-water lags in `data/stations.csv` (`lag_hw_min`) for the
reaches just below Kholo:

| Reach | km | High-water lag change | Min per km |
|---|---|---|---|
| Wacol to Goodna | 56.5–61.7 | 115 → 123 min | 1.5 |
| Goodna to Moggill | 61.7–68.6 | 123 → 141 min | 2.6 |
| Moggill to Kholo Creek | 68.6–75.8 | 141 → 150 min | 1.25 |

2 ± 1 min per km covers all three. There are no observations of high-water timing above
Kholo yet. The observations in `data/observations.csv` (2023-06-04 and 2026-11-14) record
whether the gravel runs were running and how the water looked, not when high water came.
None of them are tests of H1.

Note: the predictions model shifts the whole Kholo curve by the mean lag (160 min), not
the high-water lag (150 min). H1 uses MSQ's high-water lag because it is about high water
only.

### How to test it

You need a fixed mark at the water's edge that you can photograph from the same place
each time: a bridge pier, a rock, a post. Then:

1. Look up predicted Bar high water on the Predictions page and work out the expected
   window for your km.
2. From about 45 minutes before that window to 45 minutes after, photograph the mark
   every 10 minutes or so. The camera's clock gives the times.
3. High water is the photo, or the middle of the run of photos, where the level is
   highest. Record that time to the nearest 10 minutes, the km, and the predicted Bar
   high water. Add a row to `data/observations.csv` with quantity `high_water_time`.

### What would prove it wrong

A test is **against H1** when the observed high water is more than 10 minutes outside
the window: before 150 + 1·*d* − 10 or after 150 + 3·*d* + 10 minutes after predicted
Bar high water. The 10 minutes allows for the photo spacing.

H1 is **refuted** when 2 or more tests, on different days, are against it. One test
against it on its own is flagged for a second look: the mark, the clock, the conditions.

### What doesn't count

These are set now, before any tests:

- **Days with the river in fresh.** A Bureau of Meteorology flood warning for the
  Brisbane River below Wivenhoe in the 3 days before, or the observer sees the river in flood
  (fast, brown, carrying debris). Fresh water coming down changes when high water
  arrives. Those days belong to a later hypothesis.
- **No rise seen.** If the level doesn't visibly rise and fall at the mark, perhaps
  because a run is holding the pool up at neaps, the result is recorded as *no rise
  seen*. That is neither for nor against H1. It is evidence about how far the tide
  reaches.
- **Above km 83.7.** The Colleges Crossing run (km 83.8) separates two pools. H1 makes
  no claim above it.

### Not covered by H1

- **Low water.** Above Kholo the gravel runs set a floor under the water at low tide, and
  that floor's height is unknown. H1 says nothing about low water or how far the level
  falls.
- **Height.** H1 is about *when*, not *how high*.
- **Flow direction.** The flow turns some time after high water. When the flow turns is
  a separate question, for a later hypothesis.

### Results

| Date | km | Predicted Bar HW | Observed HW | Minutes after Bar HW | Window | Result |
|---|---|---|---|---|---|---|
| (none yet) | | | | | | |
