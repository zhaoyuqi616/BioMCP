import asyncio

from ensembl_uniprot_mcp.clients import EnsemblClient, UniProtClient


async def main():
    ens = EnsemblClient()
    uni = UniProtClient()
    try:
        print("Resolving human BRCA2...")
        hits = await ens.xrefs_symbol("homo_sapiens", "BRCA2")
        print(hits[:2])

        print("Retrieving UniProt TP53 P04637 FASTA...")
        fasta = await uni.entry_fasta("P04637")
        print("\n".join(fasta.splitlines()[:3]))
    finally:
        await ens.close()
        await uni.close()


if __name__ == "__main__":
    asyncio.run(main())
