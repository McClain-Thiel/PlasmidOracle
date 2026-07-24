# ADR-001: Isolate Bioinformatics Providers

## Status

Accepted

## Context

Plasmid Oracle combines one stable Python API with tools that have different
installation methods, database layouts, output formats, licenses, and failure
behavior. Some are Python libraries while others are CLI-only applications.

Allowing those details into the domain model would make tool upgrades risky and
would make unit tests require large databases.

## Decision

Every bioinformatics tool is represented by a provider that returns
`ProviderResult`.

- In-process packages remain behind the same provider protocol as CLI tools.
- CLI tools run only through `SubprocessRunner`.
- Upstream output is parsed by pure normalization functions.
- Provider tests use recorded outputs and injected runners.
- Real database-backed tests are a separate integration layer.
- Models never launch tools or mutate themselves.

## Alternatives Considered

- Call each tool directly from `annotate()`: less initial code, but no common
  timeout, diagnostics, manifest, or test seam.
- Use Nextflow as the library runtime: useful for batch deployment, but too much
  operational machinery for a Python call over one plasmid.
- Reimplement upstream algorithms: removes process dependencies but creates an
  unsustainable scientific validation burden.

## Consequences

- Tool upgrades normally affect one adapter and parser.
- Unit tests remain fast and offline.
- Provider completeness is visible in the analysis manifest.
- Each new provider must implement provenance and normalization work.
- Nextflow or another workflow engine can wrap the CLI later without changing
  domain types.

## Revisit When

- A provider exposes a stable service API that should replace local execution.
- Batch scheduling becomes a primary use case.
