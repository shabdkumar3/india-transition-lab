# M1 — Historical Electrolyser Cost / Deployment Dataset
## India Steel Transition Model — Phase 23 / Phase 25 / Phase 25B / Phase 25C (expanded)

**STATUS: DEFERRED / NOT_READY** (Phase 25C: the deployment half is now fully
recorded from official IEA sources back to 2015, and the paired dataset reaches
the 15-observation numeric threshold; M1 remains NOT_READY because the cost
boundary (stack vs system) is not per-row verified and the paired series spans
two IEA capacity vintages)

M1 (electrolyser learning parameter) may be activated ONLY when a qualifying
historical dataset exists. Under the M1 readiness criteria, the dataset must
provide:

- >= 15 usable observations
- consistent cost boundary (stack-only vs system vs turnkey must be separated)
- consistent deployment metric (cumulative installed capacity, GW)
- currency normalized (2015 USD / 2019 USD / nominal, with explicit conversion)
- technology tracked (alkaline vs PEM)
- chronological coverage sufficient
- source provenance complete

### Phase 23 finding (broad search)

No single gold-standard public series exists:
- **BloombergNEF** maintains a proprietary electrolyser price index; NOT publicly
  reproducible (no academic paper reproduces the full BNEF series).
- **IRENA (2020) "Green Hydrogen Cost Reduction"** provides historical SNAPSHOTS
  (e.g. PEM turnkey system ~USD 1000-2000/kW, 2018), not a continuous annual series.
- **DOE / NREL (H2A, Program Record 24005)** standardize system boundaries but
  provide current/target estimates, not a historical series.
- **IEA Global Hydrogen Review** tracks cumulative installed capacity (GW) but
  refers to external analyses for cost trajectories.
- **Schmidt et al. (2017, Nature Energy)** derive learning rates (10-20%/doubling)
  from expert elicitation — not a primary cost dataset.

### Phase 25 finding (cost side materially strengthened)

An open-access, peer-reviewed historical electrolyser CAPEX series was located
and verified:
- **Vatankhah Ghadim et al. (2025), "Clean technology cost projections: investment
  and levelized costs of solar, wind, battery, and hydrogen", Scientific Data,
  DOI 10.1038/s41597-025-05951-4** (fully open access). Dataset on Zenodo
  record 16417026 (V2.0, July 2025): "coding-friendly cost database - V1.0.xlsx"
  and "Clean energy cost database - Final version.xlsx".
- The database carries an `Actual_CAPEX` historical series per technology:
  - **Alkaline:** non-zero observations 2015, 2016, 2017, 2019, 2020, 2021, 2022
    (mean series USD/kW: 1164.59, 1138.42, 978.50, 1184.50, 983.65, 965.63, 978.50).
  - **PEM:** non-zero observations 2015-2018, 2020-2023 (mean series USD/kW:
    2621.81, 1920.81, 1670.27, 1252.71, 1217.46, 992.23, 1234.76, 1718.20).
  - Unit per database convention is USD/kW, system-level; the database provides
    conversion rates to 2024 USD. Rows store `base_year` = observation year
    (nominal). Per-row boundary not independently verified.
  - MEAN-ONLY RATIONALE: the source's `Actual_CAPEX_min`/`max` series is NOT
    internally coherent (e.g. alkaline 2017 min 1417.61 > mean 978.50; PEM
    min/max exist only for 2022-2023). Only the mean was recorded — do NOT
    "complete" the series later with the unreliable min/max bounds.
- These 15 annual mean observations were added to
  `electrolyser_cost_deployment.csv` as **M1_ANCHOR_ONLY** rows (Phase 25).

### Phase 25 consequence (why M1 is STILL NOT_READY)

Even with the Nature Scientific Data 2025 series, the M1 readiness criteria are
NOT fully satisfied:
1. **Deployment metric missing:** the database is cost-focused; it does NOT
   contain a cumulative installed capacity (GW) series by year for electrolysers.
   The paired cost+cumulative-capacity dataset required for a learning-curve
   regression still cannot be constructed from verified public sources.
