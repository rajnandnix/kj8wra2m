# Assumptions and verified facts

Every assumption is recorded here as it is made, with the reasoning. Anything marked
**Verified** was checked against a live API response on 2026-10-23 (by a throwaway spike script, since removed;
the production raw responses are in `data/raw/`). Anything marked
**Decision** is a design choice. Anything marked **Open** is not yet resolved.

## 1. Scope and date interpretation

**Decision.** "Purchase decisions made in January 2026" is read as decision days 1 to 31 January
2026 inclusive. Each decision day D-1 buys for delivery day D, so **delivery days are 2 January
to 1 February 2026 inclusive (31 days, 744 hourly intervals)**. The alternative reading
(delivery in January, decisions 31 Dec to 30 Jan) was rejected because the brief speaks of when
the *decision* is made. Both dates live in `backend/app/config.py` and nowhere else. A delivery
day is the London calendar day; in January London time equals UTC.

Scope: national GB, wind only, Elexon BMRS only, no model of our own, no price data.

Forecast publications are fetched from 28 Dec 2025 to the end of 31 Jan 2026 (the last decision
day). Publications after the last decision day are deliberately not stored, so the snapshot
cannot contain anything from after the final decision. Actuals are fetched for the delivery
window only, selected by `settlementDate`.

## 2. Elexon API facts (Phase 1, verified against live responses)

Base URL for both datasets: `https://data.elexon.co.uk/bmrs/api/v1/datasets/{DATASET}/stream`.
No API key. About 50 requests were made in total.

### 2.1 FUELHH: URL, parameters, sample response

**Verified.** Working request for a 3 day window:

```
GET https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream
    ?publishDateTimeFrom=2026-01-14T00:00:00Z
    &publishDateTimeTo=2026-01-17T00:00:00Z
    &fuelType=WIND
```

- `fuelType=WIND` filters **server side**. The result is identical to fetching all 20 fuel types
  (2,900 rows for the same window) and filtering client side (145 rows both ways).
- `publishDateTimeFrom` and `publishDateTimeTo` are **inclusive at both ends**: a 1 day window
  returns 49 half-hours, not 48. Adjacent chunks therefore share a boundary row and must be
  deduplicated.
- `settlementDateFrom=2026-01-14&settlementDateTo=2026-01-16` also works on FUELHH and filters on
  the delivery date: it returned exactly 144 rows (3 x 48), `startTime` 14 Jan 00:00 to 16 Jan
  23:30. This is a cleaner way to ask for actuals by delivery day than `publishDateTime*`.
- Fuel types present: BIOMASS, CCGT, COAL, INTELEC, INTEW, INTFR, INTGRNL, INTIFA2, INTIRL,
  INTNED, INTNEM, INTNSL, INTVKL, NPSHYD, NUCLEAR, OCGT, OIL, OTHER, PS, WIND. Wind is the single
  value `WIND`.

Sample row:

```json
{"dataset":"FUELHH","publishTime":"2026-01-17T00:00:00Z","startTime":"2026-01-16T23:30:00Z","settlementDate":"2026-01-16","settlementPeriod":48,"fuelType":"WIND","generation":9116}
```

**Trap, verified:** the parameters `from` and `to` are **silently ignored**. The request returns
HTTP 200 with the latest data for today (23 Oct 2026), not the requested January window. Unknown
parameters are never rejected. The ingestion code must therefore assert that returned rows fall
inside the requested window instead of trusting a 200.

### 2.2 WINDFOR: URL, parameters, sample response

**Verified.**

```
GET https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream
    ?publishDateTimeFrom=2026-01-14T00:00:00Z
    &publishDateTimeTo=2026-01-17T00:00:00Z
```

- The filter is on `publishTime`, inclusive at both ends.
- `from`/`to` and `settlementDateFrom`/`settlementDateTo` are **silently ignored** on WINDFOR.
  With no parameters at all, the endpoint returns only the single most recent publication
  (73 rows).
