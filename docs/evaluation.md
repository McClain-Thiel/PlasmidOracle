# Evaluation

Plasmid Oracle keeps interpretation separate from annotation. Annotation records
what the tools found. Evaluation asks what those findings mean for a question.

The guiding philosophy is:

1. Start with the smallest useful call.
2. Use named presets for common workflows.
3. Add configuration only when the defaults are too broad or too strict.
4. Keep natural-language parsing as a thin layer over deterministic checks.

The evaluation layer uses three related but independent concepts:

| Concept | Question | Default behavior |
| --- | --- | --- |
| Validity | Is this sequence coherent enough to interpret as plasmid DNA? | Loose and evidence-first. A circular sequence or plasmid evidence can be valid without looking like a lab backbone. |
| Utility | Does this plasmid satisfy a named use case? | Preset-driven. A lab vector preset may require selection, but a general plasmid preset does not. |
| Fidelity | Does this plasmid match a user prompt or parsed requirement set? | Requirement-driven. A plasmid can be valid while failing a prompt such as "amp resistant high-copy E. coli vector". |

Absence of an annotation is not automatically a biological absence. If the
responsible evidence source did not run, failed, or is not capable of ruling out
novel biology, evaluation returns `unknown` instead of pretending certainty.

## Validity

Baseline validity intentionally does not mean "standard cloning backbone".
Natural plasmids, shuttle plasmids, synthetic plasmids, and plasmid-derived
constructs may replicate without an obvious antibiotic marker or familiar
engineered-part layout.

The default validity check therefore asks for broad signals:

- the sequence is valid, normalized DNA;
- topology is known, or the caller supplied enough context to interpret it;
- the sequence has no severe ambiguity;
- there is positive plasmid evidence when available, such as circular topology,
  a replication origin, a replicon call, mobility evidence, host-range evidence,
  or whole-plasmid similarity;
- detected critical components are not obviously broken, partial, or conflicted.

This can produce:

```text
Validity: pass
Utility as lab vector: fail
Prompt fidelity: fail
```

That is a useful result. It says the plasmid is interpretable, but not the thing
the user asked for.

## Utility

Utility presets are named bundles of deterministic checks. Presets make common
questions easy without requiring users to write schemas.

Starter presets are:

| Preset | Intent |
| --- | --- |
| `plasmid_candidate` | Loose baseline validity for a plasmid-like sequence. |
| `replicative_plasmid` | Requires replication evidence such as an origin or replicon. |
| `lab_vector` | Requires replication evidence and a selection marker. |
| `cloning_vector` | Lab vector expectations plus cloning-site signals when available. |
| `bacterial_expression_vector` | Lab vector expectations plus expression-cassette checks when available. |
| `natural_plasmid` | Replication, mobility, host-range, or similarity evidence without engineered-backbone assumptions. |

Presets are intentionally transparent. Reports list each check, its status, the
evidence IDs used, and why the check passed, failed, warned, or remained
unknown.

## Fidelity

Fidelity compares a plasmid against requirements parsed from a user request. The
requirement set is independent of the plasmid.

For example, this prompt:

```text
amp resistant high copy number ecoli vector expressing ATCGTGCA
```

should parse into requirements like:

```json
{
  "preset": "bacterial_expression_vector",
  "requirements": [
    {
      "check": "selection_marker",
      "value": "ampicillin",
      "source_text": "amp resistant",
      "confidence": 0.92,
      "canonicalization_status": "canonical",
      "ambiguities": []
    },
    {
      "check": "copy_number",
      "value": "high",
      "source_text": "high copy number",
      "confidence": 0.85,
      "canonicalization_status": "inferred",
      "ambiguities": []
    },
    {
      "check": "host",
      "value": "E. coli",
      "source_text": "ecoli",
      "confidence": 0.9,
      "canonicalization_status": "canonical",
      "ambiguities": []
    },
    {
      "check": "payload_sequence",
      "value": "ATCGTGCA",
      "source_text": "expressing ATCGTGCA",
      "confidence": 0.88,
      "canonicalization_status": "literal",
      "ambiguities": []
    }
  ]
}
```

The LLM's job is only to fill this requirement schema from natural language.
Deterministic code validates the schema and evaluates the plasmid. The LLM does
not inspect raw DNA and does not decide pass or fail.

This split keeps the end-user experience simple:

```python
validity = po.evaluate(plasmid)
utility = po.evaluate(plasmid, preset="lab_vector")
fidelity = po.evaluate(plasmid, requirements=parsed_requirements)
```

It also keeps the LLM layer reliable:

- Plasmid Oracle generates the JSON Schema from its own registered checks and
  presets.
- The model can choose only known check names and preset IDs.
- Every parsed requirement carries source text, confidence, canonicalization
  status, and ambiguity notes.
- Schema-valid output is still validated semantically before evaluation.

## Walkthrough

The easiest path is a single call:

```python
validity = po.evaluate(plasmid)
print(validity.status)
```

This answers loose plasmid validity. It does not require a selectable marker.

For a common use case, choose a preset:

```python
lab_vector = po.evaluate(plasmid, preset="lab_vector")

for finding in lab_vector.findings:
    print(finding.check, finding.status.value, finding.message)
```

For stricter labs or benchmark work, pass a config:

```python
strict_lab_vector = po.evaluate(
    plasmid,
    preset="lab_vector",
    config=po.EvaluationConfig(
        min_identity=0.95,
        min_coverage=0.95,
    ),
)
```

For a natural-language workflow, inject the schema generated by Plasmid Oracle
into the model call, then validate the model output before evaluation:

```python
schema = po.requirement_schema()

# Send `schema` to an LLM structured-output call, together with the user prompt.
# The model output should be a plain JSON-compatible object.
parsed = po.requirements_from_dict(model_output)

validity = po.evaluate(plasmid)
fidelity = po.evaluate(plasmid, requirements=parsed)
```

The repository includes a runnable example that evaluates the saved pBR322
standard result without requiring external databases:

```bash
python examples/evaluate_plasmid.py
```

## Current Status

This first evaluation slice implements baseline validity, replication evidence,
selection marker checks, prompt-fidelity checks for selection marker and payload
sequence, requirement-schema generation, and configurable identity/coverage
thresholds.

Expression-cassette inference, host compatibility calibration, and copy-number
classification are intentionally conservative and may return `unknown` until
their benchmark-backed implementations are added.
