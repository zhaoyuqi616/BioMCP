"""Interactive figures use only the displayed snapshot."""

import plotly.graph_objects as go


def figures(snapshot):
    records = snapshot.get("records", [])
    expression = sorted((r for r in records if r["kind"] == "tissue_rna"), key=lambda r: r["value"])
    total = len(expression)
    expression = expression[-15:]
    rna = go.Figure(
        go.Bar(
            x=[r["value"] for r in expression],
            y=[r["subject"] for r in expression],
            orientation="h",
        )
    )
    rna.update_layout(
        title=f"HPA tissue RNA · {len(expression)} of {total} measured tissues",
        xaxis_title="nTPM",
        yaxis={"automargin": True},
    )
    associations = [r for r in records if r["kind"] == "association"]
    categories = sorted({c["id"] for r in associations for c in r["categories"]})
    scores = [{c["id"]: c["score"] for c in r["categories"]} for r in associations]
    disease = go.Figure(
        go.Heatmap(
            x=categories,
            y=[r["subject"] for r in associations],
            z=[[row.get(c) for c in categories] for row in scores],
            zmin=0,
            zmax=1,
            hoverongaps=False,
        )
    )
    disease.update_layout(title="Direct associations by evidence category")
    drug = go.Figure()
    entries = [r for r in records if r["kind"] == "drug"]
    for state in sorted({r["fda"].get("status", "not_checked") for r in entries}):
        group = [r for r in entries if r["fda"].get("status", "not_checked") == state]
        drug.add_scatter(
            x=[r["value"] for r in group],
            y=[r["subject"] for r in group],
            mode="markers",
            name=state.replace("_", " ").capitalize(),
        )
    drug.update_layout(title="Drug candidates by clinical stage", xaxis_title="Reported stage")
    for plot, values in [(rna, expression), (disease, associations), (drug, entries)]:
        if not values:
            message = (
                "No numeric tissue RNA measurements returned by HPA."
                if plot is rna
                else "No records match the selected evidence and filters. Check Sources for retrieval status."
            )
            plot.update_xaxes(visible=False)
            plot.update_yaxes(visible=False)
            plot.update_layout(height=175)
            plot.add_annotation(
                text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False
            )
    return rna, disease, drug
