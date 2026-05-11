"""forge_conformance — cross-suite conformance test harness (FORGE-04, FORGE-05).

Runs the Seamount 13-item conformance checklist against any Thermocline forge:
    8 numbered conformance items (1-8) from seamount/README.md §"Forge
    Conformance Requirements" + 5 attack-surface items (AT-E1..AT-E5) from
    §"Attack Surfaces and Mitigations".

Usage:
    python -m forge_conformance --target http://127.0.0.1:5100 --role pi-forge
    python -m forge_conformance --target http://127.0.0.1:5200 --role describe-forge --output json
"""
__version__ = "0.1.0"
