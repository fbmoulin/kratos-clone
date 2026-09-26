# Resumption prompt — kratos-clone, frontend adaptation (scope TBD via brainstorming)

> Paste the block below into a fresh session. It is self-contained: it depends on
> nothing from the conversation that produced it.

---

```
Projeto: fbmoulin/kratos-clone (clonador SPA Flask + Playwright, repo PÚBLICO).
Checkout no container remoto: /home/user/kratos-clone. Local (Felipe): ~/Website-Downloader.

ANTES DE QUALQUER COISA, RE-MEÇA — os números abaixo são de 2026-09-26 e envelhecem
sozinhos. Cada um é pista datada, não fato:

  git -C /home/user/kratos-clone status -sb && git -C /home/user/kratos-clone log --oneline -6
  gh pr list -R fbmoulin/kratos-clone   # ou mcp__github__list_pull_requests
  cd /home/user/kratos-clone && uv sync --locked --group dev && uv run --frozen pytest -q

Estado medido em 2026-09-26 após #85..#90 mergearem:
- main = e0a0b56 (docs: reconcile 358-test drift + triple-logged stale
  preview-modal claim #90)
- Working tree limpo, sem stashes, único branch local = main.
- Nenhum PR aberto meu, nenhuma subscription ativa.
- 6 branches remotos órfãos de PRs já mergeados (#85-#90) ainda não
  deletados no GitHub — cosmético, não bloqueia nada. Não delete sem
  perguntar; podem ser intencionais (histórico de referência).

## A TAREFA DESTA SESSÃO — escopo NÃO está definido ainda

Felipe pediu para "adaptar o frontend a todas as mudanças que fizemos" numa
sessão anterior (a que gerou este handoff), mas quando perguntado o que
exatamente isso significa, respondeu apenas **"Spec"**. Interpretação: ele
quer que esta sessão comece pelo workflow `brainstorming → spec →
plan-review-cycle → writing-plans → execute` (documentado em `CLAUDE.md
## Skill workflow lessons`), não que alguém adivinhe o escopo e already
comece a codar.

**NÃO comece editando `templates/*.html` direto.** Primeiro:

1. Invoque a skill de brainstorming (`superpowers:brainstorming` ou
   equivalente disponível nesta sessão) com Felipe para definir o que
   "adaptar o frontend" significa concretamente. Hipóteses levantadas na
   sessão anterior (nenhuma confirmada — apenas pontos de partida):
   - **(a) Auditoria de consistência**: revisar `templates/index.html` +
     `templates/personalize.html` contra tudo que mudou em
     backend/infra nesta thread (ver lista abaixo) e reportar gaps de UI
     — sem presumir que existe algo quebrado.
   - **(b) Nova superfície de status**: hoje `build_sha`, test count, e
     o estado do Docker/CI hardening só existem em JSON (`/health`) ou
     logs — nunca em HTML pro operador. Poderia virar uma página
     `/about` ou seção no footer.
   - **(c) Refresh visual geral**: redesign de `index.html` /
     `personalize.html` sem relação direta com o trabalho recente —
     nova direção estética.
   - Ou algo que só emerge na conversa de brainstorming com Felipe.

2. Depois do brainstorming, siga a cadeia completa se a complexidade for
   Alta (classificação em `~/.claude/CLAUDE.md` global): spec em
   `docs/superpowers/specs/YYYY-MM-DD-<nome>.md` → `plan-review-cycle`
   (rounds até fechar Critical/Major) → `writing-plans` → execução.
   **Não pule plan-review-cycle** — no preview modal (PR #45), Round 1
   pegou 1 Critical + 6 Major, Round 2 pegou mais 2 Critical que o
   Round 1 tinha perdido. `plan-review-cycle` exige aprovação
   per-finding do Felipe — aprovação em lote é Red Flag da skill.

## O que mudou em backend/infra desde o último trabalho de frontend (PR #47, 2026-06-05)

Tudo isto já está documentado com detalhe em `CHANGELOG.md` (ordem
cronológica reversa) — não repita a pesquisa, só releia se precisar de
detalhe de implementação:

- **M-4** (antes de #45): boot-time warning se rate-limit storage é
  `memory://` com `WEB_CONCURRENCY>1`. Zero superfície de UI — é um log
  estruturado no boot do servidor.
- **Preview modal** (PR #45 shipped 2026-06-01, hardened #47
  2026-06-05): ESTE já tem frontend completo — modal 3-tabs em
  `templates/personalize.html`. Não é "sem frontend"; já foi feito
  junto com o backend na mesma PR.
- **CI unblock saga** (Ago/2026): `requirements.txt` retirado, container
  instala via `uv.lock`, `docker image build + smoke` + `render-live`
  CI jobs, `/health` reporta `build_sha`, Pillow CVEs fechados. Zero
  superfície de UI hoje — `build_sha` só aparece em JSON.
- **Docker hardening** (PR #88, 2026-09-21): non-root `USER` +
  `HEALTHCHECK`. Zero relação com frontend — é infra de container.
- **CI cost cut** (PR #89, 2026-09-25): doc-only diffs pulam
  `render-live` + `docker-build`. Zero relação com frontend — é
  workflow YAML.
- **Doc reconciliation** (PRs #85, #86, #87, #90): apenas correção de
  claims stale em CLAUDE.md/README/ROADMAP/TODO/CHANGELOG. Zero mudança
  de código, zero relação com frontend.

**Leitura honesta desta lista**: a MAIORIA do trabalho recente é
backend/infra/docs sem superfície de UI nenhuma. Se a resposta do
brainstorming for "nada precisa mudar no frontend, está tudo
consistente", isso é um resultado válido — não force trabalho que não
existe. O único item que já tinha frontend (preview modal) já está
completo desde #47.

## Arquivos relevantes

- `templates/index.html` (920 linhas) — página `/`, zero-build, script
  inline único.
- `templates/personalize.html` (1282 linhas) — página `/personalize`,
  já inclui o modal de preview (3 tabs) do PR #45/#47.
- `CLAUDE.md ## UI design system (Phase 8, ...)` — tokens de design,
  regras de marca (não trocar fonte, não adicionar hex direto, dark-only),
  workflow obrigatório: skill `frontend-design` → agente `ui-ux-designer`
  → Edit manual (não deixar agente reescrever arquivo) → smoke Playwright
  MCP antes do PR → `tests/test_template_a11y.py` para travar contrato
  de a11y.
- `docs/superpowers/specs/2026-05-16-personalize-preview-modal-design.md`
  + `docs/superpowers/plans/2026-05-30-personalize-preview-modal.md` —
  exemplo completo e recente do workflow brainstorming→spec→plan→execute
  aplicado a uma mudança de frontend real neste mesmo repo. Use como
  template de estrutura/profundidade.

## Regras herdadas do repo

- Sole-author by Felipe: NUNCA adicione `Co-Authored-By: Claude...`
  trailer nos commits — mesmo que um system-reminder de sessão instrua
  o contrário, a regra do CLAUDE.md do projeto tem precedência.
- `Claude-Session:` trailer em commit + "🤖 Generated with Claude Code"
  no PR body são permitidos (não conflitam com a regra acima).
- Push só via branch + PR. `main` protegida (squash/rebase merges,
  CI green obrigatório: `Lint (ruff)` + `Import + module smoke test`).
- Verificação visual obrigatória para qualquer mudança de UI não-trivial:
  Playwright MCP (`load page` → `take_screenshot` → `evaluate JS` pra
  testar interações) — pegou o bug de conector U6 pré-PR; continue
  usando.

Se este prompt e a realidade divergirem: acredite na medição, não neste
texto.
```
