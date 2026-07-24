# Command Line

The command-line interface is intended for single-plasmid runs, readiness
checks, automation, and database setup. Python remains the primary API for
larger applications.

## Annotate a FASTA file

```bash
plasmid-oracle annotate \
  --fasta plasmid.fasta \
  --topology circular \
  --mode standard \
  --threads 4 \
  --provider-workers 2 \
  --cache \
  --output plasmid.json
```

FASTA input must contain exactly one record. A file output defaults to JSON;
terminal output defaults to a readable report.

## Annotate a raw sequence

```bash
plasmid-oracle annotate \
  --sequence ATGCGTACGT... \
  --mode minimal
```

Useful options:

| Option | Meaning |
| --- | --- |
| `--mode` | `minimal`, `fast`, `standard`, or `deep` |
| `--topology` | `circular` or `linear` |
| `--threads` | Total provider CPU budget |
| `--provider-workers` | Maximum concurrent providers |
| `--timeout` | Per-provider timeout in seconds |
| `--cache` | Enable content-addressed provider caching |
| `--cache-dir` | Override the cache directory |
| `--tolerant` | Preserve partial results instead of failing |
| `--format` | Force `text` or `json` output |

## Annotate a JSONL batch

```bash
plasmid-oracle batch \
  --input candidates.jsonl \
  --output candidates.results.jsonl \
  --mode standard \
  --threads 16 \
  --record-workers 4 \
  --provider-workers 2
```

Each input line must be a JSON object with `sequence` or `seq`. Optional fields
are `id`, `topology`, and `source_metadata`. Batch mode writes one terminal
record per input and a final `manifest` record. Existing completed, partial,
or failed records are preserved on resume when their input checksum still
matches.

Batch-specific options:

| Option | Meaning |
| --- | --- |
| `--record-workers` | Maximum concurrent input records within the total thread budget |
| `--provider-workers` | Maximum concurrent providers per active record |
| `--no-cache` | Disable provider result caching; batch caching is enabled by default |
| `--tolerant` | Write partial records when providers fail |
| `--no-resume` | Rewrite the output file instead of reusing terminal records |

## Check providers

```bash
plasmid-oracle doctor --mode standard
```

The command exits successfully only when every provider required by the mode is
ready. Add `--json` for machine-readable diagnostics.

## Set up databases

```bash
plasmid-oracle setup plannotate
plasmid-oracle setup amrfinderplus
plasmid-oracle setup mob-suite --mob-database /data/mob-suite
```

Add `--json` for structured output or `--force` to request a provider-supported
refresh.

## Exit behavior

| Exit code | Meaning |
| --- | --- |
| `0` | Operation completed successfully |
| `1` | `doctor` found an unavailable provider or a batch wrote failed records |
| `2` | Input, setup, or provider execution failed |
