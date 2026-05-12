# Architecture Decision Records (Seamount)

Seamount inherits suite-wide architecture decisions from `thermocline-py`.
Seamount has no repo-specific ADRs in v0.1 (per D-03 in Phase 4 CONTEXT).

## Inherited from `thermocline-py`
- [ADR-0001: Python 3.11 as primary language](../../../thermocline/docs/adr/ADR-0001-python-3-11-as-primary-language.md)
- [ADR-0003: Single canonical JSON path](../../../thermocline/docs/adr/ADR-0003-single-canonical-json-path.md)
- [ADR-0005: No in-process key material](../../../thermocline/docs/adr/ADR-0005-no-in-process-key-material.md)

Seamount-specific concerns (forge isolation, conformance harness scope) are
documented in `seamount/README.md` §"Forge Conformance Requirements" and
do not warrant their own ADRs at the v0.1 maturity level.
