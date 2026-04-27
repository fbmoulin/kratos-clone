"""Personalization pipeline (Phase 4).

Patch-based personalization: takes a captured site + extracted design system
+ a user brand brief, produces personalized HTML via OpenAI Responses API
(structured outputs) and gpt-image-1.

Entry points:
- ``extract_slots`` — Step 4 deterministic slot extraction
- ``apply_personalization`` — Step 7 BS4 patch applier
- ``OpenAIBrandClient`` — Steps 2/5/6 LLM calls with budget guard
- ``run_pipeline`` — sync orchestrator (Flask / CLI)
- ``arun_pipeline`` — async orchestrator (FastAPI / async tests)

See ``docs/PERSONALIZATION.md`` for the full architectural spec.
"""

__version__ = "0.1.0"
