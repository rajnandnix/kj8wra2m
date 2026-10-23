# Assumptions and verified facts

Every assumption is recorded here as it is made, with the reasoning. Anything marked
**Verified** was checked against a live API response; anything marked **Decision** is a
design choice.

## 1. Scope and date interpretation

_To fill in Phase 2/3._

## 2. Elexon API facts (Phase 1, verified against live responses)

### 2.1 FUELHH: URL, parameters, sample response
### 2.2 WINDFOR: URL, parameters, sample response
### 2.3 Response envelope shape
### 2.4 FUELHH startTime spacing
### 2.5 WINDFOR startTime spacing
### 2.6 WINDFOR publication cadence (distinct publishTime values on a sample day)
### 2.7 WINDFOR forecast horizon
### 2.8 Duplicate (startTime, publishTime) pairs
### 2.9 Timestamp timezone format
### 2.10 FUELHH completeness on a sample day
### 2.11 Maximum date range per request
### 2.12 Rate limiting

## 3. Contradictions with the project brief

_To fill after Phase 1._

## 4. Decision cutoff (no-lookahead rule)

_To fill in Phase 3._

## 5. Resolution alignment

_To fill in Phase 3._

## 6. Deduplication rule

_To fill in Phase 2._

## 7. Missing data handling

_To fill in Phase 3._

## 8. Metrics

_To fill in Phase 3._

## 9. Known data caveats

- FUELHH covers transmission-metered, BM-registered generation. Embedded
  (distribution-connected) wind is not included.
- WINDFOR likewise covers BM Unit wind. The two are broadly comparable in scope, but
  neither is total national wind.
- Any scope discrepancy between the two datasets is a source of systematic bias that
  this analysis cannot separate from genuine forecast error.

## 10. Daylight saving

_To fill in Phase 3. January has no clock change._
