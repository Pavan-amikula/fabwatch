# BI and statistical-tool handoff

FabWatch implements statistical analysis in Python and a custom operational dashboard. It exports data for Power BI, JMP, and Minitab; it does **not** claim those proprietary tools have been run.

## Standardized KPI dictionary

| SQL field | Definition | Important distinction |
|---|---|---|
| `scored` | Count of scored entities for source test day | Not factory throughput |
| `outcomes_known` | Count with a revealed test outcome | Pending records excluded from yield |
| `observed_pass_yield` | Pass outcomes / known outcomes | Entity pass fraction; not die yield or verified first-pass yield |
| `mean_risk` | Mean frozen-model failure probability | Not observed failure rate |
| `review_count` | Model-triggered review count | Does not include reference excursions |
| `abstentions` | Records blocked by missingness gate | Does not automatically imply failure |
| `missing_fraction` | Mean fraction of null sensors | Source completeness, not imputation quality |

## Power BI Desktop

For a one-time import, download `/api/export/kpis`, then Get Data > Text/CSV. To configure a refreshable local query, use the included Power Query text as an example and keep the local API running. Review date and decimal types. No `.pbix` artifact or Power BI service deployment is supplied or verified.

For a total pass fraction across days, **do not average daily yield without weights**. Use:

```dax
Observed Pass Yield =
DIVIDE(
    SUMX(kpis, kpis[observed_pass_yield] * kpis[outcomes_known]),
    SUM(kpis[outcomes_known])
)
```

Rows with unknown yield should remain null. Keep predicted risk in a distinct visualization from observed outcomes.

## JMP / Minitab

Open the CSV exports through each tool's text import. `reports/sensor_quality.csv` provides anonymous signal completeness and training associations; `reports/test_predictions.csv` provides the offline test evidence. `reports/split_manifest.csv` retains partition provenance. Do not train or select thresholds from the test export.

For a statistical review: inspect missingness, compare training and later period distributions, review appropriate control chart assumptions, and investigate drift. No engineering specification bounds are supplied, so Cp/Cpk must not be inferred. The operational database is more complete than CSV for audit history because IDs link tables.
