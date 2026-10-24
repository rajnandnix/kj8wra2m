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
hourly/half-hourly mismatch described in brief section 2.2 and 3.3 **exists**, so section 3.3
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

## 3. Contradictions with the project brief (brief)

1. **Section 2.1 and 2.2 suggest `from`/`to` as a likely parameter pair. They are silently
   ignored** and return today's data with HTTP 200 (section 2.1). Use `publishDateTimeFrom/To`
   (or `settlementDateFrom/To` for FUELHH) and validate the returned range.
2. **Section 2.3 and 3.4 assume the two datasets are broadly comparable in scope. They are not.**
   Measured against FUELHH, WINDFOR runs about 13% high at short lead (+1,473 MW, correlation 0.957)
   and 15.5% high at the day-ahead cutoff (bias +1.75 GW). **Validated in section 8.2 as a scope
   difference, not a bug:** FUELHH excludes embedded wind, which independent sources put at about
   2.5 GW on average, and against full-fleet outturn the day-ahead bias is slightly negative.
3. **Section 3.2: the 09:30 cutoff coincided with a publication time** (section 2.6), making the
   "publishTime exactly equal to the cutoff" edge case the dominant case. Resolved by replacing
   the round number with real gate-closure times (section 4).
4. **Section 3.1:** the buffer start of 28 Dec is more generous than needed. The earliest vintage
   ever selected is 1 Jan 09:30. It is harmless and kept as specified.

Not contradictions (confirmed as written): WINDFOR is hourly (2.5), the alignment design in 3.3
applies, the API is keyless, and a usable vintage exists on every delivery day.

## 4. Decision cutoff (no-lookahead rule)

**Decision (product owner), replacing the round-number 09:30.** The cutoff is the gate closure of
a real GB day-ahead auction, at wall-clock time on D-1 in Europe/London. The three times are
**verified against the exchanges' own documentation** (product owner's check, with sources below):

- **09:20 UK time, EPEX SPOT GB 60 minute day-ahead auction** and **15:30 UK time, EPEX SPOT GB 30 minute
  day-ahead auction.** Source: EPEX SPOT Trading brochure (the December 2024 edition lists the GB
  60 minute auction at 09:20 and the 30 minute auction at 15:30), and EPEX SPOT's 2020 annual report
  section "After Brexit: integration of a decoupled market" (the 60 minute auction moved from 11:00
  to 09:20 for trading day 31 December 2020).
- **09:50 UK time, Nord Pool N2EX day-ahead auction.** Source: Nord Pool support article "About the N2EX
  day-ahead auction" ("Gate closure time is 09:50 GMT / 10:50 CET"), and Nord Pool's Q4 2020 announcement
  of the GB auction changes for Brexit.

What I could and could not check myself: I read the Nord Pool article directly. EPEX SPOT's PDF and annual
report pages returned HTTP 403 to my fetch, so for EPEX I rely on the product owner's check plus search
summaries of those documents, not on having opened them. One secondary source (S&P Global, a December
2020 notice) gave a different N2EX time (09:40); the exchange's own documentation says 09:50 and is
followed here. None of these documents was checked for changes after 2024. In January the UK is on GMT,
so the UK times equal UTC on all 31 days.

| Key | Time | Auction | Role | WINDFOR vintage selected |
|---|---|---|---|---|
| `epex60` | 09:20 | EPEX SPOT GB 60 minute | **primary**, earliest gate, lookahead-safe | 07:30 |
| `n2ex` | 09:50 | Nord Pool N2EX | sensitivity | 09:30 |
| `epex30` | 15:30 | EPEX SPOT GB 30 minute | sensitivity | 11:30 (12:25 on one day) |

All three live in `config.CUTOFFS`; the primary is `config.PRIMARY_CUTOFF`. The full metric set
is computed at all three and compared in the UI.

Comparison operator: `publishTime + PUBLICATION_LAG <= cutoff`, i.e. `<=` is kept.

