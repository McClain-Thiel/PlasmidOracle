# ADR-003: Separate Raw Evidence from Resolved Annotations

Status: accepted

## Context

Independent bioinformatics providers often describe the same locus with
different names, coordinates, strands, or levels of specificity. Returning
only the provider calls makes common questions cumbersome. Choosing one call
and discarding the others makes the result difficult to audit.

Provider execution is also expensive enough that exact repeated analyses
should not rerun unchanged tools and databases.

## Decision

`Plasmid.evidence` stores every normalized provider `Annotation`.
`Plasmid.annotations` stores deterministic `ResolvedAnnotation` objects that
reference their supporting evidence.

The resolver:

- groups compatible calls using feature families and reciprocal overlap;
- treats contained partial origin fragments as support for a complete call;
- prefers specific names over anonymous ORFs;
- chooses coordinates and strands by deterministic support rules;
- retains alternative names as aliases;
- emits typed conflicts instead of hiding disagreements.

Provider caching is opt-in. Cache keys include the exact sequence checksum,
topology, provider implementation version, tool version, database versions,
and provider parameters. Entries are JSON, validated on read, and written
atomically. Invalid entries are ignored and reported in the analysis manifest.

Provider concurrency is bounded by both `provider_workers` and the caller's
total `threads` budget. Final evidence and manifests retain declared provider
order regardless of completion order.

## Consequences

- Normal Python use sees one biological feature per resolved locus.
- Every conclusion remains traceable to raw calls and database versions.
- Resolution rules become a versioned scientific contract requiring benchmark
  and metamorphic tests.
- Schema version 2 stores evidence and resolved annotations separately.
- Cache hits remain observable through `ProviderStatus.CACHED`.
- Cached results are not reused across database or tool upgrades.
