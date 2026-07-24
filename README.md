# Plasmid Oracle

[![CI](https://github.com/McClain-Thiel/PlasmidOracle/actions/workflows/ci.yml/badge.svg)](https://github.com/McClain-Thiel/PlasmidOracle/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-00796b.svg)](https://mcclain-thiel.github.io/PlasmidOracle/)
[![PyPI](https://img.shields.io/pypi/v/plasmid-oracle.svg)](https://pypi.org/project/plasmid-oracle/)
[![Python](https://img.shields.io/pypi/pyversions/plasmid-oracle.svg)](https://pypi.org/project/plasmid-oracle/)

Plasmid Oracle is an evidence-first Python library that turns plasmid DNA into
a normalized, reproducible description of the sequence, its annotations, and
its plasmid-level characteristics.

The package keeps three concerns separate:

1. Providers gather biological evidence.
2. A canonical immutable `Plasmid` normalizes that evidence.
3. Evaluators decide whether a plasmid is valid, useful for a preset, or
   faithful to parsed requirements.

The current alpha implements the annotation and evidence-resolution core plus a
first deterministic evaluation layer. It does not yet parse natural language by
itself; natural-language systems should produce the supported requirement JSON
schema and let Plasmid Oracle perform the biological checks.

## What Works

- strict IUPAC DNA normalization and exact sequence checksums;
- rotation and reverse-complement invariant identity for circular plasmids;
- zero-based, half-open locations with explicit origin-crossing spans;
- Pyrodigal ORF prediction through its in-process Python API;
- pLannotate engineered-part annotation through its DataFrame API;
- AMRFinderPlus AMR, stress, virulence, and point-mutation calls;
- MOB-suite replicon, relaxase, MPF, oriT, mobility, host-range, cluster, and
  nearest-neighbor characterization;
- provider capability declarations with conservative absence semantics;
- deterministic cross-provider evidence resolution with explicit conflicts;
- stable evidence IDs for annotations, characterization calls, and quality
  flags;
- normalized biological concept and sequence-variant fields for downstream
  evaluators;
- readable Python summaries, feature queries, and optional DataFrame export;
- complete tool/database provenance, database manifest digests, and partial-run
  manifests;
- schema-versioned JSON round trips with schema-1 and schema-2 migration;
- content-addressed provider caching keyed by sequence, parameters, tools, and
  databases;
- bounded provider concurrency and an asynchronous Python entry point;
- resumable JSONL batch execution with durable per-record output;
- readable CLI reports, machine-readable JSON, and provider diagnostics;
- explicit database setup with no annotation-time downloads;
- deterministic plasmid validity, preset utility, and parsed-requirement
  fidelity reports.

Whole-plasmid comparison beyond MOB-suite's nearest-neighbor result, evidence
calibration against broader benchmark sets, expression-cassette inference, and
natural-language parsing remain roadmap items.

## Install

The core package requires Python 3.11 or newer. It includes Pyrodigal and can
run `minimal` mode without external databases:

```bash
pip install plasmid-oracle
```

pLannotate is kept in an optional extra because it brings a larger Python
dependency set:

```bash
pip install "plasmid-oracle[plannotate]"
```

Standard analysis also requires these external executables:

| Provider | Required software | Database |
| --- | --- | --- |
| pLannotate | `blastn`, `diamond`, `cmscan`, `rg` | pLannotate databases |
| AMRFinderPlus | `amrfinder` | AMRFinderPlus database |
| MOB-suite | `mob_typer`, `mob_init` | MOB-suite database |

Install those tools with their supported system, Conda, or container
distribution. Plasmid Oracle deliberately does not force their incompatible
runtime stacks into the core Python environment.

## Quick Start

The distribution name contains a hyphen; the Python import uses an underscore:

```python
import plasmid_oracle as po

plasmid = po.annotate(
    seq="ATGCGTACGT...",
    topology="circular",
    mode="standard",
    threads=4,
    provider_workers=4,
    cache=True,
)

print(plasmid)
print(plasmid.amr_genes)
print(plasmid.find("blaTEM"))
print(plasmid.conflicts)
```

`plasmid.annotations` contains resolved biological features.
`plasmid.evidence` contains every normalized provider call supporting those
features. Resolution never discards the raw calls.

Create the canonical object without running bioinformatics:

```python
plasmid = po.plasmid(seq="ATGCGTACGT...", topology="circular")
```

Serialize a result using the versioned JSON representation:

```python
payload = po.to_dict(plasmid)
rendered = po.to_json(plasmid)
restored = po.from_json(rendered)
```

Models are immutable. Additional analysis returns a new `Plasmid`; model
construction never starts a subprocess.

Use the query and presentation helpers without parsing provider-specific data:

```python
amr = plasmid.amr_genes
origins = plasmid.features(feature_type="rep_origin")
hits = plasmid.find("tet")
table = plasmid.to_dataframe()  # requires pandas
report = plasmid.summary()
```

Evaluate loose plasmid validity, named utility presets, or parsed requirements:

```python
validity = po.evaluate(plasmid)
lab_vector = po.evaluate(plasmid, preset="lab_vector")
schema = po.requirement_schema()
```

Evaluation never treats a failed or unavailable provider as biological absence.
Completed providers only support negative findings for concepts they explicitly
declare as `bounded_catalog` or `exhaustive`; other no-hit results remain
`unknown`.
Natural-language prompts should be converted into the generated requirement
schema before calling `evaluate()`.

## Analysis Modes

| Mode | Providers | Intended use |
| --- | --- | --- |
| `minimal` | Pyrodigal | ORF discovery only, with no database setup |
| `fast` | Pyrodigal | Compatibility alias for `minimal` |
| `standard` | Pyrodigal, pLannotate, AMRFinderPlus, MOB-suite | Full current characterization |
| `deep` | Same providers as `standard` | Reserved compatibility point for broader searches |

Requested providers are strict by default. A missing database, missing
executable, timeout, or malformed result raises `ProviderExecutionError`.
Tolerant mode returns all completed evidence and records failures explicitly:

```python
plasmid = po.annotate(
    seq="ATGCGTACGT...",
    mode="standard",
    strict=False,
    threads=4,
    timeout_seconds=900,
)
```

An unavailable provider is not interpreted as biological absence.

## Cache, Concurrency, and Async

Caching is opt-in. A result is reused only when the exact sequence, topology,
provider implementation, tool version, database versions, and parameters all
match:

```python
plasmid = po.annotate(
    seq=sequence,
    mode="standard",
    cache=True,
)
```

`threads` is a total CPU budget. `provider_workers` controls how many providers
may run simultaneously. For example, two workers within a four-thread budget
receive two threads each:

```python
plasmid = po.annotate(
    seq=sequence,
    mode="standard",
    threads=4,
    provider_workers=2,
)
```

Async callers use the same bounded pipeline without blocking the event loop:

```python
plasmid = await po.annotate_async(
    seq=sequence,
    mode="standard",
    threads=4,
    provider_workers=4,
    cache=True,
)
```

## Database Setup

Large scientific databases are not stored in the wheel and are never
downloaded by `annotate()`. Install them explicitly after their associated
software is available:

```bash
plasmid-oracle setup plannotate
plasmid-oracle setup amrfinderplus
plasmid-oracle setup mob-suite --mob-database ~/.local/share/mob-suite
```

The same operations are exposed in Python:

```python
from pathlib import Path

import plasmid_oracle as po

po.setup("plannotate")
po.setup("amrfinderplus")
po.setup("mob_suite", mob_database_dir=Path("~/.local/share/mob-suite"))
```

MOB-suite analysis requires the selected path to be configured:

```bash
export PLASMID_ORACLE_MOB_DATABASE="$HOME/.local/share/mob-suite"
```

Optional executable and database overrides are:

```text
PLASMID_ORACLE_AMRFINDER_EXECUTABLE
PLASMID_ORACLE_AMRFINDER_DATABASE
PLASMID_ORACLE_MOB_TYPER_EXECUTABLE
PLASMID_ORACLE_MOB_DATABASE
```

Check readiness before a long run:

```bash
plasmid-oracle doctor --mode standard
plasmid-oracle doctor --mode standard --json
```

## CLI

Annotate either a raw sequence or a one-record FASTA:

```bash
plasmid-oracle annotate \
  --fasta plasmid.fasta \
  --topology circular \
  --mode standard \
  --threads 4 \
  --provider-workers 4 \
  --cache \
  --output plasmid.json
```

Terminal output is a readable report by default. Use `--format json` for JSON
on stdout. File output defaults to JSON. Use `--tolerant` to return a partial
result; the default is strict.

Run many records from JSONL with resumable, manifest-last output:

```bash
plasmid-oracle batch \
  --input candidates.jsonl \
  --output candidates.results.jsonl \
  --mode standard \
  --threads 16 \
  --record-workers 4 \
  --provider-workers 2
```

Each input line is a JSON object with `sequence` or `seq`, optional `id`, and
optional `topology`. Batch mode writes one terminal record per plasmid and a
final manifest line with input, output, and record checksums.
On resume, terminal records are reused only when the current input checksum and
stored output checksum still validate. Stale records are dropped and malformed
existing JSONL fails fast.

## Canonical Result

Every raw evidence call records:

- a stable `evidence_id`;
- feature type, name, identifiers, integrity, sequence, and qualifiers;
- normalized biological concepts and sequence variants when available;
- zero-based half-open location, strand, and circular spans;
- identity, coverage, score, and e-value when available;
- provider, provider version, tool version, database, and database version.

Resolved annotations group compatible evidence, retain aliases, and report
support as `supported`, `single_source`, or `conflicted`. Typed conflict records
currently cover strand, material coordinate, and integrity disagreements.

Plasmid-level characterization records replicons, relaxases, MPF types, oriT
sites, mobility, host range, similarity hits, and quality flags. The analysis
manifest records each requested provider as completed, failed, skipped,
unavailable, or cached, including declared capabilities and database manifest
digests.

See [the architecture guide](docs/design.md) for the detailed contracts and
tradeoffs. The
[hosted documentation](https://mcclain-thiel.github.io/PlasmidOracle/)
provides the user guide and API overview. The
[third-party inventory](docs/third-party.md) records tool and database license
boundaries. Release mechanics are documented in
[the release guide](docs/releasing.md).

## Development

The repository uses a `src/` layout, strict type checking, and test-first
provider adapters with recorded outputs:

```bash
uv sync --dev
uv run pytest --cov=plasmid_oracle --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

Unit tests do not download databases. Real database-backed benchmark tests will
only run when explicitly enabled:

```bash
PLASMID_ORACLE_RUN_INTEGRATION=1 uv run pytest tests/integration
```

## License

Plasmid Oracle is licensed under the
[GNU General Public License v3.0](LICENSE). Its separately distributed
dependencies and external databases retain their own licenses.