- Fields: `dataset`, `publishTime`, `startTime`, `generation`. There is no `settlementDate`,
  `settlementPeriod` or `fuelType`.

Sample rows:

```json
{"dataset":"WINDFOR","publishTime":"2026-01-14T04:30:00Z","startTime":"2026-01-13T21:00:00Z","generation":12079}
{"dataset":"WINDFOR","publishTime":"2026-01-14T04:30:00Z","startTime":"2026-01-13T22:00:00Z","generation":11434}
```

### 2.3 Response envelope shape

**Verified.** A bare JSON array of objects for both datasets, with no `{"data": [...]}` wrapper.
Content type `application/json; charset=utf-8`.

### 2.4 FUELHH startTime spacing

**Verified.** 30 minutes. In the fetch window (28 Dec 2025 to 3 Feb 2026) all 1,776 gaps between
consecutive WIND `startTime` values are exactly 30 minutes, and the minute-of-hour is only 00 or 30.

### 2.5 WINDFOR startTime spacing

**Verified. WINDFOR is hourly, not half-hourly.** All 21,312 gaps between consecutive `startTime`
values within a publication are exactly 60 minutes, and every `startTime` is on the hour. The
hourly/half-hourly mismatch described in CLAUDE.md 2.2 and 3.3 **exists**, so section 3.3
(evaluate at native hourly resolution, average the two half-hourly actuals) applies.

### 2.6 WINDFOR publication cadence

**Verified.** Over 37 calendar days there are 296 distinct `publishTime` values: **exactly 8 per
UTC day on all 37 days**. Standard times (UTC): **02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30,
22:30**. Gaps are 2h, 3h or 4h. One irregularity: on 15 Jan the 11:30 publication did not occur
and a 12:25 one appeared instead (this is the only occurrence in the window).

Sample day 2026-01-14: publications at 02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30, 22:30,
each with 73 rows.

**A meaningful "latest forecast before the cutoff" exists on every delivery day**, and it is
always a full vintage: for each of the 31 delivery days (2 Jan to 1 Feb 2026) the vintage
selected at the cutoff covers all 24 hourly targets of the delivery day, with lead times of
14.5h to 37.5h.

**Critical finding: the 09:30 publication lands exactly on the 09:30 cutoff.** With
`cutoff = (D-1) 09:30 Europe/London` (= 09:30 UTC in January) and the rule `publishTime <= cutoff`,
the selected vintage on **all 31 days** is the one with `publishTime == cutoff` exactly (age 0.0h).
With a strict `publishTime < cutoff` the selected vintage would instead be the 07:30 publication
(2h earlier). The inclusive/exclusive decision therefore changes the vintage on every single
day, so it is not an edge case. See section 4.

### 2.7 WINDFOR forecast horizon

**Verified.** Each publication contains exactly 73 hourly rows (3 days + 1 hour) on a window that
is keyed to the publication date: for publications on 14 Jan the window is always 13 Jan 21:00Z to
16 Jan 21:00Z, whatever time of day it was published. Consequences:

- Furthest `startTime` per publication (the horizon) ranges from **46.5h (22:30 publication) to
  66.5h (02:30 publication)**. The 09:30 publication reaches 59.5h ahead.
- About 20% of all rows (4,441 of 21,608) have `startTime < publishTime`: the early hours of each
  window are already in the past when published (up to 25.5h before). They are not forecasts.
  They are irrelevant for D-1 decisions, which only use targets in the future delivery day,
  but they must never be treated as forecast lead-time data.

### 2.8 Duplicate (startTime, publishTime) pairs

**Verified.** None. WINDFOR: 0 duplicate `(startTime, publishTime)` pairs in 21,608 rows. FUELHH
WIND: 0 duplicate pairs, and every `startTime` has exactly one `publishTime` (no revision
history is exposed) and one `generation` value. No nulls or negatives in either dataset. WINDFOR
range 2,051 to 21,353 MW; FUELHH WIND 1,695 to 17,805 MW.

