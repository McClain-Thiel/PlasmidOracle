from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from plasmid_oracle.errors import InvalidSequenceError
from plasmid_oracle.model import Integrity, Plasmid, ProviderStatus, ResolvedAnnotation, Topology
from plasmid_oracle.model.evaluation import (
    EvaluationConfig,
    EvaluationFinding,
    EvaluationReport,
    EvaluationScope,
    EvaluationStatus,
    JsonScalar,
    Requirement,
    RequirementSet,
)
from plasmid_oracle.model.sequence import SequenceInfo, reverse_complement


@dataclass(frozen=True, slots=True)
class _Preset:
    scope: EvaluationScope
    required_checks: tuple[str, ...]
    advisory_checks: tuple[str, ...] = ()


_PRESETS: Mapping[str, _Preset] = {
    "plasmid_candidate": _Preset(
        scope=EvaluationScope.VALIDITY,
        required_checks=("sequence_evaluable", "plasmid_evidence"),
        advisory_checks=("red_flags", "evidence_complete_enough"),
    ),
    "replicative_plasmid": _Preset(
        scope=EvaluationScope.UTILITY,
        required_checks=("sequence_evaluable", "has_replication_component"),
        advisory_checks=("red_flags", "evidence_complete_enough"),
    ),
    "natural_plasmid": _Preset(
        scope=EvaluationScope.UTILITY,
        required_checks=("sequence_evaluable", "plasmid_evidence"),
        advisory_checks=("red_flags", "evidence_complete_enough"),
    ),
    "lab_vector": _Preset(
        scope=EvaluationScope.UTILITY,
        required_checks=(
            "sequence_evaluable",
            "has_replication_component",
            "has_selection_component",
        ),
        advisory_checks=("red_flags", "evidence_complete_enough"),
    ),
    "cloning_vector": _Preset(
        scope=EvaluationScope.UTILITY,
        required_checks=(
            "sequence_evaluable",
            "has_replication_component",
            "has_selection_component",
        ),
        advisory_checks=("red_flags", "evidence_complete_enough"),
    ),
    "bacterial_expression_vector": _Preset(
        scope=EvaluationScope.UTILITY,
        required_checks=(
            "sequence_evaluable",
            "has_replication_component",
            "has_selection_component",
        ),
        advisory_checks=("red_flags", "evidence_complete_enough", "expression_cassette"),
    ),
}

_REQUIREMENT_CHECKS = (
    "selection_marker",
    "payload_sequence",
    "copy_number",
    "host",
)
_CHECKS = tuple(
    sorted(
        {
            "sequence_evaluable",
            "plasmid_evidence",
            "has_replication_component",
            "has_selection_component",
            "red_flags",
            "evidence_complete_enough",
            "expression_cassette",
            *_REQUIREMENT_CHECKS,
        }
    )
)
_ABSENCE_CONCEPTS: Mapping[str, frozenset[str]] = {
    "plasmid_evidence": frozenset(
        {
            "replication_component",
            "replicon",
            "orit_site",
            "mobility",
            "plasmid_similarity",
        }
    ),
    "has_replication_component": frozenset({"replication_component", "replicon", "origin"}),
    "has_selection_component": frozenset(
        {"selectable_marker", "selection_marker", "antimicrobial_resistance_gene"}
    ),
    "selection_marker": frozenset(
        {"selectable_marker", "selection_marker", "antimicrobial_resistance_gene"}
    ),
    "host": frozenset({"host_range"}),
}
_ANTIBIOTIC_SYNONYMS: Mapping[str, tuple[str, ...]] = {
    "ampicillin": ("ampicillin", "amp", "carbenicillin", "beta-lactam", "bla", "tem"),
    "carbenicillin": ("carbenicillin", "ampicillin", "beta-lactam", "bla", "tem"),
    "tetracycline": ("tetracycline", "tet"),
    "chloramphenicol": ("chloramphenicol", "cmr", "cat", "cml"),
    "kanamycin": ("kanamycin", "kan", "aph", "npt"),
}


def check(
    plasmid: Plasmid,
    check_id: str,
    *,
    value: JsonScalar | None = None,
    config: EvaluationConfig | None = None,
) -> EvaluationFinding:
    if not isinstance(plasmid, Plasmid):
        raise TypeError("check expects a Plasmid")
    normalized = _validate_check_id(check_id)
    return _run_check(
        plasmid,
        normalized,
        value=value,
        config=config or EvaluationConfig(),
        required=True,
    )