**One publication does land exactly on a boundary, and the lag is deliberate conservatism.**
WINDFOR publishes at 15:30 UTC, which is exactly the 15:30 gate closure. The product owner's
premise that "no publication time lands exactly on a boundary" holds for 09:20 and 09:50 but not
for 15:30 (the premise was acknowledged as theirs and the fix confirmed). The reasoning: **a
forecast stamped 15:30:00 is not on the desk of someone submitting into a 15:30:00 gate.** So
`config.PUBLICATION_LAG = 1 minute`: a forecast stamped t is treated as in hand from t + 1 min,
and the comparison stays `publishTime + lag <= cutoff`. This is a choice for lookahead safety,
not a workaround: it makes the 15:30 cutoff use the 11:30 vintage, as intended. Only that cutoff is
affected. With the lag at zero the 15:30 gate would use the 15:30 vintage and measure MAE
1,873.5 MW against 1,904.0 MW with the lag, so the conservative choice costs 30 MW of apparent
accuracy.

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

**Procurement band** (brief section 3.5), **conditional on forecast level.** realised = forecast
- error, so the realised wind lies in [forecast - P90, forecast - P10]. The P10 and P90 are taken
from the bucket the hour's forecast falls in (0-6, 6-10, 10-14, 14+ GW, left-closed), because bias
grows with the forecast level. Each hour of a delivery day uses its own bucket; the headline
shows day averages, and MWh is the sum over hours of the hourly P90 cover (floored at zero) x 1 h.
Buckets step where a forecast crosses an edge, so the band is not smooth there. It is an empirical,
**in-sample** band (fitted and scored on the same 744 hours, including the displayed day) and not a
probabilistic forecast. One month cannot support out-of-sample validation, so coverage in other
periods is unknown and probably lower. An informal leave-one-day-out check gave 76.5% hour
coverage against 79.3% in-sample (diagnostic only, not a validation).

In-sample coverage at the primary cutoff (hours whose actual fell inside the band):

| Forecast level | Hours | P10 / P50 / P90 of error (MW) | Conditional band | Single global band |
|---|---|---|---|---|
| < 6 GW | 63 | -832 / +1,127 / +2,239 | 77.8% | 74.6% |
| 6-10 GW | 182 | -1,604 / +936 / +2,607 | 79.1% | 68.7% |
| 10-14 GW | 163 | -53 / +1,506 / +3,305 | 79.1% | 89.0% |
| >= 14 GW | 336 | +537 / +2,388 / +4,730 | 79.8% | 82.4% |
| **All** | 744 | | **79.3%** | **79.8%** |

Overall coverage is about the same (both target the middle 80%); the gain is that coverage is now
even across levels (78-80% each) where the single global band ranged 69-89%, and the cover to hold
at P90 is sized to the forecast (2.2 GW below 6 GW, 4.7 GW at 14 GW and above, against 4.1 GW for
everything). Coverage clusters by day: with the conditional band 8 of 31 days are fully inside
and 9 Jan is 20 of 24 hours inside while 28 Jan is 0 of 24, so a per-hour "8 in 10" statement
understates day-level risk.

**Default demo day** is 9 Jan (a day where the band works); 28 Jan (the largest miss at the primary
cutoff) is kept as the cutoff-sensitivity example, where the 15:30 gate cuts that day's MAE from
5,375 to 2,991 MW because the 11:30 publication revised the 07:30 to 09:30 forecast down by 1 to 3
GW. Both are config constants.

**Cutoff comparison:** paired on common intervals, 95% interval from a day-block bootstrap
(whole delivery days resampled, 2,000 resamples, fixed seed) because errors within a day are
correlated. "Materially better" requires at least 3% MAE improvement; the verdict says so when
the interval includes zero.

### 8.1 Curtailment hypothesis (time-boxed)

Hypothesis: WINDFOR forecasts available wind, FUELHH records metered output after curtailment,
curtailment concentrates in high-wind periods, so the gap should scale with generation level.

- Bucketed on *actual* output the gap does not scale cleanly (bias +1.86 GW below 6 GW, +1.14 at 6-10,
  +1.22 at 10-14, +2.40 at 14+; level explains 2.8% of error variance), but conditioning on the outcome
  mechanically inflates low buckets.
- Bucketed on *forecast* the gap scales: +0.77, +0.73, +1.68, +2.51 GW across the four buckets; slope
  0.19 MW per MW of forecast, R2 0.27 (0.35 at 15:30).
- **Revised after section 8.2:** the level dependence is explained mainly by embedded wind, which rises
  with the wind (about 1.2 GW on the lowest-wind day, 4.9 GW on the highest). Curtailment of metered
  output may contribute but was not separated; AGWS and FUELHH-plus-embedded agree closely at the top
  end, so there is no evidence here that curtailment is the main driver.

