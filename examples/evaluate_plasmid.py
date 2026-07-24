from __future__ import annotations

from pathlib import Path

import plasmid_oracle as po


def _print_report(title: str, report: po.EvaluationReport) -> None:
    print(title)
    print(f"  status: {report.status.value}")
    print(f"  scope: {report.scope.value}")
    for finding in report.findings:
        requirement = "required" if finding.required else "advisory"
        print(f"  - {finding.check}: {finding.status.value} ({requirement})")
        print(f"    {finding.message}")


def main() -> None:
    example_path = Path(__file__).parent / "results" / "pBR322_J01749.1.standard.json"
    plasmid = po.from_json(example_path.read_text(encoding="utf-8"))

    validity = po.evaluate(plasmid)
    lab_vector = po.evaluate(plasmid, preset="lab_vector")

    prompt_requirements = po.requirements_from_dict(
        {
            "preset": None,
            "requirements": [
                {
                    "check": "selection_marker",
                    "value": "ampicillin",
                    "source_text": "amp resistant",
                    "confidence": 0.9,
                    "canonicalization_status": "canonical",
                    "ambiguities": [],
                },
                {
                    "check": "copy_number",
                    "value": "high",
                    "source_text": "high copy number",
                    "confidence": 0.8,
                    "canonicalization_status": "inferred",
                    "ambiguities": [],
                },
                {
                    "check": "payload_sequence",
                    "value": "GGGGAAAACCCC",
                    "source_text": "expressing GGGGAAAACCCC",
                    "confidence": 0.85,
                    "canonicalization_status": "literal",
                    "ambiguities": [],
                },
            ],
        }
    )
    fidelity = po.evaluate(plasmid, requirements=prompt_requirements)

    _print_report("Validity", validity)
    _print_report("Lab vector utility", lab_vector)
    _print_report("Prompt fidelity", fidelity)


if __name__ == "__main__":
    main()
