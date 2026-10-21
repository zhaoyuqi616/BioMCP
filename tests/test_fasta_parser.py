from ensembl_uniprot_mcp.server import _parse_fasta_sequence


def test_parse_fasta_sequence():
    header, seq = _parse_fasta_sequence(
        ">sp|P04637|P53_HUMAN Cellular tumor antigen p53\nMEEPQSDPSV\nEPPLSQETF\n"
    )
    assert header.startswith(">sp|P04637")
    assert seq == "MEEPQSDPSVEPPLSQETF"
