from __future__ import annotations

from typing import TYPE_CHECKING

from plasmid_oracle.model import ProviderStatus, ResolvedAnnotation

if TYPE_CHECKING:
    from plasmid_oracle.model import Plasmid


def _identifier(plasmid: Plasmid) -> str:
    identifier = plasmid.source_metadata.get("id")
    return str(identifier) if identifier is not None else plasmid.sequence.checksum[:12]


def _feature_location(feature: ResolvedAnnotation) -> str:
    if feature.location.wraps_origin:
        spans = ", ".join(f"[{span.start}, {span.end})" for span in feature.location.spans)
        return f"{spans} {feature.location.strand.value}"
    return f"[{feature.location.start}, {feature.location.end}) {feature.location.strand.value}"


def _feature_line(feature: ResolvedAnnotation) -> str:
    providers = ", ".join(feature.providers)
    aliases = f"; aliases: {', '.join(feature.aliases)}" if feature.aliases else ""
    return (
        f"  {feature.name} ({feature.feature_type}) "
        f"{_feature_location(feature)} [{feature.status.value}; {providers}{aliases}]"
    )


def render_text(plasmid: Plasmid) -> str:
    gc = (
        f"{plasmid.sequence.gc_fraction:.1%} GC"
        if plasmid.sequence.gc_fraction is not None
        else "GC unknown"
    )
    lines = [
        (
            f"{_identifier(plasmid)} | {plasmid.sequence.length:,} bp | "
            f"{plasmid.sequence.topology.value} | {gc}"
        ),
        (
            f"{len(plasmid.annotations)} resolved annotations from "
            f"{len(plasmid.evidence)} evidence calls"
        ),
    ]

    if plasmid.annotations:
        lines.extend(("", "Annotations"))
        lines.extend(_feature_line(feature) for feature in plasmid.annotations)
    else:
        lines.extend(("", "Annotations", "  None detected"))

    characterization = plasmid.characterization
    if (
        characterization.replicons
        or characterization.mobility
        or characterization.orit_sites
        or characterization.host_range
    ):
        lines.extend(("", "Characterization"))
        for label, calls in (
            ("Replicon", characterization.replicons),
            ("Mobility", characterization.mobility),
            ("oriT", characterization.orit_sites),
            ("Host range", characterization.host_range),
        ):
            for call in calls:
                basis = call.qualifiers.get("basis")
                suffix = f" ({basis})" if basis else ""
                lines.append(f"  {label}: {call.name}{suffix}")

    if plasmid.analysis.provider_runs:
        lines.extend(("", "Providers"))
        for run in plasmid.analysis.provider_runs:
            detail = run.status.value
            if run.tool_version:
                detail = f"{detail}, tool {run.tool_version}"
            lines.append(f"  {run.name}: {detail}")

    warnings: list[str] = []
    warnings.extend(warning.message for warning in plasmid.sequence.warnings)
    warnings.extend(plasmid.analysis.warnings)
    for feature in plasmid.annotations:
        warnings.extend(f"{feature.name}: {conflict.message}" for conflict in feature.conflicts)
    for run in plasmid.analysis.provider_runs:
        if run.status not in {ProviderStatus.COMPLETED, ProviderStatus.CACHED}:
            warnings.append(f"{run.name}: {run.error or run.status.value}")
        warnings.extend(f"{run.name}: {warning}" for warning in run.warnings)
    if warnings:
        lines.extend(("", "Warnings"))
        lines.extend(f"  {warning}" for warning in warnings)

    return "\n".join(lines)


def annotation_rows(plasmid: Plasmid) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for feature in plasmid.annotations:
        rows.append(
            {
                "annotation_id": feature.annotation_id,
                "feature_type": feature.feature_type,
                "name": feature.name,
                "aliases": ", ".join(feature.aliases),
                "start": feature.location.start,
                "end": feature.location.end,
                "wraps_origin": feature.location.wraps_origin,
                "strand": feature.location.strand.value,
                "status": feature.status.value,
                "integrity": feature.integrity.value,
                "providers": ", ".join(feature.providers),
                "support_count": feature.support_count,
                "conflicts": ", ".join(conflict.code for conflict in feature.conflicts),
            }
        )
    return tuple(rows)
