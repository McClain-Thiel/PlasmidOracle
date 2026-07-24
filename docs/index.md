# Plasmid Oracle

Plasmid Oracle turns plasmid DNA into a normalized, evidence-backed description
of the sequence, its annotated features, and its plasmid-level
characteristics.

[Get started](getting-started.md){ .md-button .md-button--primary }
[View the Python API](python-api.md){ .md-button }

!!! warning "Alpha software"

    The current alpha implements annotation and evidence resolution. Natural
    language requirements and transcriptional-unit inference are roadmap work.

## Where to go

| Need | Start here |
| --- | --- |
| Run your first plasmid locally | [Getting Started](getting-started.md) |
| Annotate many records from files | [Command Line](cli.md#annotate-a-jsonl-batch) |
| Understand pass/fail/unknown results | [Evaluation](evaluation.md) |
| Use Plasmid Oracle from Python | [Python API](python-api.md) |
| Set up external tools and databases | [Providers and Databases](providers.md) |
| See the system boundaries | [Architecture](design.md) |

## What it does

Given a DNA sequence, Plasmid Oracle can:

- normalize IUPAC DNA and calculate exact and circular-plasmid identities;
- predict coding sequences with Pyrodigal;
- annotate known engineered parts with pLannotate;
- identify AMR, stress, and virulence determinants with AMRFinderPlus;
- characterize replicons and mobility with MOB-suite;
- preserve stable evidence IDs for annotations and plasmid-level facts;
- reconcile compatible calls without discarding the underlying evidence;
- evaluate plasmid validity and named-use-case utility from normalized evidence;
- run resumable JSONL batches with manifest-last output;
- serialize a complete, reproducible result to schema-versioned JSON.

## The core contract

Every analysis keeps three kinds of information separate:

1. **Evidence** records exactly what each provider reported.
2. **Resolved annotations** combine compatible calls and expose conflicts.
3. **The analysis manifest** records tools, databases, parameters, and provider
   outcomes, including capability declarations and database identity digests.

This means an unavailable database, failed provider, or positive-only search is
never silently interpreted as the absence of a biological feature.

## Smallest useful example

```python
import plasmid_oracle as po

result = po.annotate(
    seq=sequence,
    source_metadata={"id": "my-plasmid"},
    mode="minimal",
)

print(result.summary())
print(result.features(feature_type="CDS"))
print(result.analysis_complete)
```

`minimal` mode runs in-process with no external database setup. Move to
`standard` mode when the external providers are installed and
[`doctor`](providers.md#check-readiness) reports that they are ready.

## Current boundaries

Plasmid Oracle reports what the available evidence supports. It does not yet
claim that:

- a detected gene is expressed in a particular host;
- a promoter, CDS, and terminator form one transcriptional unit;
- a natural-language prompt has been faithfully parsed without validation;
- failure to detect a feature proves biological absence unless a completed
  provider explicitly supports absence for that concept.

Those conclusions belong to the evaluation layer built on the normalized result.
See [Evaluation](evaluation.md) for the validity, utility, and fidelity split.
