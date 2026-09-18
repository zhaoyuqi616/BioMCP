from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SequenceRecord(BaseModel):
    source: Literal["Ensembl", "UniProt"]
    query: str
    id: str | None = None
    species: str | None = None
    molecule: str | None = None
    sequence: str
    length: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeneLookupRecord(BaseModel):
    source: Literal["Ensembl"] = "Ensembl"
    query: str
    species: str
    ensembl_id: str
    object_type: str | None = None
    display_id: str | None = None
    description: str | None = None
    location: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProteinLookupRecord(BaseModel):
    source: Literal["UniProt"] = "UniProt"
    query: str
    accession: str
    id: str | None = None
    protein_name: str | None = None
    organism: str | None = None
    gene_names: list[str] = Field(default_factory=list)
    reviewed: bool | None = None
    sequence: str | None = None
    length: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
