# Reference Plasmid Fixtures

These fixtures are versioned records fetched from NCBI Nucleotide on
2026-07-24:

| Plasmid | Accession | Length | Why it is useful |
| --- | --- | ---: | --- |
| pBR322 | J01749.1 | 4,361 bp | TetR, AmpR, ROP, and a ColE1-family origin |
| pUC19 | M77789.2 | 2,686 bp | AmpR, lacZ alpha, MCS, and a high-copy pMB1 derivative |
| pACYC184 | X06403.1 | 4,245 bp | TetR, CmR, and a p15A origin |

The FASTA header retains the versioned NCBI accession. `manifest.json` locks
the raw fixture checksum, normalized DNA checksum, circular canonical checksum,
length, topology, and source URL.

The pBR322 ground-truth coordinates come from the NCBI GenBank feature table
and are converted from one-based inclusive coordinates to Plasmid Oracle's
zero-based half-open convention.

Fixtures must not be updated in place. Add a new accession version and review
the biological expectations when an upstream record changes.
