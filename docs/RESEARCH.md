# Research and design decisions

## Primary sources

1. **McCann, M. and Johnston, A. (2008), SECOM.** UCI Machine Learning Repository. DOI: [10.24432/C54305](https://doi.org/10.24432/C54305). [Dataset page](https://archive.ics.uci.edu/dataset/179/secom). Real anonymized semiconductor process records with pass/fail outcomes, missing measurements, and test timestamps. The catalog describes 591 features; the downloaded numeric matrix contains **590 sensor columns**, verified by the loader. No recipe, equipment, wafer-map, lot genealogy, sensor units, or measurement-availability metadata is provided. Credit belongs to the dataset creators; CC BY 4.0 applies to the data.

2. **Salem, M., Taheri, S., and Yuan, J.-S. (2018).** [An Experimental Evaluation of Fault Diagnosis from Imbalanced and Incomplete Data for Smart Semiconductor Manufacturing](https://doi.org/10.3390/bdcc2040030). Investigates imputation, feature selection, and classifiers on SECOM. It motivates treating missingness, imbalance, and irrelevant measurements as first-class engineering concerns. FabWatch implements its own smaller declared model comparison; it does **not** reproduce the paper's complete experiment or claim comparable scores under a different split.

3. **Zhou et al. (2023).** [Quantile Online Learning for Semiconductor Failure Analysis](https://arxiv.org/abs/2303.07062). Discusses evolving distributions and single-pass defect detection. FabWatch adopts the operational concern of sequential arrival, but **does not implement the paper's quantile online learning algorithm**. Models remain frozen during replay to preserve evaluation provenance.

4. **NIST/SEMATECH e-Handbook, section 6.3.2.4.** [EWMA control charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm). Provides the EWMA recursion and time-dependent control-limit form. FabWatch uses lambda 0.2, initialization at the training mean, training standard deviation, and three-sigma reference bands. Missing observations are skipped without advancing the valid-reading count. Independence, normality, and process stability are not established: bands are exploratory, not a certified in-control process claim.

## Public project review

- [LDY5388/secom-process-dashboard](https://github.com/LDY5388/secom-process-dashboard): reviewed the public description for yield, process monitoring, and variable-importance workflow coverage.
- [gurdeep-munde/secom-yield-prediction](https://github.com/gurdeep-munde/secom-yield-prediction): reviewed the public overview of imbalanced classification and engineering interpretation.

These are contextual references. No source code, screenshots, assets, or numerical results were copied. The implementation, interface, and experiment here are independent. Published results from different preprocessing and split protocols are not a leaderboard for this project.

## Interface references

- [Tulip manufacturing dashboards](https://tulip.co/production-management/manufacturing-dashboards/): operational KPIs with drill-down to engineering context.
- [Tulip operations management dashboard documentation](https://support.tulip.co/docs/operations-management-dashboard-1): status visibility and ownership of follow-up work.
- [Tulip analytics](https://tulip.co/platform/analytics/): connecting process records with interpretable operational views.

Design choices: restrained paper/charcoal/brass palette; compact ledger; separate operations, investigation, data health, and model evidence views; labels that distinguish observed outcomes from risk estimates. No third-party UI template, remote font, chart CDN, or visual asset is required.

## Why no Cp/Cpk, OEE, or invented factory maps?

SECOM has no engineering specification limits, downtime, availability, ideal cycle time, machine IDs, or real lot membership. Computing process capability or OEE, assigning physical sensor names, or inventing wafer lots would imply facts absent from the source. Yield means the observed **entity pass fraction**, never die yield or verified first-pass yield. RCA support means a traceable hypothesis and evidence workflow, not proven causal diagnosis.
