"""Pipeline-stage scripts (Stages 1, 3, 6) and design-system generators.

Modules:
- ``probe`` — Stage 1: site reconnaissance (HEAD/GET, framework detection, CSP)
- ``post_process`` — Stage 3: asset audit, scroll-fix strip, base64 inline
- ``validate`` — Stage 6: data-driven coverage scorecard, asset-ref check,
  placeholder grep, WCAG contrast pass
- ``inventory`` — design-system inventory extractor (single-script style)
- ``generate_design_system_v{1,2}`` — design-system HTML showcase generators
"""
