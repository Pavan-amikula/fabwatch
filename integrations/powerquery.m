// Example Power Query; not executed in Power BI Desktop.
let
    Source = Csv.Document(
        Web.Contents("http://127.0.0.1:8768/api/export/kpis"),
        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"day", type date}, {"scored", Int64.Type}, {"outcomes_known", Int64.Type},
        {"observed_pass_yield", type number}, {"mean_risk", type number},
        {"review_count", Int64.Type}, {"abstentions", Int64.Type}, {"missing_fraction", type number}
    }, "en-US")
in
    Typed
