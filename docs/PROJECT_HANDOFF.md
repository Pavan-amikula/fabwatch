# FabWatch: complete project handoff for résumé and interviews

## Short identity

**Project:** FabWatch — Semiconductor Manufacturing Quality Intelligence

**Repository:** https://github.com/Pavan-amikula/fabwatch

**Demonstration:** https://github.com/Pavan-amikula/fabwatch/blob/main/docs/media/fabwatch-demo.mp4

**Type:** Independent engineering ML portfolio project. Real public historical data; working local application and ingestion API; no factory deployment.

**Stack:** Python, pandas, NumPy, SciPy, scikit-learn, SQL/SQLite, FastAPI, Pydantic, HTML/CSS/JavaScript, SVG charts, pytest, GitHub Actions, Docker configuration. CSV statistical-tool handoff and example Power Query/DAX are included. No JMP, Minitab, or Power BI execution has been verified.

## Business and engineering problem

Semiconductor process analysis involves high-dimensional, incomplete measurements, rare failures, changing distributions, and delayed test outcomes. Engineers need to inspect the quality of their inputs, compare statistical and ML baselines, keep outcomes distinct from predictions, and translate suspicious records into traceable investigations. FabWatch implements this workflow and reports when a model is not useful enough to act on.

## Dataset

UCI SECOM by Michael McCann and Adrian Johnston (2008), DOI 10.24432/C54305, CC BY 4.0. The numeric release contains 1,567 production entities, 590 anonymous sensor columns, and 104 failures. Missing fraction is 4.538%. The earliest training period contains 122 constant or effectively empty signals. Dates span July-October 2008. IDs are synthetic identifiers tied deterministically to source row numbers, not real lot or equipment IDs.

The catalog lists 591 features, while the actual numeric matrix contains 590 sensor columns. The project verifies the downloaded shape and documents this discrepancy rather than silently assuming the catalog dimension. No large-scale data claim is warranted for this small benchmark.

## What was implemented

1. **Source integrity and validation:** downloaded the public release, pinned file SHA-256 hashes, validated matrix shape, labels, infinities, and timestamp parsing.
2. **Temporal modeling:** sorted records by test timestamp and kept tied timestamps in the same partition; used separate fitting, calibration, policy-selection, and final-test intervals.
3. **Preprocessing:** training-only median imputation and missing indicators; constant-column removal; F-test feature selection; standard scaling.
4. **Original model comparison:** logistic regression, Extra Trees, random forest, and histogram gradient boosting; separate calibration; policy-set AP/Brier selection; hypothetical cost-based operating threshold. A training-pass-only Isolation Forest provides an anomaly reference.
5. **Uncertainty and evidence:** day-block bootstrap intervals, PR/ROC plots, confusion matrix, Brier score, explicit false-review/missed-failure counts, saved predictions, source/split/model provenance, and warm CPU pipeline profiling.
6. **Continuous-ingestion demonstration:** local JSON ingress with 590 numeric/null measurements, ID and timestamp validation, historical test replay, ten-arrival synthetic outcome delay, and a frozen model.
7. **SQL warehouse:** normalized entities, predictions, outcomes, investigations, audit events; primary and foreign keys; WAL; transactions; idempotent repeated ingestion; conflicting-ID rejection; restart checkpoint recovery.
8. **Quality and process safeguards:** missingness abstention; training-associated signal deviations; exploratory EWMA chart using frozen training references. No physical sensor causes, specification limits, OEE, Cp/Cpk, or guaranteed lead time are invented.
9. **Engineering workflow:** dashboard with operations, investigation queue, data/process health, and model evidence; owner/status/notes editing; audit history; CSV handoff and a KPI dictionary.
10. **Verification and communication:** automated tests, reproducible CI configuration, measured operational replay, desktop browser verification, screenshots, a captioned video walkthrough, and full documentation.

## Verified outcomes

- 29 local automated tests passed.
- Complete replay: 314 entities scored, 304 outcomes revealed, 10 pending by the declared delay.
- Three missingness holds and five process-reference excursions created eight traceable investigation cases.
- The five excursions corresponded to passing records: they are diagnostic follow-up triggers, not demonstrated failure detections.
- All 314 entity-evidence responses were checked.
- Measured original model warm pipeline p95: approximately 5.16 ms per row on the local CPU; excludes HTTP, SQL, and explanation time.
- The UI was exercised through replay, view navigation, entity inspection, and a saved investigation assignment/note. This is local functional validation, not production rollout.