2. **Cost boundary not per-row verified:** the database aggregates system-level
   costs across studies; stack vs system boundary is not independently confirmed
   per row. Confidence stored as MEDIUM for the Phase 25 rows.
3. **Currency/base-year normalization** to a single reference year is provided by
   the database conversion sheet (2024 USD reference) but NOT applied to the
   recorded rows. The Phase 25 rows store `base_year` = observation year
   (nominal, as reported), matching the file's existing convention; a future
   normalization decision must convert all rows to one canonical base before
   M1 can be fitted.

### Phase 25B update (deployment side now recorded — see M1_DEPLOYMENT_EVIDENCE_REPORT.md)

The deployment metric is no longer entirely missing. Verified IEA cumulative
installed capacity (year-end, dedicated water electrolysis, excluding
chlor-alkali) is recorded as `deployment_anchor` rows in
`electrolyser_cost_deployment.csv`:
- **Total:** 2020 = 0.33 GW, 2021 = 0.57 GW, 2022 = 0.70 GW, 2023 = 1.39 GW,
  2024 = ~2.0 GW (IEA Global Hydrogen Review 2024: "Installed water
  electrolyser capacity reached 1.4 GW by the end of 2023"; GHR 2025 end-2024
  estimate ~2 GW).
- **Technology split (IEA tracking page / Hydrogen Projects Database, 2020-2023):**
  ALK 200/370/400/840 MW; PEM 110/150/240/300 MW; Other 20/50/60/250 MW.
  The split sums match the totals exactly (330/570/700/1390 MW) — internal
  consistency verified. Technology split rows carry MEDIUM confidence (per-year
  table not page-verified); total rows carry HIGH confidence (GHR 2024 quote).
- **Technology-compatible paired observations (Phase 25B):** 7 pairs existed
  where the Nature SD cost series and the IEA technology-specific cumulative
  capacity overlap in 2020-2023 (ALK 2020/2021/2022; PEM 2020/2021/2022/2023).

### Phase 25C update (pre-2020 technology split now verified — see M1_PRE2020_DEPLOYMENT_REPORT.md)

The pre-2020 gap is CLOSED using the official IEA chart **"Global installed
electrolysis capacity by technology, 2015-2020"** (IEA data-and-statistics
chart, source: IEA 2021 Hydrogen Projects Database; chart data CSV extracted
from the official chart page, GHR 2021 p.116 figure):

| Year | Alkaline (MW) | PEM (MW) | SOEC (MW) | Unknown (MW) | Total (MW) |
|---|---|---|---|---|---|
| 2015 | 133.77 | 18.89 | 0.00 | 7.03 | 159.69 |
| 2016 | 136.85 | 20.55 | 0.00 | 7.40 | 164.80 |
| 2017 | 140.41 | 20.67 | 0.00 | 7.45 | 168.53 |
| 2018 | 145.83 | 37.75 | 0.07 | 7.56 | 191.21 |
| 2019 | 149.51 | 61.27 | 0.07 | 11.81 | 222.66 |
| 2020 | 175.76 | 89.26 | 0.79 | 21.12 | 286.93 |

Internal consistency with GHR 2021 p.116 text verified: 2020 total 290 MW
(rounding), 61% alkaline (175.76/286.93 = 61.3%), 31% PEM (89.26/286.93 =
31.1%), SOEC 0.8 MW (0.79). **25 new deployment anchors (2015-2019)** added to
`electrolyser_cost_deployment.csv` (42 deployment anchors total; 60 rows
overall), all `M1_ANCHOR_ONLY`. The 8 pre-2020 Nature SD cost rows
(ALK 2015/2016/2017/2019; PEM 2015/2016/2017/2018) now carry their
technology-compatible cumulative capacity.

**IEA internal revision (documented, SC-14):** the GHR 2021 chart gives 2020
total 286.93 MW (ALK 175.76 / PEM 89.26), while the later IEA tracking page /
Hydrogen Projects Database gives 330 MW (ALK 200 / PEM 110). Both series are
kept with explicit source labels; the 2020+ pairs use the tracking series, the
2015-2019 pairs use the GHR 2021 chart series.