def evaluate(
    plasmid: Plasmid,
    *,
    preset: str | None = "plasmid_candidate",
    requirements: RequirementSet | Mapping[str, object] | Sequence[Requirement] | None = None,
    config: EvaluationConfig | None = None,
) -> EvaluationReport:
    if not isinstance(plasmid, Plasmid):
        raise TypeError("evaluate expects a Plasmid")
    active_config = config or EvaluationConfig()
    requirement_set = _coerce_requirements(requirements)
    active_preset = _active_preset(preset, requirement_set)

    findings: list[EvaluationFinding] = []
    scope = EvaluationScope.FIDELITY if requirement_set is not None else EvaluationScope.VALIDITY
    if active_preset is not None:
        preset_definition = _preset(active_preset)
        scope = EvaluationScope.FIDELITY if requirement_set is not None else preset_definition.scope
        findings.extend(
            _run_check(plasmid, check_id, config=active_config, required=True)
            for check_id in preset_definition.required_checks
        )
        findings.extend(
            _run_check(plasmid, check_id, config=active_config, required=False)
            for check_id in preset_definition.advisory_checks
        )

    if requirement_set is not None:
        for requirement in requirement_set.requirements:
            findings.append(
                _run_check(
                    plasmid,
                    _validate_requirement_check(requirement.check),
                    value=requirement.value,
                    config=active_config,
                    required=True,
                    requirement=requirement,
                )
            )

    if not findings:
        raise ValueError("Evaluation requires a preset or at least one requirement")

    return EvaluationReport(
        scope=scope,
        status=_aggregate(findings),
        preset=active_preset,
        findings=tuple(findings),
        requirements=requirement_set,
        config=active_config,
    )


