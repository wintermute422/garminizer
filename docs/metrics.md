# Metrics

Garminizer shows Garmin's own metrics (training load, training effect, VO2max, readiness, HRV status,
body battery, sleep score, …) as Garmin computed them, and adds a few of its own. This page explains
the ones Garminizer computes. All code is in `backend/garminizer/analytics/` with unit tests.

## Training load series
- **Daily load** = sum of Garmin's *activity training load* per local day; activities without one use
  TRIMP instead. Rest days count as 0.
- **Fitness (CTL)** = exponentially weighted average of daily load with a 42-day time constant:
  `CTL_t = CTL_{t-1} + (load_t − CTL_{t-1}) · (1 − e^(−1/42))`.
- **Fatigue (ATL)** = the same with a 7-day time constant.
- **Form (TSB)** = yesterday's fitness − yesterday's fatigue. Positive: fresh; strongly negative:
  carrying fatigue.
- **ACWR** = 7-day average load / 28-day average load. 0.8–1.3 is the commonly cited "sweet spot";
  above 1.5 suggests a sharp increase.
- **Monotony / strain** (Foster) = 7-day mean / standard deviation of daily load; strain = weekly
  load × monotony.

These are the Banister impulse-response / "performance management" ideas popularised by
TrainingPeaks, computed on Garmin's load numbers — so absolute values are not comparable with TSS.

## TRIMP
Banister TRIMP per sample: `Δt[min] · HRr · 0.64 · e^(1.92 · HRr)` (women: `0.86 · e^(1.67 · HRr)`),
with `HRr = (HR − HRrest) / (HRmax − HRrest)` clipped to 0…1.

## Best efforts (mean-maximal curves)
For every activity: the highest average speed, power and heart rate sustained over 1 s … 5 h
(resampled to 1 Hz, gaps longer than 10 s are not bridged). Curves on the Records page take the best
value over all activities for each duration and are made non-increasing (a longer effort that was
faster also counts for shorter durations).

**Best distance times**: the fastest time to cover 400 m, 1 km, 1 mile, 5 km, 10 km, 15 km, half
marathon, 30 km and marathon *within* any run (start point interpolated between samples).

## Efficiency
- **Efficiency factor** = average output per heartbeat: speed in m/min (runs) or power in W (rides)
  divided by average heart rate. Rising EF at the same effort = improving aerobic fitness.
- **Aerobic decoupling (Pa:HR)** = how much EF dropped from the first to the second half of an
  activity, in percent. Below ~5 % on long steady sessions indicates good aerobic endurance.

## Zones
If Garmin did not provide heart-rate zone times for an activity, Garminizer computes them from the
recorded heart rate and your zone floors (Garmin profile, or 50/60/70/80/90 % of max HR). Power
zones use the Coggan bands relative to your FTP.

## Maps
- **Tracks** are simplified with Douglas-Peucker (≤ 600 points) for fast overview maps.
- **Explorer tiles** are the zoom-14 slippy-map tiles (≈ 1.5 km at mid latitudes) your tracks
  touched; *max square* is the largest fully visited k×k square, *max cluster* the largest
  4-connected group of tiles whose four neighbours are all visited.

## Insights
Correlations are Pearson's r between daily metrics (from the `v_daily` view) with an optional lag
(x on day d against y on day d+lag). With hundreds of days, |r| ≈ 0.1 is weak, 0.3 moderate and
≥ 0.5 strong — correlation is not causation. Insight cards are rule-based summaries (e.g. resting
HR over the last 30 days vs the previous 60) and only appear when enough data supports them.

## Demo data
The demo athlete is a day-by-day simulation, not real data: a periodised training plan drives
per-second streams (grade-adjusted pace, cycling power physics, heart rate with lag, drift, heat and
fatigue) and an all-day timeline; fitness, resting HR, HRV, sleep and readiness respond to load.
