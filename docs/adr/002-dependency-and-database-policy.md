# ADR-002: Keep Large Tools and Databases Explicit

## Status

Accepted

## Context

Pyrodigal ships modern Python wheels and has a stable typed API. pLannotate is a
large optional Python package with external executable requirements. AMRFinderPlus
is distributed as a compiled bioinformatics tool. MOB-suite 3.1.9's Python
package pins old NumPy and Pandas versions that conflict with a modern package
environment.

All three standard-mode providers require databases that are too large or too
volatile to hide in the Plasmid Oracle wheel.

## Decision

- Pyrodigal is a required runtime dependency and powers `fast` mode.
- pLannotate is an optional extra named `plannotate`.
- AMRFinderPlus and MOB-suite are external CLI dependencies.
- MOB-suite is not installed as a Python dependency.
- Annotation never downloads a database.
- `setup(component)` is an explicit user action.
- Executable and database locations can be supplied through environment
  variables.
- Exact tool and database versions are recorded in provider manifests.

## Alternatives Considered

- Put every tool in one Python environment: simpler instructions, but currently
  creates dependency conflicts and fragile installations.
- Bundle all databases in the wheel: zero setup, but impractical wheel size and
  opaque scientific updates.
- Download on first annotation: convenient once, but surprising, slow, and
  hostile to reproducibility and offline environments.

## Consequences

- Core installation remains small and works on supported Python versions.
- Standard mode requires explicit system preparation.
- `doctor()` can explain missing components before a long analysis begins.
- Container and Conda recipes can provide a batteries-included deployment later.

## Revisit When

- MOB-suite publishes a modern dependency-compatible Python distribution.
- A versioned, redistributable combined database pack is maintained by this
  project.
