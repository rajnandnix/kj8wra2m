# Assumptions and verified facts

Every assumption is recorded here as it is made, with the reasoning. Anything marked
**Verified** was checked against a live API response on 2026-10-23 (the spike script and its
cached raw responses are in `scripts/explore.py` and `data/raw/explore/`). Anything marked
**Decision** is a design choice. Anything marked **Open** is not yet resolved.

## 1. Scope and date interpretation

_To fill in Phase 2/3._

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
   positive.** I have not diagnosed the cause (hypotheses: FUELHH is metered output after
   curtailment/constraints whereas WINDFOR forecasts potential generation; different unit
   coverage). This is a short-lead sample only; day-ahead vintages are not yet measured.
3. **Section 3.2: the 09:30 cutoff coincides with a publication time** (section 2.6). Not a
   contradiction of the text, but it makes the "publishTime exactly equal to the cutoff" edge
   case the dominant case. The rationale given for 09:30 assumed vintages straddle it.
4. **Section 3.1:** the buffer start of 28 Dec is more generous than needed. The earliest vintage
   ever selected is 1 Jan 09:30. It is harmless and kept as specified.

Not contradictions (confirmed as written): WINDFOR is hourly (2.5), the alignment design in 3.3
applies, the API is keyless, and a usable vintage exists on every delivery day.

## 4. Decision cutoff (no-lookahead rule)

**Open: needs a decision before Phase 3.** The brief says `publishTime <= cutoff` is inclusive,
to be decided and documented. Because the 09:30 publication sits exactly on the cutoff on every
day:

- **Inclusive (`<=`)**: uses the 09:30 vintage. It assumes a forecast stamped 09:30:00 is on
  the desk at 09:30:00. The data cannot show how long after `publishTime` a forecast is actually
  available, so this is the optimistic reading and the one most exposed to a lookahead challenge.
- **Strict (`<`)**: uses the 07:30 vintage (2h older, so slightly worse accuracy). Conservative:
  a forecast is only used if it was published strictly before the decision moment.

Recommendation: strict `<`, with the inclusive result shown as a sensitivity. See the Phase 1
report.

## 5. Resolution alignment

**Decision (provisional, confirm in Phase 3).** Evaluate at WINDFOR's native hourly resolution.
For hourly target `T`, the actual is the mean of the two FUELHH half-hours with `startTime = T` and
`T + 30 min`, i.e. the "hour beginning T" convention, since `startTime` everywhere in this API is
the start of the interval. **This convention is assumed, not verified**: a nowcast test of four
alternative conventions (hour beginning, hour ending, centred, point) gave mean absolute gaps of
1,687 / 1,659 / 1,668 / 1,680 MW, a spread of under 2%, which is too small to discriminate
because the level offset (section 3.2) dominates and hourly wind output moves slowly. The
choice is therefore low stakes but should be stated openly.

## 6. Deduplication rule

No duplicates exist in the data as served (section 2.8). Rule for Phase 2: after concatenating
chunks, drop exact duplicate rows (chunk boundaries overlap because the range filter is inclusive
at both ends), then assert uniqueness of `(startTime, publishTime)` for WINDFOR and of
`startTime` for FUELHH WIND, and fail loudly if either is violated.

## 7. Missing data handling

_To fill in Phase 3._ Phase 1 result: 0 missing actuals, 0 missing forecast targets in the
delivery window, so expected coverage is 100%.

## 8. Metrics

_To fill in Phase 3._

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

_To fill in Phase 3._ January has no clock change: London time equals UTC, so
`09:30 Europe/London` is `09:30Z` for all 31 cutoffs. Not safe to extend to March or October
without an audit.
