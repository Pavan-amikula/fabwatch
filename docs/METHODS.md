# Experiment and operational contract

## Question

Can measurements from historical semiconductor production entities usefully rank final test failure risk on a later time interval, and can the same data support a traceable quality investigation workflow?

## Dataset and time

1,567 entities, 590 numeric signals, 104 failures. Original release dates: July-October 2008. IDs are deterministic source-row identifiers, not real factory identifiers. Rows are sorted by parsed test timestamp and source row. Equal timestamps never cross a partition boundary. The test timestamp is not documented as the sensor-availability time: this benchmark cannot establish advance warning or online lead time.

## Declared fitting procedure

| Partition | Purpose | Entities | Failures |
|---|---|---:|---:|
| Earliest 50% | Fit all preprocessing, classifiers, and reference statistics | 783 | 67 |
| Next 15% | Fit sigmoid calibrators | 235 | 9 |
| Next 15% | Choose calibration, model, and operating threshold | 235 | 11 |
| Latest 20% | Final chronological test | 314 | 17 |

All pipelines: training median imputation with missing indicators, constant-feature removal, F-test selection of 60 transformed features, standard scaling, classifier. Candidates and fixed hyperparameters are declared in `fabwatch/train.py`: logistic regression, Extra Trees, random forest, histogram gradient boosting. Class weights are used for the first three. No resampling crosses partitions. No test data fits transformations.

For each candidate, sigmoid calibration is fitted using log-odds on the calibration interval. Policy Brier score decides calibrated versus raw output. Policy average precision selects a classifier; policy Brier breaks ties. Calibration is not guaranteed to improve generalization. Only nine calibration failures make probability estimates particularly uncertain. Histogram gradient boosting won this declared development comparison. Checking its calibration coefficient after the first result did not alter any model, features, split, or threshold.

Threshold minimizes `10 * missed_failures + false_alerts` on policy data, with lower alert volume breaking ties. Costs are hypothetical and do not represent currency or measured business losses. Candidate thresholds include a value above 1 to permit disabling alerts. This selected **1.000001**, meaning no model-triggered risk reviews. The dashboard must not present this as successful fault detection.

## Held-out findings

- Average precision: 0.063589 versus 0.054140 test prevalence / constant-score baseline.
- ROC AUC: 0.512379.
- Brier: 0.051818 versus 0.052197 for the training-prevalence baseline.
- At the selected threshold: 0/17 failures detected; 0 false reviews; 297 true negatives.
- Hypothetical cost: 54.1401 units per 100 entities, identical to pass-all.
- Training-pass-only Isolation Forest reference: test AP 0.052926.
- 500 day-block bootstrap resamples: AP interval approximately [0.02356, 0.12109]. This is uncertainty within this small test period, not external-fab validation. Repeated entities are not known, so residual dependency may remain.

The classifier is **not recommended for autonomous failure decisions**. Selecting a lower threshold after viewing test labels would be test tuning; this project preserves the original operating point. Model evidence is reported separately from operational gates and reference excursions.

## Operational safeguards and separate signals

- Missingness gate: abstain when the missing-sensor fraction exceeds max(15%, training 99th percentile). The score remains visible for analysis but is not used to grant a quality release. There are three such holds in the complete held-out sequence.
- Exploratory process references: select twelve sensors with at least 70% training availability using absolute standardized train failure/pass mean differences. At inference, flag a process investigation when any selected signal is more than 3 training SD from its training median. This creates five reference excursions on the test sequence; overlapping reasons may share one queue entry.
- Multiple comparisons and drift can cause false reference alarms. These are diagnostic flags, not validated defect detectors or causal attribution. No test-derived signal ranking or physical sensor interpretation is used.
- EWMA is a separate visual monitor on the first training-associated sensor, using the training mean and SD. It does not change the risk classifier or predict causal failures.
- Labels are revealed after a synthetic delay of ten arrivals to demonstrate pending outcomes. This is not measured production latency. The last ten records remain pending at the end of replay; full evaluation has all 314 historical labels.
- Predictions, outcomes, investigations, and audit events are separate SQL tables. Entity IDs are idempotent; conflicting measurements are rejected. Reserved SECOM IDs cannot be submitted through external ingress.
- The source data and serialized model have SHA-256 integrity checks. Joblib artifacts are loaded only from locally produced files; never load an untrusted model pickle.

## Limits and next validation

No factory integration, equipment validation, causal experiment, external site, industrial deployment, cost reduction, yield improvement, or production-ready alerting is demonstrated. The source is small, old, anonymized, and has no lot/tool groups. The project therefore demonstrates engineering delivery and evaluation discipline, not manufacturing scale or industrial employment.

A real next experiment would collect named sensor/time-availability contracts, equipment and lot genealogy, failure taxonomy, and agreed review costs; perform development across several time periods and a genuinely untouched future/site holdout; and run engineer-reviewed shadow deployment before considering alerts or interventions. JMP/Minitab/Power BI execution is not claimed.