No dedup rule is needed for the data as served. A defensive rule is still required for the
**chunk boundary overlap** (section 2.1): drop exact duplicate rows after concatenating chunks.

FUELHH `publishTime` is `startTime + 30 min` for 1,773 of 1,777 rows. The four exceptions are
`startTime` 10:00, 10:30, 11:00 and 11:30 on 15 Jan, published late at 12:25 to 12:26. Same
day as the irregular WINDFOR 12:25 publication, which suggests a source-side delay. It does not
affect the evaluation (all values are present).

### 2.9 Timestamp timezone format

**Verified.** Every `startTime` and `publishTime` in both datasets matches
`YYYY-MM-DDTHH:MM:SSZ` (0 exceptions in 23,385 rows). UTC with a `Z` suffix. `settlementDate` is
a plain date.

### 2.10 FUELHH completeness on a sample day

**Verified.** On 2026-01-14 there are exactly 48 WIND rows, `settlementPeriod` 1 to 48. Over the
whole delivery window (2 Jan to 1 Feb 2026, 31 days) **1,488 of 1,488 expected half-hours are
present (0 missing)**. WINDFOR: 744 of 744 expected hourly targets are present in at least one
vintage (0 missing).

### 2.11 Maximum date range per request

**Verified, upper bound not found.** `publishDateTimeFrom/To` spans of 1, 7, 14, 31, 36, 60 and 90
days all returned 200 with no truncation (FUELHH WIND rows = 90 x 48 + 1 exactly at 90 days;
WINDFOR 52,552 rows, 5.9 MB, 1.4 s at 90 days; row counts scale linearly). The whole 37 day fetch
window fits in one request per dataset. I did not test beyond 90 days.

### 2.12 Rate limiting

**Verified: none observed.** A burst of 15 back-to-back requests with no pause all returned 200
in 0.2 to 1.6s. No `429`, no `Retry-After`, and no rate-limit headers in any response. Retry with
backoff is still worth implementing (cheap insurance), but it was never triggered.

## 3. Contradictions with the project brief (CLAUDE.md)

1. **Section 2.1 and 2.2 suggest `from`/`to` as a likely parameter pair. They are silently
   ignored** and return today's data with HTTP 200 (section 2.1). Use `publishDateTimeFrom/To`
   (or `settlementDateFrom/To` for FUELHH) and validate the returned range.
2. **Section 2.3 and 3.4 assume the two datasets are broadly comparable in scope. At the level
   of absolute MW they are not.** At short lead times (0.5h to 3.5h, 744 hourly targets over
   the delivery window) the WINDFOR value averages **12,757 MW** against **11,284 MW** for FUELHH
   WIND: a mean offset of **+1,473 MW (+13.1%)**, with correlation 0.957. Removing the mean
   offset cuts the mean absolute gap from 1,687 MW to 1,174 MW. So most of the
   gap is a systematic level offset, i.e. exactly the "scope bias that cannot be separated
   from forecast error" of section 2.3. **Expect the Phase 3 headline MAE and bias to be well
   above CLAUDE.md's "low hundreds of MW to ~1 GW" sanity range, and bias to be large and
   positive.** Confirmed at day-ahead leads: bias +1.75 GW (+15.5% of mean actual) at the primary
   cutoff. Cause analysed in section 8.1.
3. **Section 3.2: the 09:30 cutoff coincided with a publication time** (section 2.6), making the
   "publishTime exactly equal to the cutoff" edge case the dominant case. Resolved by replacing
   the round number with real gate-closure times (section 4).
4. **Section 3.1:** the buffer start of 28 Dec is more generous than needed. The earliest vintage
   ever selected is 1 Jan 09:30. It is harmless and kept as specified.

Not contradictions (confirmed as written): WINDFOR is hourly (2.5), the alignment design in 3.3
applies, the API is keyless, and a usable vintage exists on every delivery day.

## 4. Decision cutoff (no-lookahead rule)

