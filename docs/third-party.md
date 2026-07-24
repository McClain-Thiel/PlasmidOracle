# Third-Party Software and Data

Status: dependency inventory for the `0.2.0a0` package design

This document is an engineering inventory, not legal advice. The Plasmid
Oracle project license has not yet been selected.

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

## Before Publication

1. Select and add the Plasmid Oracle project license.
2. Review compatibility with the required Pyrodigal dependency and the
   optional pLannotate integration.
3. Pin this inventory to the dependency versions used for a release.
4. Preserve upstream notices in any container or bundled distribution that
   includes external tools.
