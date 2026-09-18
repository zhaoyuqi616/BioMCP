from ensembl_uniprot_mcp.models import SequenceRecord


def test_sequence_record_length():
    rec = SequenceRecord(
        source="UniProt",
        query="P04637",
        id="P04637",
        molecule="protein",
        sequence="MEEPQ",
        length=5,
    )
    assert rec.length == len(rec.sequence)