**Decision (product owner), replacing the round-number 09:30.** The cutoff is the gate closure of
a real GB day-ahead auction, at wall-clock time on D-1 in Europe/London. The three times were
supplied by the product owner and are **not independently verified against exchange rules**.

| Key | Time | Auction | Role | WINDFOR vintage selected |
|---|---|---|---|---|
| `epex60` | 09:20 | EPEX SPOT GB 60 minute | **primary**, earliest gate, lookahead-safe | 07:30 |
| `n2ex` | 09:50 | Nord Pool N2EX | sensitivity | 09:30 |
| `epex30` | 15:30 | EPEX SPOT GB 30 minute | sensitivity | 11:30 (12:25 on one day) |

All three live in `config.CUTOFFS`; the primary is `config.PRIMARY_CUTOFF`. The full metric set
is computed at all three and compared in the UI.

Comparison operator: `publishTime + PUBLICATION_LAG <= cutoff`, i.e. `<=` is kept.

**Deviation to flag: one publication does land exactly on a boundary.** WINDFOR publishes at
15:30 UTC, which is exactly the 15:30 gate closure. The premise that "no publication time lands
exactly on a boundary" is true for 09:20 and 09:50 but not for 15:30. With a bare `<=` the
15:30 vintage would be used at the 15:30 cutoff, which contradicts the stated intent that this
cutoff makes the **11:30** vintage usable. I resolved it by honouring the intent:
`config.PUBLICATION_LAG = 1 minute`, so a forecast stamped t is treated as in hand from t + 1 min.
The operator stays `<=`. Only the 15:30 cutoff is affected. Setting the lag to zero gives the
15:30 vintage at that gate; that variant measured MAE 1,873.5 MW against 1,904.0 MW with the lag
(a 30 MW difference, recorded in the phase report).

Cutoff is converted from London wall-clock time to UTC with `zoneinfo`, so it is correct across
clock changes (tested for July). January has no clock change.

`publishTime` is assumed to be the moment a forecast becomes available. The data cannot show
the real latency, and this is the main residual lookahead risk.

## 5. Resolution alignment

