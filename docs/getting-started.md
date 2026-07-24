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

## Normalize a sequence

Create the canonical object without running any bioinformatics:

```python
import plasmid_oracle as po

plasmid = po.plasmid(
    seq=sequence,
    topology="circular",
    source_metadata={"id": "pExample"},
)

print(plasmid.sequence.length)
print(plasmid.sequence.checksum)
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
    source_metadata={"id": "pExample"},
)

print(result)
print(f"{len(result.annotations)} resolved annotations")
print(f"{len(result.evidence)} raw evidence calls")
```

The returned `Plasmid` is immutable. Running more analysis returns another
object rather than changing the existing result.

## Query results

```python
coding_sequences = result.features(feature_type="CDS")
ampicillin_hits = result.find("blaTEM")
resistance_genes = result.amr_genes
conflicts = result.conflicts

for feature in coding_sequences:
    print(
        feature.name,
        feature.location.start,
        feature.location.end,
        feature.location.strand,
        feature.providers,
    )
```

For tabular analysis:

```python
frame = result.to_dataframe()  # requires pandas
```

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
assert restored == result
```

The JSON schema is versioned. Older supported schemas are migrated on read;
unknown or malformed schemas fail explicitly.
