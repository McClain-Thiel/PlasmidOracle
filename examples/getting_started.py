from __future__ import annotations

from pathlib import Path

import plasmid_oracle as po


def _example_sequence() -> str:
    example_path = Path(__file__).parent / "results" / "pBR322_J01749.1.standard.json"
    return po.from_json(example_path.read_text(encoding="utf-8")).sequence.bases


def main() -> None:
    sequence = _example_sequence()

    plasmid = po.plasmid(
        seq=sequence,
        topology="circular",
        source_metadata={"id": "pBR322"},
    )
    print("Normalize")
    print(f"  length: {plasmid.sequence.length}")
    print(f"  checksum: {plasmid.sequence.checksum}")

    result = po.annotate(
        seq=sequence,
        topology="circular",
        mode="minimal",
        source_metadata={"id": "pBR322"},
    )
    print("\nMinimal annotation")
    print(f"  resolved annotations: {len(result.annotations)}")
    print(f"  raw evidence calls: {len(result.evidence)}")

    coding_sequences = result.features(feature_type="CDS")
    print("\nQuery")
    print(f"  CDS features: {len(coding_sequences)}")
    print(f"  blaTEM hits in minimal mode: {len(result.find('blaTEM'))}")
    print(f"  AMR genes in minimal mode: {len(result.amr_genes)}")
    for feature in coding_sequences[:3]:
        print(
            f"  {feature.name} "
            f"[{feature.location.start}, {feature.location.end}) "
            f"{feature.location.strand.value} via {', '.join(feature.providers)}"
        )

    validity = po.evaluate(result)
    lab_vector = po.evaluate(result, preset="lab_vector")
    print("\nEvaluation")
    print(f"  validity: {validity.status.value}")
    for finding in validity.findings:
        print(f"    {finding.check}: {finding.status.value}")
    print(f"  lab_vector utility: {lab_vector.status.value}")
    for finding in lab_vector.findings:
        print(f"    {finding.check}: {finding.status.value}")

    restored = po.from_json(po.to_json(result))
    print("\nSave and restore")
    print(f"  round trip preserved: {restored == result}")


if __name__ == "__main__":
    main()
