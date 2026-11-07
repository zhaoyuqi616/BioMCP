"""Conservative claim semantics without cross-source confidence inference."""

SEMANTICS = {
    "association": ("Disease association", "Association does not establish causality."),
    "curation": (
        "Curated gene–disease validity",
        "Interpret the source classification and inheritance together.",
    ),
    "drug": (
        "Drug–target candidate",
        "Clinical stage is drug-level evidence, not approval for this gene or indication.",
    ),
    "regulatory": (
        "Ingredient approval lookup",
        "An ingredient approval record does not verify a target-specific indication or current marketing status.",
    ),
    "tissue_rna": (
        "RNA measurement",
        "RNA abundance does not establish protein abundance. Only returned tissues are represented.",
    ),
    "expression_annotation": (
        "Expression annotation",
        "Source annotation; missing values are not evidence of absent expression.",
    ),
    "publication": ("Linked literature", "A linked publication is not a validated causal claim."),
}


def annotate(records, identity):
    for record in records:
        label, limitation = SEMANTICS.get(
            record["kind"], ("Reference annotation", "Interpret within the source dataset.")
        )
        record["evidence_type"] = label
        record["interpretation_limit"] = limitation
        record["context"] = {
            "species": "Homo sapiens",
            "gene_symbol": identity.get("symbol"),
            "ensembl_id": identity.get("ensembl_id"),
            "dataset_release": (
                record.get("value", {}).get("dataset")
                if isinstance(record.get("value"), dict)
                else None
            )
            or "Not provided by adapter",
        }
        record["provenance"] = {
            "source": record["source"],
            "record_url": record.get("url"),
            "retrieved_at": record.get("retrieved_at"),
            "retrieval_time_status": "reported" if record.get("retrieved_at") else "not_reported",
        }
        if record["kind"] == "drug":
            record["relationships"] = {
                "target_association": "Reported candidate for queried target",
                "mechanism_of_action": "Not retrieved",
                "directness": "Not established by this adapter",
                "drug_indication": "Not retrieved",
                "target_specific_approval": "Not verified",
                "indication_specific_approval": "Not verified",
            }
    return records


def select_records(snapshot, sources=None, question="All evidence", search=""):
    kinds = {
        "Where is it expressed?": {"tissue_rna", "expression_annotation"},
        "Which diseases are associated?": {"association", "curation"},
        "Are there drug candidates?": {"drug", "regulatory"},
    }.get(question)
    return [
        r
        for r in snapshot.get("records", [])
        if (not sources or r["source"] in sources)
        and (not kinds or r["kind"] in kinds)
        and (search or "").casefold() in str(r.get("subject", "")).casefold()
    ]