def requirement_schema() -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "PlasmidOracleRequirementSet",
        "type": "object",
        "additionalProperties": False,
        "required": ["preset", "requirements"],
        "properties": {
            "preset": {
                "type": ["string", "null"],
                "enum": [None, *sorted(_PRESETS)],
            },
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "check",
                        "value",
                        "source_text",
                        "confidence",
                        "canonicalization_status",
                        "ambiguities",
                    ],
                    "properties": {
                        "check": {"type": "string", "enum": list(_REQUIREMENT_CHECKS)},
                        "value": {
                            "type": ["string", "number", "boolean", "null"],
                            "description": (
                                "Canonical requirement value, such as ampicillin or ATCGTGCA."
                            ),
                        },
                        "source_text": {
                            "type": "string",
                            "description": "Exact prompt span that produced this requirement.",
                        },
                        "confidence": {
                            "type": ["number", "null"],
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "canonicalization_status": {
                            "type": "string",
                            "enum": ["canonical", "inferred", "literal", "ambiguous", "unresolved"],
                        },
                        "ambiguities": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    }


def requirements_from_dict(payload: Mapping[str, object]) -> RequirementSet:
    if not isinstance(payload, Mapping):
        raise TypeError("requirements_from_dict expects a mapping")
    allowed_top_level = {"preset", "requirements"}
    extra_top_level = set(payload) - allowed_top_level
    if extra_top_level:
        extras = ", ".join(sorted(extra_top_level))
        raise ValueError(f"Unsupported requirement payload fields: {extras}")

    preset_value = payload.get("preset")
    if preset_value is None:
        preset: str | None = None
    elif isinstance(preset_value, str):
        preset = _validate_preset_id(preset_value)
    else:
        raise ValueError("Requirement preset must be a string or null")

    requirement_items = payload.get("requirements")
    if not isinstance(requirement_items, Sequence) or isinstance(requirement_items, str | bytes):
        raise ValueError("Requirement payload must contain a requirements array")

    requirements: list[Requirement] = []
    for index, item in enumerate(requirement_items):
        if not isinstance(item, Mapping):
            raise ValueError(f"Requirement {index} must be an object")
        requirements.append(_requirement_from_mapping(item, index=index))
    return RequirementSet(preset=preset, requirements=tuple(requirements))


def _requirement_from_mapping(payload: Mapping[object, object], *, index: int) -> Requirement:
    allowed_fields = {
        "check",
        "value",
        "source_text",
        "confidence",
        "canonicalization_status",
        "ambiguities",
    }
    if not all(isinstance(key, str) for key in payload):
        raise ValueError(f"Requirement {index} keys must be strings")
    extra_fields = set(payload) - allowed_fields
    if extra_fields:
        extras = ", ".join(sorted(str(field) for field in extra_fields))
        raise ValueError(f"Unsupported requirement fields: {extras}")

    check_value = payload.get("check")
    if not isinstance(check_value, str):
        raise ValueError(f"Requirement {index} check must be a string")
    check_id = _validate_requirement_check(check_value)

    value = payload.get("value")
    if value is not None and not isinstance(value, str | int | float | bool):
        raise ValueError(f"Requirement {index} value must be a string, number, boolean, or null")

    source_text = payload.get("source_text")
    if not isinstance(source_text, str):
        raise ValueError(f"Requirement {index} source_text must be a string")

    confidence = payload.get("confidence")
    if confidence is not None and (
        not isinstance(confidence, int | float) or isinstance(confidence, bool)
    ):
        raise ValueError(f"Requirement {index} confidence must be a number or null")

    canonicalization_status = payload.get("canonicalization_status")
    if not isinstance(canonicalization_status, str):
        raise ValueError(f"Requirement {index} canonicalization_status must be a string")

    ambiguities = payload.get("ambiguities")
    if not isinstance(ambiguities, Sequence) or isinstance(ambiguities, str | bytes):
        raise ValueError(f"Requirement {index} ambiguities must be an array")
    if not all(isinstance(item, str) for item in ambiguities):
        raise ValueError(f"Requirement {index} ambiguities must contain only strings")

    return Requirement(
        check=check_id,
        value=value,
        source_text=source_text,
        confidence=float(confidence) if confidence is not None else None,
        canonicalization_status=canonicalization_status,
        ambiguities=tuple(ambiguities),
    )


def _active_preset(preset: str | None, requirements: RequirementSet | None) -> str | None:
    if requirements is not None and requirements.preset is not None:
        return _validate_preset_id(requirements.preset)
    if requirements is not None and preset == "plasmid_candidate":
        return None
    return _validate_preset_id(preset) if preset is not None else None


def _preset(preset: str) -> _Preset:
    return _PRESETS[_validate_preset_id(preset)]


def _validate_preset_id(preset: str | None) -> str:
    if preset is None:
        raise ValueError("Preset cannot be null here")
    normalized = preset.strip()
    if normalized not in _PRESETS:
        choices = ", ".join(sorted(_PRESETS))
        raise ValueError(f"Unsupported evaluation preset {preset!r}; expected one of: {choices}")
    return normalized


def _validate_check_id(check_id: str) -> str:
    normalized = check_id.strip()
    if normalized not in _CHECKS:
        choices = ", ".join(_CHECKS)
        raise ValueError(f"Unsupported evaluation check {check_id!r}; expected one of: {choices}")
    return normalized


def _validate_requirement_check(check_id: str) -> str:
    normalized = check_id.strip()
    if normalized not in _REQUIREMENT_CHECKS:
        choices = ", ".join(_REQUIREMENT_CHECKS)
        raise ValueError(f"Unsupported requirement check {check_id!r}; expected one of: {choices}")
    return normalized


def _coerce_requirements(
    requirements: RequirementSet | Mapping[str, object] | Sequence[Requirement] | None,
) -> RequirementSet | None:
    if requirements is None:
        return None
    if isinstance(requirements, RequirementSet):
        for requirement in requirements.requirements:
            _validate_requirement_check(requirement.check)
        if requirements.preset is not None:
            _validate_preset_id(requirements.preset)
        return requirements
    if isinstance(requirements, Mapping):
        return requirements_from_dict(requirements)
    if isinstance(requirements, Sequence) and not isinstance(requirements, str | bytes):
        if not all(isinstance(item, Requirement) for item in requirements):
            raise TypeError("Requirement sequences must contain only Requirement objects")
        return RequirementSet(requirements=tuple(requirements))
    raise TypeError("requirements must be a RequirementSet, mapping, sequence, or None")


def _run_check(
    plasmid: Plasmid,
    check_id: str,
    *,
    value: JsonScalar | None = None,
    config: EvaluationConfig,
    required: bool,
    requirement: Requirement | None = None,
) -> EvaluationFinding:
    normalized = _validate_check_id(check_id)
    if normalized == "sequence_evaluable":
        finding = _check_sequence_evaluable(plasmid)
    elif normalized == "plasmid_evidence":
        finding = _check_plasmid_evidence(plasmid, config=config)
    elif normalized == "has_replication_component":
        finding = _check_replication_component(plasmid, config=config)
    elif normalized == "has_selection_component":
        finding = _check_selection_marker(plasmid, value=None, config=config)
    elif normalized == "selection_marker":
        finding = _check_selection_marker(plasmid, value=value, config=config)
    elif normalized == "payload_sequence":
        finding = _check_payload_sequence(plasmid, value=value)
    elif normalized == "copy_number":
        finding = _check_copy_number(plasmid, value=value)
    elif normalized == "host":
        finding = _check_host(plasmid, value=value)
    elif normalized == "red_flags":
        finding = _check_red_flags(plasmid)
    elif normalized == "evidence_complete_enough":
        finding = _check_evidence_complete(plasmid)
    elif normalized == "expression_cassette":
        finding = EvaluationFinding(
            check=normalized,
            status=EvaluationStatus.UNKNOWN,
            message="Expression cassette inference is not implemented yet",
        )
    else:  # pragma: no cover - _validate_check_id keeps this unreachable.
        raise AssertionError(f"Unhandled check {check_id!r}")
    return EvaluationFinding(
        check=finding.check,
        status=finding.status,
        message=finding.message,
        evidence_ids=finding.evidence_ids,
        required=required,
        requirement=requirement,
        metadata=finding.metadata,
    )


def _check_sequence_evaluable(plasmid: Plasmid) -> EvaluationFinding:
    if plasmid.sequence.length <= 0:
        return EvaluationFinding(
            check="sequence_evaluable",
            status=EvaluationStatus.FAIL,
            message="Sequence is empty",
        )
    if plasmid.sequence.ambiguous_base_count:
        return EvaluationFinding(
            check="sequence_evaluable",
            status=EvaluationStatus.WARNING,
            message=(
                "Sequence is evaluable but contains "
                f"{plasmid.sequence.ambiguous_base_count} ambiguous bases"
            ),
            metadata={"ambiguous_base_count": plasmid.sequence.ambiguous_base_count},
        )
    return EvaluationFinding(
        check="sequence_evaluable",
        status=EvaluationStatus.PASS,
        message="Sequence is valid normalized DNA",
    )


def _check_plasmid_evidence(plasmid: Plasmid, *, config: EvaluationConfig) -> EvaluationFinding:
    replication_features = _replication_features(plasmid, config=config)
    if plasmid.sequence.topology is Topology.CIRCULAR:
        return EvaluationFinding(
            check="plasmid_evidence",
            status=EvaluationStatus.PASS,
            message="Circular topology supports plasmid-like interpretation",
            evidence_ids=_evidence_ids(replication_features),
        )
    if replication_features or _has_plasmid_characterization(plasmid):
        evidence_ids = list(_evidence_ids(replication_features))
        evidence_ids.extend(_characterization_ids(plasmid))
        return EvaluationFinding(
            check="plasmid_evidence",
            status=EvaluationStatus.PASS,
            message="Detected plasmid-associated replication or characterization evidence",
            evidence_ids=tuple(evidence_ids),
        )
    return _absence_finding(
        plasmid,
        "plasmid_evidence",
        absent_message="No plasmid-associated evidence was detected",
        unknown_message="Plasmid-associated evidence was not fully tested",
    )


def _check_replication_component(
    plasmid: Plasmid,
    *,
    config: EvaluationConfig,
) -> EvaluationFinding:
    features = _replication_features(plasmid, config=config)
    if features:
        names = ", ".join(feature.name for feature in features[:3])
        return EvaluationFinding(
            check="has_replication_component",
            status=EvaluationStatus.PASS,
            message=f"Detected replication component: {names}",
            evidence_ids=_evidence_ids(features),
        )
    candidates = _replication_features(plasmid, config=None)
    if candidates:
        names = ", ".join(feature.name for feature in candidates[:3])
        return EvaluationFinding(
            check="has_replication_component",
            status=EvaluationStatus.FAIL,
            message=f"Replication evidence did not meet configured thresholds: {names}",
            evidence_ids=_evidence_ids(candidates),
        )
    if plasmid.characterization.replicons:
        names = ", ".join(call.name for call in plasmid.characterization.replicons[:3])
        return EvaluationFinding(
            check="has_replication_component",
            status=EvaluationStatus.PASS,
            message=f"Detected replicon characterization: {names}",
            evidence_ids=tuple(call.evidence_id for call in plasmid.characterization.replicons),
        )
    return _absence_finding(
        plasmid,
        "has_replication_component",
        absent_message="No replication origin or replicon was detected",
        unknown_message="Replication evidence was not fully tested",
    )


def _check_selection_marker(
    plasmid: Plasmid,
    *,
    value: JsonScalar | None,
    config: EvaluationConfig,
) -> EvaluationFinding:
    features = _selection_features(plasmid, config=config)
    if value is None:
        if features:
            names = ", ".join(feature.name for feature in features[:3])
            return EvaluationFinding(
                check="has_selection_component",
                status=EvaluationStatus.PASS,
                message=f"Detected selection marker evidence: {names}",
                evidence_ids=_evidence_ids(features),
            )
        candidates = _selection_features(plasmid, config=None)
        if candidates:
            names = ", ".join(feature.name for feature in candidates[:3])
            return EvaluationFinding(
                check="has_selection_component",
                status=EvaluationStatus.FAIL,
                message=f"Selection marker evidence did not meet configured thresholds: {names}",
                evidence_ids=_evidence_ids(candidates),
            )
        return _absence_finding(
            plasmid,
            "has_selection_component",
            absent_message="No selection marker was detected",
            unknown_message="Selection marker evidence was not fully tested",
        )

    expected = str(value).strip()
    if not expected:
        return EvaluationFinding(
            check="selection_marker",
            status=EvaluationStatus.UNKNOWN,
            message="Selection marker requirement did not include a value",
        )
    matching = tuple(feature for feature in features if _selection_matches(feature, expected))
    if matching:
        names = ", ".join(feature.name for feature in matching[:3])
        return EvaluationFinding(
            check="selection_marker",
            status=EvaluationStatus.PASS,
            message=f"Detected requested selection marker {expected}: {names}",
            evidence_ids=_evidence_ids(matching),
            metadata={"expected": expected},
        )
    if features:
        names = ", ".join(feature.name for feature in features[:3])
        return EvaluationFinding(
            check="selection_marker",
            status=EvaluationStatus.FAIL,
            message=f"Detected selection marker evidence, but not {expected}: {names}",
            evidence_ids=_evidence_ids(features),
            metadata={"expected": expected},
        )
    candidates = _selection_features(plasmid, config=None)
    if candidates:
        names = ", ".join(feature.name for feature in candidates[:3])
        return EvaluationFinding(
            check="selection_marker",
            status=EvaluationStatus.FAIL,
            message=f"Selection marker evidence for {expected} did not meet thresholds: {names}",
            evidence_ids=_evidence_ids(candidates),
            metadata={"expected": expected},
        )
    return _absence_finding(
        plasmid,
        "selection_marker",
        absent_message=f"No selection marker matching {expected} was detected",
        unknown_message=f"Selection marker evidence for {expected} was not fully tested",
    )


def _check_payload_sequence(plasmid: Plasmid, *, value: JsonScalar | None) -> EvaluationFinding:
    if not isinstance(value, str) or not value.strip():
        return EvaluationFinding(
            check="payload_sequence",
            status=EvaluationStatus.UNKNOWN,
            message="Payload sequence requirement did not include DNA bases",
        )
    try:
        query = SequenceInfo.from_raw(value, topology="linear").bases
    except InvalidSequenceError:
        return EvaluationFinding(
            check="payload_sequence",
            status=EvaluationStatus.UNKNOWN,
            message="Payload sequence requirement is not valid IUPAC DNA",
            metadata={"expected": value},
        )

    if _contains_sequence(plasmid, query):
        return EvaluationFinding(
            check="payload_sequence",
            status=EvaluationStatus.PASS,
            message="Requested payload sequence is present",
            metadata={"expected": query},
        )
    return EvaluationFinding(
        check="payload_sequence",
        status=EvaluationStatus.FAIL,
        message="Requested payload sequence was not detected",
        metadata={"expected": query},
    )


def _check_copy_number(plasmid: Plasmid, *, value: JsonScalar | None) -> EvaluationFinding:
    expected = str(value).strip().casefold() if value is not None else ""
    text = _combined_feature_text(_replication_features(plasmid, config=EvaluationConfig()))
    if expected == "high" and any(token in text for token in ("high-copy", "high copy", "puc")):
        return EvaluationFinding(
            check="copy_number",
            status=EvaluationStatus.PASS,
            message="Replication evidence is consistent with high copy number",
            metadata={"expected": expected},
        )
    return EvaluationFinding(
        check="copy_number",
        status=EvaluationStatus.UNKNOWN,
        message="Copy number inference is not strong enough for this requirement",
        metadata={"expected": expected or None},
    )


def _check_host(plasmid: Plasmid, *, value: JsonScalar | None) -> EvaluationFinding:
    expected = str(value).strip().casefold() if value is not None else ""
    host_range = plasmid.characterization.host_range
    if expected and any(expected in call.name.casefold() for call in host_range):
        return EvaluationFinding(
            check="host",
            status=EvaluationStatus.PASS,
            message=f"Host-range evidence includes {value}",
            evidence_ids=tuple(call.evidence_id for call in host_range),
            metadata={"expected": str(value)},
        )
    if host_range:
        return EvaluationFinding(
            check="host",
            status=EvaluationStatus.UNKNOWN,
            message="Host-range evidence exists but does not confidently prove the requested host",
            evidence_ids=tuple(call.evidence_id for call in host_range),
            metadata={"expected": str(value) if value is not None else None},
        )
    return _absence_finding(
        plasmid,
        "host",
        absent_message="No host-range evidence was detected",
        unknown_message="Host-range evidence was not fully tested",
    )


def _check_red_flags(plasmid: Plasmid) -> EvaluationFinding:
    issues: list[str] = []
    evidence_ids: list[str] = []
    for feature in plasmid.annotations:
        if feature.conflicts:
            issues.append(f"{feature.name} has conflicting evidence")
            evidence_ids.extend(item.evidence_id for item in feature.evidence)
        if feature.feature_type.casefold() in {"rep_origin", "antimicrobial_resistance_gene"} and (
            feature.integrity in {Integrity.PARTIAL, Integrity.INTERRUPTED, Integrity.AMBIGUOUS}
        ):
            issues.append(f"{feature.name} is {feature.integrity.value}")
            evidence_ids.extend(item.evidence_id for item in feature.evidence)
    for flag in plasmid.characterization.quality_flags:
        if flag.severity.casefold() in {"warning", "error"}:
            issues.append(flag.message)
            evidence_ids.append(flag.evidence_id)
    if issues:
        return EvaluationFinding(
            check="red_flags",
            status=EvaluationStatus.WARNING,
            message="; ".join(issues[:3]),
            evidence_ids=tuple(evidence_ids),
        )
    return EvaluationFinding(
        check="red_flags",
        status=EvaluationStatus.PASS,
        message="No obvious evaluation red flags were detected",
        required=False,
    )


def _check_evidence_complete(plasmid: Plasmid) -> EvaluationFinding:
    runs = plasmid.analysis.provider_runs
    if not runs:
        return EvaluationFinding(
            check="evidence_complete_enough",
            status=EvaluationStatus.UNKNOWN,
            message="No provider runs are recorded, so absence-based claims are limited",
            required=False,
        )
    incomplete = tuple(
        run for run in runs if run.status not in {ProviderStatus.COMPLETED, ProviderStatus.CACHED}
    )
    if incomplete:
        names = ", ".join(run.name for run in incomplete)
        return EvaluationFinding(
            check="evidence_complete_enough",
            status=EvaluationStatus.WARNING,
            message=f"Some providers did not complete: {names}",
            required=False,
        )
    return EvaluationFinding(
        check="evidence_complete_enough",
        status=EvaluationStatus.PASS,
        message="Recorded provider runs completed",
        required=False,
    )


def _replication_features(
    plasmid: Plasmid,
    *,
    config: EvaluationConfig | None,
) -> tuple[ResolvedAnnotation, ...]:
    return tuple(
        feature
        for feature in plasmid.annotations
        if feature.feature_type.strip().casefold()
        in {"rep_origin", "origin_of_replication", "replicon"}
        and (config is None or _feature_passes_thresholds(feature, config=config))
    )


def _selection_features(
    plasmid: Plasmid,
    *,
    config: EvaluationConfig | None,
) -> tuple[ResolvedAnnotation, ...]:
    return tuple(
        feature
        for feature in plasmid.annotations
        if feature.feature_type.strip().casefold()
        in {"antimicrobial_resistance_gene", "selectable_marker", "selection_marker"}
        and (config is None or _feature_passes_thresholds(feature, config=config))
    )


def _feature_passes_thresholds(
    feature: ResolvedAnnotation,
    *,
    config: EvaluationConfig,
) -> bool:
    if feature.integrity in {Integrity.PARTIAL, Integrity.INTERRUPTED}:
        return False
    for evidence in feature.evidence:
        identity = evidence.metrics.identity
        coverage = evidence.metrics.coverage
        if identity is not None and identity < config.min_identity:
            return False
        if coverage is not None and coverage < config.min_coverage:
            return False
    return True


def _has_plasmid_characterization(plasmid: Plasmid) -> bool:
    characterization = plasmid.characterization
    return bool(
        characterization.replicons
        or characterization.mobility
        or characterization.orit_sites
        or characterization.host_range
        or characterization.similarity_hits
    )


def _evidence_ids(features: Sequence[ResolvedAnnotation]) -> tuple[str, ...]:
    return tuple(evidence.evidence_id for feature in features for evidence in feature.evidence)


def _characterization_ids(plasmid: Plasmid) -> tuple[str, ...]:
    characterization = plasmid.characterization
    return tuple(
        call.evidence_id
        for calls in (
            characterization.replicons,
            characterization.relaxases,
            characterization.mpf_types,
            characterization.orit_sites,
            characterization.mobility,
            characterization.host_range,
            characterization.similarity_hits,
        )
        for call in calls
    )


def _absence_finding(
    plasmid: Plasmid,
    check_id: str,
    *,
    absent_message: str,
    unknown_message: str,
) -> EvaluationFinding:
    if _can_make_absence_claim(plasmid, check_id):
        return EvaluationFinding(
            check=check_id,
            status=EvaluationStatus.FAIL,
            message=absent_message,
        )
    return EvaluationFinding(
        check=check_id,
        status=EvaluationStatus.UNKNOWN,
        message=unknown_message,
    )


def _can_make_absence_claim(plasmid: Plasmid, check_id: str) -> bool:
    concepts = _ABSENCE_CONCEPTS.get(check_id, frozenset())
    if not concepts:
        return False
    for run in plasmid.analysis.provider_runs:
        if run.status not in {ProviderStatus.COMPLETED, ProviderStatus.CACHED}:
            continue
        for capability in run.capabilities:
            if capability.concept in concepts and capability.supports_absence:
                return True
    return False


def _selection_matches(feature: ResolvedAnnotation, expected: str) -> bool:
    normalized = expected.casefold()
    aliases = _ANTIBIOTIC_SYNONYMS.get(normalized, (normalized,))
    text = _combined_feature_text((feature,))
    return any(alias.casefold() in text for alias in aliases)


def _combined_feature_text(features: Sequence[ResolvedAnnotation]) -> str:
    parts: list[str] = []
    for feature in features:
        parts.extend((feature.name, *feature.aliases, *feature.canonical_ids))
        for evidence in feature.evidence:
            parts.extend((evidence.name, *evidence.canonical_ids))
            parts.extend(str(value) for value in evidence.qualifiers.values())
    return " ".join(parts).casefold()


def _contains_sequence(plasmid: Plasmid, query: str) -> bool:
    bases = plasmid.sequence.bases
    candidates = {query, reverse_complement(query)}
    if plasmid.sequence.topology is Topology.CIRCULAR and len(query) > 1:
        search_space = bases + bases[: len(query) - 1]
    else:
        search_space = bases
    return any(candidate in search_space for candidate in candidates)


def _aggregate(findings: Sequence[EvaluationFinding]) -> EvaluationStatus:
    required = tuple(finding for finding in findings if finding.required)
    if any(finding.status is EvaluationStatus.FAIL for finding in required):
        return EvaluationStatus.FAIL
    if any(finding.status is EvaluationStatus.UNKNOWN for finding in required):
        return EvaluationStatus.UNKNOWN
    if any(finding.status is EvaluationStatus.WARNING for finding in findings):
        return EvaluationStatus.WARNING
    return EvaluationStatus.PASS