### Phase 25C readiness status (recorded separately, per Phase 25C decision rule)

- **COST_DATASET_READY = TRUE** (18 cost rows: 15 Nature SD annual means +
  3 IEA/IRENA parameter rows).
- **DEPLOYMENT_DATASET_READY = TRUE** (42 deployment anchors, official IEA,
  2015-2024 totals + technology splits 2015-2023).
- **PAIRED_DATASET_READY = CONDITIONAL / NOT CLAIMED**: 18 paired rows exist
  (9 Alkaline + 9 PEM); of these 15 are Nature SD point observations paired
  with technology-compatible capacity — the numeric >=15 threshold is MET.
  Readiness is NOT claimed because (a) the Nature SD per-row stack-vs-system
  cost boundary is not independently verified, and (b) the paired capacity
  series spans two IEA vintages (GHR 2021 chart 2015-2019, tracking
  2020-2023) with a documented 2020 revision.
- **M1_READY = FALSE** — M1 remains **DEFERRED / NOT_READY.**

No synthetic data has been created. The Phase 25C anchors are recorded for
future dataset construction (documented, not promoted). Do NOT fit M1.

### Data dictionary — electrolyser_cost_deployment.csv columns

| Column | Type | Meaning |
|---|---|---|
| year | int | Calendar year of the observation |
| technology | str | Alkaline / PEM (as reported by the source) |
| cumulative_installed_capacity_gw | float (nullable) | Global cumulative installed capacity in GW; null where no page-verified figure was available in this phase |
| cost_low / cost_high | float (nullable) | Cost range endpoints (USD/kW or USD/kWe); a single verified point is stored as low == high. No fabricated midpoint is ever recorded |
| cost_unit | str | USD/kW or USD/kWe |
| currency / base_year | str / int | Currency and base year of the cost |
| system_boundary | str | stack-only / process-equipment+EPC / turnkey system — kept explicit so boundaries are never silently combined |
| geography | str | Global / India |
| source | str | Verbatim source title |
| page_or_table | str (nullable) | Page/table reference where available |
| confidence | str | HIGH / MEDIUM / LOW |
| observation_type | str | historical_snapshot / historical_parameter / historical_parameter_bounds |
| status | str | Always `M1_ANCHOR_ONLY` — anchors for future dataset construction, NOT a qualifying M1 dataset |

### Verified anchor points (for future use)

See `electrolyser_cost_deployment.csv`. Only source-verified data points are
listed; all are contextual anchors, NOT a qualifying M1 dataset. Rows are
historical observations/parameter values only (no projections); cost ranges are
stored as `cost_low`/`cost_high` pairs (no fabricated midpoint). Deployment
(cumulative installed capacity GW) is left null where no page-verified figure
was available in this phase.

Phase 25 rows (Nature Scientific Data 2025) are the first genuine HISTORICAL
COST SERIES in the file: 7 alkaline + 8 PEM annual mean observations
(2015-2023, USD/kW, system-level per database convention, MEDIUM confidence).
They remain M1_ANCHOR_ONLY — recorded, not promoted — because the paired
deployment series is still absent.

### What is still needed to reach M1_READY

1. **Per-row cost-boundary verification** for the Nature Scientific Data 2025
   rows (stack vs system), or a normalization decision fixing one boundary
   across all observations — the single remaining blocker after Phase 25C.
2. A currency/base-year normalization decision (2024 USD per the database
   conversion sheet) applied uniformly across all rows.
3. Resolution of the IEA capacity-vintage break at 2020 (GHR 2021 chart vs
   tracking page, SC-14) or an explicit series-selection decision.
4. (Optional) BNEF historical electrolyser price index or IRENA 2020 appendix
   tables as a cross-check of the cost series.

Until then: **M1 remains DEFERRED. Do NOT fit M1.**