### 8.2 Scope validation: is the offset a bug? (answer: no, it is scope)

Run once, from `scripts/scope_check.py`, against independent public sources: NESO Historic Demand Data
2026 (`EMBEDDED_WIND_GENERATION`, capacity 6,417 MW) and Elexon AGWS (actual aggregated wind
generation, onshore plus offshore). Delivery window 2 Jan to 1 Feb 2026.

1. **Maxima.** FUELHH WIND max 17,805 MW; WINDFOR max 21,353 MW (20% higher; at short lead the
   ratio is 1.20); AGWS max 22,569 MW; FUELHH plus embedded max 23,021 MW. WINDFOR's maximum sits well
   above FUELHH's, which is the signature of a different fleet. Means (short-lead WINDFOR): FUELHH
   11,284, WINDFOR 12,765, AGWS 13,449, FUELHH plus embedded 13,763 MW.
2. **Shape and timing.** Short-lead WINDFOR is a near-proportional scale of FUELHH
   (`forecast = 1.135 x actual - 39 MW`, correlation 0.957), and correlates better with AGWS (0.976)
   than with FUELHH. Shifting the actual by +/- 1 to 4 hours worsens the match steadily, so there is no
   timing bug. (A -1 h shift is marginally best, correlation 0.958 against 0.957: a weak hint that
   WINDFOR labels hour-ending, flagged but not acted on.)
3. **Orders of magnitude, two days.** High-wind day 27 Jan, daily mean: FUELHH 16,409 MW; AGWS 20,759;
   NESO embedded 4,905; FUELHH plus embedded 21,313; WINDFOR (short lead) 19,690. Low-wind day 8 Jan:
   FUELHH 4,528; AGWS 5,815; embedded 1,194; FUELHH plus embedded 5,722; WINDFOR 5,664 (within 1%).
   FUELHH is the right order of magnitude and is about 22% below the full fleet on average.
4. **Day-ahead error against different definitions of "actual wind"** (09:20 cutoff, 744 hours):

| Actual wind defined as | MAE | RMSE | Bias | nMAE | Debiased MAE |
|---|---|---|---|---|---|
| FUELHH only (what the app uses) | 2,039 | 2,505 | +1,748 | 18.1% | 1,376 |
| FUELHH + NESO embedded wind | 1,518 | 1,939 | -731 | 11.0% | 1,386 |
| Elexon AGWS national wind | 1,330 | 1,723 | -418 | 9.9% | 1,284 |

Conclusion: the +1.75 GW offset is scope. Against fuller outturn series the forecast is slightly *low*, with
nMAE 10 to 11%. The app deliberately keeps FUELHH (brief: evaluate the forecast as published) and says
so on screen. The debiased MAE against FUELHH (1,376 MW) is therefore mostly a dataset reconciliation,
not forecast skill: the same bias-removal step against the two fuller series improves MAE by only
8.7% (1,518 to 1,386 MW) and 3.4% (1,330 to 1,284 MW). The fuller series are the closest available match,
not a perfect one: WINDFOR's short-lead mean still sits about 0.7 to 1.0 GW below them. WINDFOR's exact
fleet definition was not found in documentation; "WINDFOR covers embedded wind" is an inference from
these numbers.

**I did not find a published benchmark** for GB national day-ahead wind error, so there is no source for
calling 10% of mean output "normal". NESO declined an FOI request on the question, and the closest published
figures (ESO incentive targets for metered wind) use a different metric and fleet. The app therefore
states 10% as a measured figure and does not call it typical.

### 8.3 Scope boundary: a deliberate, disclosed exception

The brief restricts the product to two datasets, Elexon FUELHH and WINDFOR. **The application honours
that.** During analysis the error looked implausibly high, so I went outside that scope for **one
cross-check only**, to establish whether the forecast or the comparison was wrong. The check used Elexon
AGWS (another BMRS dataset, actual aggregated wind generation) and NESO's embedded-wind estimate (a
different organisation's data). It lives in a standalone script, `scripts/scope_check.py`, not in the
application, and it produced the main finding. The application never queries those sources: its Accuracy
view shows the script's 09:20 results as fixed text, labelled as fixed to that cutoff.

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
