# Engineering workbench: reference review and final design

The original card dashboard was replaced with task-oriented analysis surfaces. References were used to understand interaction patterns; no source code, branding, screenshots, or proprietary assets were copied.

| Reference | Pattern reviewed | FabWatch implementation |
|---|---|---|
| [Seeq Workbench data views](https://support.seeq.com/latest/cloud/data-views) | Signal search, trending, and multiple analysis views | Searchable signal picker; standardized overlays; raw and EWMA views; movable record windows |
| [Cognite Industrial Canvas](https://www.cognite.com/en/industrial-canvas) | Keeping industrial evidence and analysis in context | Linked trace, fingerprint, selected entity, review ownership, and event history |
| [Siemens Insights Hub OEE analysis overview](https://docs.industrial-operations-x.siemens.cloud/r/en-us/insights-hub-oee/data-visualization/analysis-overview/analysis-overview?contentId=gRlerQ3ETzNGfFR53PoC0w) | Time-based operational inspection and drill-down | Source test-time context, selectable records, explicit outcomes and pending labels; no fabricated OEE |
| [Tulip operations management dashboard](https://support.tulip.co/docs/operations-management-dashboard-1) | Operational follow-up and action ownership | Filtered review board, owner/status/notes, manual investigation creation, and audit events |

## Practical interactions

1. **Inspect a process change:** choose a signal, select raw or EWMA mode, move the analysis window, click a record, and inspect its measured value against training references.
2. **Compare records:** pin two or three entities, compare the same sensor evidence, and keep revealed outcomes distinct from model scores.
3. **Prioritize an investigation:** filter input holds versus process excursions, select an unresolved case, assign an owner, and record a verification step.
4. **Investigate missed failures:** filter revealed failed records and explicitly create an engineering review. This is retrospective human investigation, not a newly successful model alert.
5. **Repeat a scenario:** start a new replay warehouse, choose records per tick, pause/resume, and restore the prior warehouse without deleting its evidence.
6. **Hand off data:** export the current window/filter with selected signals, or use the standardized SQL KPI and audit exports.

## Visual and data conventions

The layout uses a compact horizontal toolbar, a signal browser, linked plots, a fingerprint grid, a sortable ledger, and an evidence inspector. Cool neutral surfaces distinguish working areas; blue/teal/orange identify trace channels. Orange marks revealed failures in the risk view. Gray fingerprint cells indicate missing measurements. Status labels always accompany status colors.

On narrow screens, the inspector becomes a closable evidence drawer. The source timestamp, API freshness, paused/running/complete state, and synthetic outcome delay are separately labelled. Replay completion disables further stepping until a new session is created or a prior checkpoint is restored. The fixed cost-based model policy is never changed by UI exploration.

The original model, chronological splits, error counts, and exploratory challenger status are unchanged by this interface redesign. No physical sensor names, causal root causes, production interventions, process capability indices, or yield improvements are invented.