**Decision.** Metrics are computed at WINDFOR's native hourly resolution. For hourly target `T`
the actual is the mean of the FUELHH half-hours with `startTime = T` and `T + 30 min` ("hour
beginning T"). Mean, not sum, because `generation` is power in MW. An hour missing either
half-hour is reported as a missing actual, never averaged from one value. The forecast is
never interpolated. Energy (MWh) is MW x 1.0 h per hourly interval.

The "hour beginning T" convention is assumed, not verified: four alternative conventions gave
mean absolute gaps within 2% of each other (1,687 / 1,659 / 1,668 / 1,680 MW at nowcast leads),
which is too small to discriminate because hourly wind output moves slowly and the level
offset dominates. Low stakes, stated openly. Approved by the product owner.

## 6. Deduplication rule

No duplicates exist in the data as served (section 2.8). Rule for Phase 2: after concatenating
chunks, drop exact duplicate rows (chunk boundaries overlap because the range filter is inclusive
at both ends), then assert uniqueness of `(startTime, publishTime)` for WINDFOR and of
`startTime` for FUELHH WIND, and fail loudly if either is violated.

## 7. Missing data handling

The aligned table is an outer join against the complete expected index (31 days x 24 hours = 744
rows). Each row has status `ok`, `missing_forecast`, `missing_actual` or `missing_both`.
Incomplete pairs are excluded from the metrics and counted; coverage is shown in the API and UI.
Result for January 2026: 744 of 744 complete at all three cutoffs (100% coverage, nothing
excluded). Past-dated WINDFOR rows (`startTime < publishTime`) are stored but can never be
selected, because every cutoff precedes the delivery day (asserted in a test on the real data).

## 8. Metrics

error = forecast - actual; positive means the forecast was too high (under-procurement).
MAE, RMSE, bias (mean error), nMAE (MAE over mean actual, a percentage), P10/P50/P90 of error
(linear-interpolation percentiles), max absolute error with its timestamp, coverage. **No MAPE**
(wind approaches zero). Breakdowns: by local hour, by generation level, by delivery day, and an
error histogram (500 MW bins).

**Debiased MAE and RMSE** (secondary, clearly labelled): the same metric after subtracting the
mean error. This separates a standing offset, which a client could correct, from forecast skill.
Debiased MAE can exceed MAE in principle (the mean is not the MAE-minimising offset); it does
not on this data.

**Level buckets** are 0-6, 6-10, 10-14 and 14+ GW, not the brief's 0-2-4 GW example, because
January GB wind (as served by FUELHH) ranged 1.7 to 17.8 GW with mean 11.3 GW.

**Procurement band** (CLAUDE.md 3.5): realised = forecast - error, so the realised wind lies in
[forecast - P90, forecast - P10]. Cover to hold at P90 = max(P90 of error, 0) MW; MWh = MW x hours.
It is an empirical, **in-sample** band (the displayed day is part of the sample that sets the
quantiles), unconditional on hour or level, and not a probabilistic forecast.

**Cutoff comparison:** paired on common intervals, 95% interval from a day-block bootstrap
(whole delivery days resampled, 2,000 resamples, fixed seed) because errors within a day are
correlated. "Materially better" requires at least 3% MAE improvement; the verdict says so when
the interval includes zero.

### 8.1 Curtailment hypothesis (time-boxed, product owner's instruction)

Hypothesis: WINDFOR forecasts available wind, FUELHH records metered output after curtailment,
curtailment concentrates in high-wind periods, so the gap should scale with generation level.

- **Bucketed on actual** (the brief's breakdown) the gap does not scale cleanly: bias +1.86 GW at
  <6 GW (41% of actual), +1.14 GW at 6-10, +1.22 GW at 10-14, +2.40 GW at 14+. Level explains
  under 3% of error variance (R2 0.028). But conditioning on the realised value mechanically
  inflates low buckets, so this view understates any level effect.
- **Bucketed on forecast** (what a trader knows at decision time) the gap does scale: +0.77 GW
  below 6 GW, +0.73 at 6-10, +1.68 at 10-14, +2.51 at 14+ GW (primary cutoff). Slope of error
  on forecast 0.19, R2 0.27 (0.35 at the 15:30 cutoff). Realised wind is about 0.81 x forecast
  + 0.74 GW. FUELHH peaks at 17.8 GW while WINDFOR reaches 21.4 GW.
- **Verdict: partly supported.** The level dependence at high forecasts is what curtailment would
  produce and is the larger part of the bias. It does not explain the roughly 0.75 GW offset that
  remains at low forecast levels, where curtailment is least likely; that residual is more
  consistent with a scope or coverage difference between the datasets. Cause is not proven and
  was not pursued further.

## 9. Known data caveats

- FUELHH covers transmission-metered, BM-registered generation. Embedded
  (distribution-connected) wind is not included.
- WINDFOR likewise covers BM Unit wind, but see section 3.2: measured against FUELHH it sits about
  13% higher at short lead times, so the two are **not** equivalent in practice.
- Any scope discrepancy between the two datasets is a source of systematic bias that
  this analysis cannot separate from genuine forecast error.
- The data cannot show how long after `publishTime` a forecast was actually available to a
  trader. Treating `publishTime` as the availability time is an assumption.
- Elexon accepts unknown query parameters silently (section 2.1).

## 10. Daylight saving

January has no clock change: London time equals UTC, so every cutoff equals its UTC value on all
31 days. The cutoff conversion uses `zoneinfo` and is unit-tested for a July date, delivery days
are London calendar days, and the expected hourly index is built in London time and converted to
UTC. Still, the code should be audited before extending to March or October (23 and 25 hour
days, WINDFOR publication-window alignment, FUELHH settlement periods 1-46 or 1-50).
