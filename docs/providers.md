# Providers and Databases

## Analysis modes

| Mode | Providers | Intended use |
| --- | --- | --- |
| `minimal` | Pyrodigal | ORF discovery with no external database |
| `fast` | Pyrodigal | Compatibility alias for `minimal` |
| `standard` | Pyrodigal, pLannotate, AMRFinderPlus, MOB-suite | Current full characterization |
| `deep` | Same as `standard` | Reserved for broader future searches |

## Provider responsibilities

### Pyrodigal

Pyrodigal runs in the Python process and predicts coding sequences. Evidence
includes coordinates, strand, translated sequence, prediction confidence,
start type, and RBS motif where available. Its coding-sequence capability is
positive-only; no ORF call is not treated as biological absence.

### pLannotate

pLannotate searches known engineered parts and can identify features such as
promoters, CDSs, terminators, and origins. It requires its Python extra plus
`blastn`, `diamond`, `cmscan`, `rg`, and the pLannotate databases. Its
known-part capabilities are bounded to the installed pLannotate catalog.

### AMRFinderPlus

AMRFinderPlus contributes antimicrobial resistance, stress, virulence, and
point-mutation evidence. It runs as the external `amrfinder` executable with a
versioned NCBI database. AMR, stress, virulence, and point-mutation absence is
bounded to the AMRFinderPlus database version and scope recorded in the
manifest.

### MOB-suite

MOB-suite contributes replicon, relaxase, MPF, oriT, mobility, host-range,
cluster, and nearest-neighbor characterization. It runs `mob_typer` against a
configured MOB-suite database. Replicon, relaxase, oriT, and mobility absence
is bounded to the configured MOB-suite database; host-range and similarity
calls are currently positive-only.

## Install databases

Database installation is always explicit:

```bash
plasmid-oracle setup plannotate
plasmid-oracle setup amrfinderplus
plasmid-oracle setup mob-suite --mob-database "$HOME/.local/share/mob-suite"
```

The same operations are available in Python:

```python
from pathlib import Path

import plasmid_oracle as po

po.setup("plannotate")
po.setup("amrfinderplus")
po.setup(
    "mob_suite",
    mob_database_dir=Path.home() / ".local/share/mob-suite",
)
```

Importing the package and calling `annotate()` never initiate a database
download.

## Check readiness

```bash
plasmid-oracle doctor --mode standard
plasmid-oracle doctor --mode standard --json
```

Or in Python:

```python
report = po.doctor(mode="standard", threads=4)

for provider in report.providers:
    print(provider.name, provider.available, provider.issues)
```

Run `doctor` before a batch so missing tools and databases fail early.
Machine-readable diagnostics include each provider's declared capabilities and
database manifest digests.

## Environment overrides

```text
PLASMID_ORACLE_AMRFINDER_EXECUTABLE
PLASMID_ORACLE_AMRFINDER_DATABASE
PLASMID_ORACLE_MOB_TYPER_EXECUTABLE
PLASMID_ORACLE_MOB_DATABASE
```

MOB-suite analysis requires `PLASMID_ORACLE_MOB_DATABASE` unless its database
path is otherwise supplied by the provider configuration.

## Scientific interpretation

!!! important

    `unavailable`, `failed`, and `skipped` providers mean that the relevant
    biological question was not fully tested. They do not mean that a feature
    is absent. Completed positive-only providers also do not support absence
    claims.

Known-part annotation is also not equivalent to de novo regulatory prediction.
For example, a promoter not recognized by pLannotate may still be functional,
and a detected resistance gene is not by itself proof of expression in every
host.

Use strict mode for reproducible analyses that require every requested
provider. Use tolerant mode for exploratory work where a partial result is
useful, and inspect `plasmid.analysis` before drawing conclusions.
