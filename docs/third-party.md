# Third-Party Software and Data

Status: dependency inventory for the `0.2.0a1` release

This document is an engineering inventory, not legal advice. Plasmid Oracle is
distributed under GPL-3.0-only, matching the license of its required Pyrodigal
runtime dependency.

## Runtime Components

| Component | Relationship | Upstream license |
| --- | --- | --- |
| Pyrodigal | Required Python dependency | GPL-3.0 |
| pLannotate | Optional Python dependency | GPL-3.0-or-later |
| AMRFinderPlus | External executable and database | US Government public domain; see upstream terms |
| MOB-suite | External executable and database | Apache-2.0 |
| platformdirs | Required Python dependency | BSD-3-Clause |

Authoritative terms remain in each upstream distribution:

- [Pyrodigal on PyPI](https://pypi.org/project/pyrodigal/)
- [pLannotate license](https://github.com/McClain-Thiel/pLannotate/blob/main/LICENSE)
- [AMRFinderPlus license](https://github.com/ncbi/amr/blob/master/LICENSE)
- [MOB-suite license](https://github.com/phac-nml/mob-suite/blob/master/LICENSE)
- [platformdirs license](https://github.com/tox-dev/platformdirs/blob/main/LICENSE)

AMRFinderPlus and MOB-suite are discovered and invoked as external programs;
their code and databases are not included in the Plasmid Oracle wheel.
pLannotate is an opt-in extra and is also not included in the wheel. Pyrodigal
and platformdirs are declared package dependencies and are resolved separately
by the Python installer.

## Repository Fixtures

Recorded AMRFinderPlus output and the small `blaTEM` sequence fixture are
derived from the public NCBI AMRFinderPlus test corpus. They are test data, not
part of the installed wheel.

## Release Review

1. Review compatibility when adding or changing a runtime dependency.
2. Pin this inventory to the dependency versions used for a release.
3. Preserve upstream notices in any container or bundled distribution that
   includes external tools.