## Model evidence: exact wording matters

Original chronological split: 783 training entities / 235 calibration / 235 policy / 314 test. Failure counts: 67 / 9 / 11 / 17. The original selected model was sigmoid-calibrated histogram gradient boosting.

Original test AP was 0.06359, compared with test prevalence 0.05414; ROC AUC was 0.51238. The development-selected 10:1 error-cost rule disabled alerts, missing all 17 failures and achieving no hypothetical cost improvement over pass-all. This result is preserved. It should not become a résumé claim of strong failure prediction, 94% model accuracy, 94% manufacturing yield improvement, or successful deployment.

After inspecting the original result, a separate challenger study tried seven declared additional models (SVMs and full-signal/smaller-feature tree/logistic baselines), using only the original training and policy partitions for fitting/selection. The selected full-signal random forest achieved AP 0.11061, ROC AUC 0.66271, 4/17 detected failures, 30 false reviews, and 50.96 hypothetical cost units per 100 entities on the **already-inspected test period**. This is exploratory; it was not promoted into serving and needs a new future/site evaluation. Do not present it as an independently validated production gain.

## Ready-to-use résumé bullets

Choose two or three based on space:

- Built a semiconductor manufacturing analytics workbench using Python, scikit-learn, FastAPI, and SQL, integrating 590-signal process records with quality validation, failure-risk screening, and engineering investigation workflows.
- Implemented chronological train/calibration/policy/test separation, train-only preprocessing, rare-event evaluation, cost-sensitive thresholds, and day-block bootstrap analysis; documented weak generalization and retained the original frozen model evidence.
- Developed an auditable SQLite pipeline with idempotent ingestion, delayed outcome tracking, standardized yield KPIs, missingness abstention, exploratory EWMA monitoring, and owner/status-based investigation handoffs.
- Verified a 314-entity historical replay and 314 entity-evidence responses; passed 29 automated tests covering data contracts, temporal separation, frozen prediction parity, conflict handling, recovery, and reporting.

Optional research-specific bullet, only with its qualifier intact:

- Evaluated seven additional development-selected ML challengers; an exploratory random forest achieved AP 0.111 and ROC AUC 0.663 on a reused historical test period, with new future/site validation identified as the next model-promotion requirement.

## Relevant keywords supported by implementation

Engineering data analysis; semiconductor manufacturing analytics; failure-risk modeling; yield analytics; statistical process monitoring; EWMA; anomaly-reference baselines; rare-event classification; class imbalance; calibration; precision-recall; Brier score; chronological validation; data quality; missing-data handling; root cause investigation support; KPI standardization; Python; pandas; NumPy; SciPy; scikit-learn; SQL; SQLite; FastAPI; REST API; Pydantic; automated reporting; data visualization; data provenance; reproducibility; pytest; GitHub Actions; engineering handoff; audit trail.

## Terms requiring qualification

- **Real-time:** the app supports local ingestion and dashboard updates; the demonstrated source is historical replay. No live fab feed exists.
- **Root cause analysis:** the app supports investigation and reference deviations; it does not prove causal root causes.
- **Yield:** observed entity pass fraction only. No interventions or verified improvement.
- **Power BI/JMP/Minitab:** compatible exports and integration guidance, not tool execution or hands-on proprietary-tool proficiency.
- **Deployment:** local CPU prototype. Docker and CI configuration do not imply factory deployment, cloud hosting, or industrial scale.
- **Experience:** independent project work does not become employment, three years of industry experience, or a completed industrial thesis.

## Suggested interview explanation

“I built FabWatch to connect semiconductor process data with an engineering decision workflow. I started with the data contract and time-based evaluation rather than optimizing accuracy on a random split. The original model did not establish useful failure detection, so I kept that limitation visible and separated model risk from data quality and statistical process investigations. The application still demonstrates ingestion, outcome tracking, SQL KPIs, evidence inspection, ownership, and reproducible reporting. A later challenger showed a stronger exploratory ranking, but I would require a new future or site holdout and engineer-reviewed shadow evaluation before promoting it.”

## Request for the résumé-writing chat

Use this handoff as factual project evidence. Tailor the résumé toward Coherent's Machine Learning & AI Specialist role using supported keywords and the verified engineering outcomes. Keep the project independent and local, preserve the distinction between frozen and exploratory results, and do not invent industrial deployment, yield savings, employer collaboration, physical causes, proprietary-tool experience, or degree completion. Do not turn observed pass yield into model accuracy.
