# ADR 004: Evidence Identity and Absence Semantics

Status: accepted

## Context

Plasmid Oracle is used both for exploratory annotation and for reproducible
evaluation. A frozen benchmark or judge needs to cite exact evidence facts and
needs to distinguish "a provider found nothing" from "the biological concept is
absent".

The earlier model had stable IDs for annotations but not for plasmid-level
characterization calls such as replicons, host-range calls, mobility calls, or
quality flags. The evaluator also used provider completion as a proxy for some
absence-based claims. That was too strong for custom providers and for
positive-only tools.

## Decision

Every serialized evidence fact now carries a stable `evidence_id`. Annotation
objects retain their result-local `annotation_id` for compatibility, but
resolved annotations, conflicts, and evaluation findings cite stable evidence
IDs.

Provider runs serialize declared `ProviderCapability` entries:

```python
ProviderCapability(
    concept="antimicrobial_resistance_gene",
    absence_semantics="bounded_catalog",
    scope={"database": "AMRFinderPlus", "organism": None},
)
```

The supported absence semantics are:

- `positive_only`: hits are useful, but no-hit means unknown;
- `bounded_catalog`: no-hit can support absence within the declared database
  and scope;
- `exhaustive`: no-hit can support absence across a formal search space.

Evaluation may make a negative finding only from a completed or cached provider
run with a matching absence-capable capability. Completed custom providers no
longer justify absence unless they explicitly declare the concept and
semantics.

Provider runs also serialize database manifest identities. The current digest
is computed from the normalized database identity Plasmid Oracle can observe,
such as the database name and reported version. Providers that can expose a
full file manifest may supply stronger identities later without changing the
manifest shape.

## Consequences

- Requirement findings can cite annotations, replicons, host-range calls,
  similarity calls, and quality flags through a single `evidence_id` mechanism.
- Older schema 1 and schema 2 JSON still loads, but newly serialized results use
  schema 3.
- No-hit results become more conservative. Some findings that previously failed
  now remain `unknown` unless a provider declares bounded or exhaustive
  absence support.
- Database identity is stronger than a human-readable version string, though it
  still depends on what each upstream tool exposes.
- Custom provider authors must declare capabilities to participate in
  absence-based evaluation.
