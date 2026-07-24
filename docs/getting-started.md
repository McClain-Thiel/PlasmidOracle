# Getting Started

## Install

Plasmid Oracle requires Python 3.11 or newer.

=== "PyPI"

    ```bash
    pip install plasmid-oracle
    ```

=== "Current main branch"

    ```bash
    pip install "plasmid-oracle @ git+https://github.com/McClain-Thiel/PlasmidOracle.git"
    ```

Install the optional pLannotate Python integration with:

```bash
pip install "plasmid-oracle[plannotate]"
```

The core installation includes Pyrodigal. Standard analysis additionally needs
external executables and databases; see
[Providers and Databases](providers.md).

## Runnable walkthrough

From a source checkout, the whole walkthrough below can be run without external
databases:

```bash
uv run python examples/getting_started.py
```

Expected output:

```text
Normalize
  length: 4361
  checksum: 536042a7485bdabdf49c4d21a306213a098d77d19bdba57a1c6adc76ce2b8372

Minimal annotation
  resolved annotations: 5
  raw evidence calls: 5

Query
  CDS features: 5
  blaTEM hits in minimal mode: 0
  AMR genes in minimal mode: 0
  predicted CDS [85, 1276) + via pyrodigal
  predicted CDS [1331, 1460) - via pyrodigal
  predicted CDS [1514, 1883) - via pyrodigal

Evaluation
  validity: pass
    sequence_evaluable: pass
    plasmid_evidence: pass
    red_flags: pass
    evidence_complete_enough: pass
  lab_vector utility: unknown
    sequence_evaluable: pass
    has_replication_component: unknown
    has_selection_component: unknown
    red_flags: pass
    evidence_complete_enough: pass

Save and restore
  round trip preserved: True
```

The `lab_vector` result is `unknown` because minimal mode only runs Pyrodigal.
It can predict coding sequences, but it does not test replication origins or
selection markers.

## Normalize a sequence

Create the canonical object without running any bioinformatics:

```python
from pathlib import Path

import plasmid_oracle as po

example = Path("examples/results/pBR322_J01749.1.standard.json")
sequence = po.from_json(example.read_text(encoding="utf-8")).sequence.bases

plasmid = po.plasmid(
    seq=sequence,
    topology="circular",
    source_metadata={"id": "pBR322"},
)

print(f"length: {plasmid.sequence.length}")
print(f"checksum: {plasmid.sequence.checksum}")
```

Output:

```text
length: 4361
checksum: 536042a7485bdabdf49c4d21a306213a098d77d19bdba57a1c6adc76ce2b8372
```

Input is normalized as strict IUPAC DNA. Invalid symbols and invalid locations
raise typed `PlasmidOracleError` subclasses.

## Run a minimal annotation

Minimal mode only runs Pyrodigal and needs no external database:

```python
result = po.annotate(
    seq=sequence,
    topology="circular",
    mode="minimal",
    source_metadata={"id": "pBR322"},
)

print(f"resolved annotations: {len(result.annotations)}")
print(f"raw evidence calls: {len(result.evidence)}")
```

Output:

```text
resolved annotations: 5
raw evidence calls: 5
```

The returned `Plasmid` is immutable. Running more analysis returns another
object rather than changing the existing result.

## Query results

```python
coding_sequences = result.features(feature_type="CDS")
ampicillin_hits = result.find("blaTEM")
resistance_genes = result.amr_genes
conflicts = result.conflicts

print(f"CDS features: {len(coding_sequences)}")
print(f"blaTEM hits in minimal mode: {len(ampicillin_hits)}")
print(f"AMR genes in minimal mode: {len(resistance_genes)}")

for feature in coding_sequences[:3]:
    print(
        f"{feature.name} "
        f"[{feature.location.start}, {feature.location.end}) "
        f"{feature.location.strand.value} via {', '.join(feature.providers)}"
    )
```

Output:

```text
CDS features: 5
blaTEM hits in minimal mode: 0
AMR genes in minimal mode: 0
predicted CDS [85, 1276) + via pyrodigal
predicted CDS [1331, 1460) - via pyrodigal
predicted CDS [1514, 1883) - via pyrodigal
```

Minimal mode is useful for an instant smoke test, but it does not run
pLannotate, AMRFinderPlus, or MOB-suite. That is why the ampicillin and AMR
queries return zero here.

For tabular analysis:

```python
frame = result.to_dataframe()  # requires pandas
```

## Evaluate a plasmid

Evaluation is designed to be easy first and configurable later. The default is
loose plasmid validity, not a strict lab-vector definition:

```python
validity = po.evaluate(result)
print(f"validity: {validity.status.value}")
```

Output:

```text
validity: pass
```

Use a preset when you have a use case:

```python
lab_vector = po.evaluate(result, preset="lab_vector")

for finding in lab_vector.findings:
    print(f"{finding.check}: {finding.status.value}")
```

Output:

```text
sequence_evaluable: pass
has_replication_component: unknown
has_selection_component: unknown
red_flags: pass
evidence_complete_enough: pass
```

When you need stricter evidence thresholds, pass a config:

```python
strict = po.evaluate(
    result,
    preset="lab_vector",
    config=po.EvaluationConfig(min_identity=0.95, min_coverage=0.95),
)
```

Natural-language prompts should be parsed into requirements first. The
requirements are independent from the plasmid, so validity and prompt fidelity
can be reported separately.

## Run standard analysis

After provider setup:

```python
result = po.annotate(
    seq=sequence,
    mode="standard",
    threads=4,
    provider_workers=2,
    cache=True,
)
```

`threads` is the total CPU budget. `provider_workers` limits concurrent
providers within that budget.

Strict mode is the default: a requested provider failure raises
`ProviderExecutionError`. Tolerant mode preserves completed evidence and
records every failure in the manifest:

```python
partial = po.annotate(
    seq=sequence,
    mode="standard",
    strict=False,
)

print(partial.provider_status)
print(partial.analysis_complete)
```

## Use async

Async applications can run the same bounded pipeline without blocking their
event loop:

```python
result = await po.annotate_async(
    seq=sequence,
    mode="standard",
    threads=4,
    provider_workers=2,
    cache=True,
)
```

## Save and restore

```python
payload = po.to_dict(result)
rendered = po.to_json(result)

restored = po.from_json(rendered)
print(restored == result)
```

Output:

```text
True
```

The JSON schema is versioned. Older supported schemas are migrated on read;
unknown or malformed schemas fail explicitly.
