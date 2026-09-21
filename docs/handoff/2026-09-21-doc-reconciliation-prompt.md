# Resumption prompt — kratos-clone, post doc reconciliation (2026-09-21)

> Paste the block below into a fresh session. It is self-contained: it depends on
> nothing from the conversation that produced it.

---

```
Projeto: fbmoulin/kratos-clone (clonador SPA Flask + Playwright, repo PÚBLICO).
Checkout no container remoto: /home/user/kratos-clone. Local (Felipe): ~/Website-Downloader.

ANTES DE QUALQUER COISA, RE-MEÇA — os números abaixo são de 2026-09-21 e envelhecem
sozinhos. Cada um é pista datada, não fato:

  git -C /home/user/kratos-clone status -sb && git -C /home/user/kratos-clone log --oneline -5
  gh pr list -R fbmoulin/kratos-clone   # ou mcp__github__list_pull_requests
  cd /home/user/kratos-clone && uv sync --locked --group dev && uv run --frozen pytest -q

Estado medido em 2026-09-21T09:30Z após #85+#86+#87 mergearem, e depois
atualizado por esta mesma rodada que fecha N-6+N-7 no Dockerfile:
- main pré-este-PR = a712a0c (docs handoff #87). Após merge deste PR,
  main = <sha do squash de N-6+N-7>. Re-meça — o número acima envelhece.
- Working tree limpo, sem stashes.
- Nenhum PR aberto meu, nenhuma subscription ativa (pressupondo merge feito).

✅ RECONCILIAÇÃO DOC-ONLY COMPLETA. Não a refaça.
   #85 (480e43d): substituiu a seção "Feature — feat/personalize-preview-modal branch
     (IMPLEMENTED 2026-05-31, NOT pushed)" de CLAUDE.md por descrição factual do
     preview modal SHIPPED via PR #45 (feature, 2026-06-01) + #47 (5 hardening
     fixes, 2026-06-05) + #55 (KCD_MAX_CONCURRENT_RENDERS=1 pin em Render).
     Também retitulou "## Skill workflow lessons (this session)" para atribuir
     concretamente aos PRs #45/#47.
   #86 (0a567cd): corrigiu 2 outras stale claims:
     (a) CLAUDE.md warning "Generators have hardcoded NexusFlow indices — IndexError
         on arbitrary sites. Phase 2 fixes this." → FACTUALMENTE ERRADO. O P1-C fix
         (find_button_by_classes em scripts/generate_design_system_v2.py:501) já
         landed e todo inv[…] no arquivo é defensivo (min(), .get(), slicing).
         Substituído por statement dos limites RESIDUAIS (site name "NexusFlow"
         hardcoded em ~4 sites de copy; find_button_by_classes usa fragmentos
         de classes Tailwind).
     (b) PRE_DEPLOY_AUDIT §N-4 (No CORS/CSRF) DEFERRED → PARTIAL. O preview endpoint
         em app.py:858-902 (via PR #45/#47) tem same-host CORS explícito, CSP
         content-type-aware, X-Content-Type-Options: nosniff, Cache-Control: no-cache
         em .html. NÃO é uma flask-cors allowlist geral — POST endpoints
         (/api/personalize/*, /download, /api/client-errors) continuam uncovered.

📋 BACKLOG ATUAL (verificado 2026-09-21):
   ✅ Todos P1/P2 (13+12 findings) fechados
   ✅ M-1..M-5 do pre-deploy audit: fechados ou partial (M-5 launch-args)
   ✅ N-6 (Dockerfile HEALTHCHECK) + N-7 (non-root USER) fechados no mesmo PR
      que shipou este handoff atualizado. UID/GID 65532 (distroless nonroot
      convention); Playwright browsers rehomed p/ /opt/ms-playwright via
      PLAYWRIGHT_BROWSERS_PATH SET ANTES do install pra USER switch não cegar
      o Chromium; wget --spider contra /health (wget já vinha do apt layer).
   🟡 N-4 PARTIAL: preview coberto; POST endpoints ainda sem CORS/CSRF geral
   ⏳ N-5, N-8, N-9 (3 MINOR fully deferred), inalterados de 2026-05:
      - N-5: janitor Thread daemon=True em app.py:289 (idempotent rmtree mitiga)
      - N-8: Procfile dead code sob `env: docker` no render.yaml (harmless)
      - N-9: downloader.py excluído do bandit CI scope (1 High unannotated: md5
             para asset filename hashing)
   ⏳ ~13 P3 em docs/AUDIT.md (informational: SHA-pinning, unused fields, upper-bounds)
   🟡 Generator ainda hardcoded "NexusFlow" em título/section descriptors/footer URL
      (não bloqueia captura — só cosmético/design-system output). Um safe_int_env
      helper compartilhado com kratos_clone/capture.py também é candidato de
      refactor (não urgente; ver PR #42 review thread #6 histórico).

▶ CANDIDATOS PRÓXIMOS, sem prioridade absoluta (perguntar ao Felipe):
   1. N-4 completo: flask-cors com allowlist restrita nos POST endpoints. Requer
      decisão de política — quem consome fora do same-origin? Hoje: só o próprio
      Flask serve o formulário. Ganho = defesa se algum dia mudar.
   2. Generator branding parameterization: dropar "NexusFlow" hardcoded (~4 sites),
      aceitar `--site-name` CLI arg + inferir de inv["meta"]["title"] com fallback.
      Baixo risco, doc-only-adjacent.
   3. safe_int_env helper (extract from app.py; aplicar em kratos_clone/capture.py
      onde vários `int(os.getenv(KCD_*))` são unguarded). Vem do backlog PR #42
      review; low priority porque KCD_* são operator-set, não platform-set.
   4. render.yaml healthCheckPath (herdado do handoff anterior de 2026-08-03) —
      /health hoje reporta build_sha E o novo HEALTHCHECK do container também
      bate nele, mas o Render ainda promove por probe externa que não passa
      por esse path a menos que healthCheckPath seja setado.
   5. ci.yml paths-ignore para docs-only pushes (~1 min por PR doc-only hoje).

📖 LEITURA OBRIGATÓRIA antes de tocar código:
   - /home/user/kratos-clone/CLAUDE.md (agora factualmente correto pós-#85/#86)
   - docs/PRE_DEPLOY_AUDIT_2026-05-10.md (para N-4..N-9 detalhados)
   - docs/handoff/2026-08-02-ci-unblock-prompt.md (item 5 de "PRÓXIMAS AÇÕES" lá
     — render.yaml healthCheckPath — ainda vale)

⚠️ Regras herdadas do repo:
   - Sole-author by Felipe: NUNCA adicione Co-Authored-By trailer nos commits.
   - Push só via branch + PR. main protegida (squash/rebase merges).
   - Attribution Claude-Session em commit trailer + "🤖 Generated with Claude Code"
     no PR body é permitido (não conflita com sole-author rule que só cobre
     Co-Authored-By).

Se este prompt e a realidade divergirem: acredite na medição, não neste texto.
```
