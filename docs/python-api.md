# Python API

The public package is imported as:

```python
import plasmid_oracle as po
```

The distribution name is `plasmid-oracle`; Python module names cannot contain
hyphens.

## Construct a plasmid

```python
po.plasmid(
    *,
    seq: str,
    topology: str = "circular",
    source_metadata: Mapping[str, object] | None = None,
) -> po.Plasmid
```

Normalizes a sequence and returns an immutable `Plasmid` without running
providers.

## Annotate

```python
po.annotate(
    *,
    seq: str,
    topology: str = "circular",
    mode: str = "minimal",
    providers: Iterable[AnnotationProvider] | None = None,
    source_metadata: Mapping[str, object] | None = None,
    strict: bool = True,
    threads: int = 1,
    timeout_seconds: float = 600.0,
    cache: bool = False,
    cache_dir: Path | None = None,
    provider_workers: int = 1,
) -> po.Plasmid
```

Runs the requested provider pipeline and resolves its evidence. Supplying
`providers` replaces the providers selected by `mode`, which is useful for
testing and custom integrations.

`po.annotate_async(...)` accepts the same arguments and returns an awaitable
`Plasmid`.

## Batch annotation

```python
po.annotate_jsonl(
    *,
    input_path: Path,
    output_path: Path,
    mode: str = "minimal",
    threads: int = 1,
    record_workers: int = 1,
    provider_workers: int = 1,
    cache: bool = True,
    resume: bool = True,
) -> po.BatchSummary
```

Each input line is a JSON object with `sequence` or `seq`, optional `id`,
optional `topology`, and optional `source_metadata`. The output is JSONL: one
terminal record per input and a final manifest line. Batch records include
input checksums, result checksums, completed/partial/failed status, and the
serialized plasmid when annotation succeeds.

When `resume=True`, prior terminal records are reused only if their
`record_id`, `input_sha256`, status, and `output_sha256` still validate against
the current input. Stale records are pruned before processing and reported in
the manifest parameters; malformed existing JSONL stops the resume.

## Inspect a result

A `Plasmid` contains:

| Attribute | Meaning |
| --- | --- |
| `sequence` | Normalized DNA, topology, checksums, and sequence warnings |
| `evidence` | Every provider call before resolution |
| `annotations` | Deterministically resolved biological features |
| `characterization` | Replicon, mobility, host-range, and similarity calls |
| `source_metadata` | Caller-provided source identifiers and context |
| `analysis` | Pipeline version, provider runs, parameters, and quality flags |

Convenience methods and properties:

```python
plasmid.features(feature_type="CDS", status="supported")
plasmid.find("tet")
plasmid.amr_genes
plasmid.conflicts
plasmid.provider_status
plasmid.analysis_complete
plasmid.summary()
plasmid.to_dataframe()
```

## Evidence and resolution

`Annotation` represents one normalized provider call. It includes:

- a provider-scoped annotation ID, stable `evidence_id`, feature type, name,
  and location;
- provider, tool, and database provenance;
- normalized biological concepts and sequence variants when available;
- identity, coverage, score, and e-value when reported;
- nucleotide and protein sequences when available;
- complete, partial, interrupted, ambiguous, or unknown integrity.

`ResolvedAnnotation` groups compatible evidence and exposes:

- a selected display name and aliases;
- canonical identifiers;
- supporting providers;
- `supported`, `single_source`, or `conflicted` resolution status;
- typed coordinate, strand, and integrity conflicts.

Raw evidence is retained even when a more specific resolved feature is chosen
for presentation.

Provider runs declare `ProviderCapability` entries. Evaluation only treats a
no-hit result as absence when a completed or cached provider has a matching
capability whose `absence_semantics` is `bounded_catalog` or `exhaustive`.
`positive_only` capabilities can support positive findings but leave no-hit
questions as `unknown`.

## Evaluate

```python
po.evaluate(plasmid) -> po.EvaluationReport
po.evaluate(plasmid, preset="lab_vector") -> po.EvaluationReport
po.check(plasmid, "has_replication_component") -> po.EvaluationFinding
po.requirement_schema() -> dict[str, object]
po.requirements_from_dict(payload) -> po.RequirementSet
```

Evaluation is separate from annotation. The default evaluates loose plasmid
validity. Named presets evaluate utility for a use case. Requirement sets
evaluate fidelity to parsed user intent.

The natural-language layer should request structured output using
`po.requirement_schema()`, validate the returned payload with
`po.requirements_from_dict(...)`, then pass the resulting requirement set to
`po.evaluate(...)`.

## Serialization

```python
po.to_dict(plasmid) -> dict[str, object]
po.to_json(plasmid, *, indent: int = 2) -> str
po.from_dict(payload) -> po.Plasmid
po.from_json(payload) -> po.Plasmid
```

Use these functions instead of serializing dataclasses directly. They own the
schema version and migration behavior.

Schema 3 serializes stable evidence IDs, normalized concepts, sequence
variants, provider capabilities, database manifest digests, and cache identity
when present. Schema 1 and 2 payloads still load through compatibility
migrations, including legacy annotation and conflict references that predate
stable `evidence_id` fields.

## Provider readiness and setup

```python
report = po.doctor(mode="standard", threads=4)
result = po.setup("amrfinderplus")
```

See [Providers and Databases](providers.md) for setup details and environment
overrides.

## Errors

All package-specific exceptions derive from `po.PlasmidOracleError`:

| Exception | Meaning |
| --- | --- |
| `InvalidSequenceError` | DNA normalization failed |
| `InvalidLocationError` | Coordinates are invalid for the sequence |
| `InvalidProviderResultError` | Provider output violates the normalized contract |
| `ProviderUnavailableError` | Required software or database is unavailable |
| `ProviderExecutionError` | A provider failed or timed out |
| `InvalidSerializedPlasmidError` | Serialized data is malformed or unsupported |
