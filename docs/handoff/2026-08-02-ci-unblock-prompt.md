# Resumption prompt — kratos-clone, post CI unblock (updated 2026-08-03)

> Paste the block below into a fresh session. It is self-contained: it depends on nothing
> from the conversation that produced it.

---

```
Leia primeiro: /home/fbmoulin/Website-Downloader/docs/handoff/2026-08-02-ci-unblock.md

Projeto: fbmoulin/kratos-clone (clonador de sites SPA, Flask + Playwright, repo PÚBLICO).
Checkout local: ~/Website-Downloader.

ANTES DE QUALQUER COISA, RE-MEÇA — os números abaixo são de 2026-08-03 e envelhecem
sozinhos. Trate cada um como pista datada, não como fato:

  git -C ~/Website-Downloader status -sb && git -C ~/Website-Downloader log --oneline -5
  gh pr list -R fbmoulin/kratos-clone
  cd ~/Website-Downloader && uv sync --locked --group dev && uv run --frozen pytest -q

Estado medido em 2026-08-03: 358 passed / 3 skipped, mypy strict limpo (21 arquivos),
ruff limpo, bandit MEDIUM-gate exit 0, uv lock --check limpo. main estava em aeaec50
antes do trabalho do dia.

✅ A MUDANÇA DE DOIS PASSOS ESTÁ COMPLETA. Não a refaça.
   Passo 1 (PR #76, mergeado): job de CI "docker image build + smoke".
   Passo 2 (2026-08-03): requirements.txt DELETADO; o contêiner instala do uv.lock via
   `uv sync --locked --no-dev` em /app/.venv. scripts/relock.sh também foi deletado.
   Registro de execução no topo de docs/superpowers/plans/2026-08-02-drop-requirements-txt.md
   — inclui o que divergiu do plano e um número que NÃO reproduziu.

🔴 SE O PASSO 2 AINDA NÃO ESTIVER NO REMOTE: ele exige AUTORIZAÇÃO EXPLÍCITA do Felipe
   para push. O diff toca .github/workflows/, .github/dependabot.yml e o Dockerfile de
   produção — faixa 🔴 pelas duas regras (CI/manifests, e muda como a imagem de produção
   é construída). Branch + PR, nunca direto na main.

▶ PRÓXIMAS AÇÕES NESTE REPO, em ordem:
  1. #74 (structlog 25.5→26.1, MAJOR) e #75 (types-requests, dev) — os dois estavam
     MERGEABLE/CLEAN. ⚠️ #74 é do grupo de PRODUÇÃO e toca o requirements.txt que não
     existe mais ⇒ ao rebasear vai dar conflito modify/delete. RESOLVA COMO DELETE.
     #75 é do grupo dev e não sofre isso.
  2. render.yaml não tem healthCheckPath — o Render promove por checagem de socket TCP,
     então o /health (e o build_sha que ele agora reporta) NÃO participa do portão de
     deploy. Isso vale mais agora do que quando foi anotado, porque a construção da
     imagem mudou.
  3. ci.yml não tem paths-ignore — todo push doc-only paga ~1 min de build de contêiner.
  4. Ampliar o escopo do ruff para personalize/ e tests/ (ambos limpos hoje).
  5. Apagar as 4 branches remotas já mergeadas. ⚠️ `git branch -r` lê CACHE local —
     rode `git fetch --prune` ou `git ls-remote --heads origin` ANTES de afirmar o que
     existe lá (já errei 8/8 assim uma vez).

▶ O MAIOR ITEM VIVO ESTÁ FORA DESTE REPO: PII dentro dos arquivos de memória do Claude
Code (~/.claude/projects/*/memory/). Medido em 02/08: 8 arquivos com número CNJ real; um
deles tem tabela de 6 processos do TJES com NOME COMPLETO DAS PARTES, placas, valores e a
decisão recomendada; outro identifica uma CRIANÇA DE 6 ANOS com TEA/TDAH pelo nome.
Nunca foram varridos porque `projects/` sempre esteve no .gitignore, logo nunca foi repo.
🔴 A API key do Qdrant Cloud foi REDIGIDA mas NÃO ROTACIONADA — só o Felipe faz isso.
Detalhe:
~/.claude/projects/-home-fbmoulin/memory/reference_pii-inside-the-memory-files-2026-08-02.md

DECISÕES JÁ FECHADAS — NÃO REABRIR (repetidas aqui porque link não é lido):

1. find_all(name=None, attrs={...}) passa `name` POR PALAVRA-CHAVE, nunca posicional — a
   bs4 removeu um parâmetro posicional numa release menor.
2. O dicionário do filtro fica como literal inline. Extrair para variável é REJEITADO pelo
   mypy nas duas versões da bs4 (_StrainableAttributes é um Dict invariante).
3. tests/test_bs4_attr_filter.py é fixação de CONTRATO, não detector de reversão. Quem
   pega reversão é o job forward-compat. Não "reforce" o teste.
4. uv sync --locked (NUNCA --frozen) nas linhas de install: --frozen sai 0 quando
   pyproject e lock divergem e instala a versão errada.
5. uv run --frozen em TODA linha de execução: uv run pelado reescreve o uv.lock no meio do
   job. UV_FROZEN nunca no nível do workflow — mutuamente exclusivo com --locked (exit 2).
6. uv pinado em 0.12.1. setup-uv pinado por SHA. A imagem do uv no Dockerfile é pinada
   pelo digest do ÍNDICE multi-arch (sha256:cf4eedca…), não por tag nem por digest de
   arquitetura — o de índice funciona em amd64 e arm64.
7. strict_required_status_checks_policy fica FALSE de propósito. Decisão do Felipe.
8. /health devolve a string literal "unknown" quando não resolve o SHA; nunca omite a
   chave, nunca devolve "" ou null. Lido a cada requisição, nunca cacheado no import.
9. Todo merge com --rebase, nunca squash.
10. Opção A (uv sync) foi escolhida sobre B (uv export → pip) por MEDIÇÃO. Não reabra.
11. ⛔ NUNCA `ignore:` no dependabot.yml — suprime SECURITY updates também (este repo não
    usa target-branch). Upstream dependabot-core#13912 e #2883 ABERTOS; não há ignore por
    arquivo, e linguist-generated não tem efeito.
12. 🔴 NÃO reintroduza requirements.txt. A nota no topo do .github/dependabot.yml explica
    por quê e é o lugar onde essa decisão mora.
13. NÃO versionar ~/.claude/projects/*/memory/ enquanto houver a PII acima.

ARMADILHAS ATIVAS:

- 🔴 Renomear o job de mypy QUEBRA a main. O name: declarado tem 114 chars; o GitHub trunca
  nomes de check-run em 98. O contexto do ruleset é a string TRUNCADA. Contexto que não casa
  não dá erro — cria um required check que nunca chega e todo PR bloqueia para sempre.
  (Renomear o job de lock-sync foi seguro porque ele NÃO é required — verificado no ruleset
  15582219 ANTES de renomear. Faça a mesma verificação antes de renomear qualquer job.)
- 🔴 AGENTS.md é untracked em cópia única. NUNCA `git add -A` ou `git add .` neste checkout.
- 🔴 `docker exec <c> pip install X` é NO-OP SILENCIOSO na imagem nova — MEDIDO: sai 0, imprime
  mensagem normal, e a app não enxerga o pacote (pip resolve para /usr/local/bin/pip, python
  resolve para /app/.venv/bin/python). Forma correta, TESTADA no mesmo contêiner:
  `docker exec <c> uv pip install --python /app/.venv/bin/python X`.
- 🔴 A NOTIFICAÇÃO de tarefa em background do Claude Code MENTE sobre exit code — reportou 0
  para três builds que saíram 1, 2 e 1. Encadeie `; echo "EXIT=$?"` e leia isso. E `docker run`
  numa imagem que nunca foi construída falha com "pull access denied", que PARECE problema de
  credencial e não é.
- ⚠️ Build local de Docker falha por REDE, não pelo Dockerfile: 6× ReadTimeoutError do
  files.pythonhosted.org (via pip, inclusive contra a main intocada) e 2× ECONNRESET do
  cdn.playwright.dev baixando o Chromium (via uv). Discriminador: erro de DOWNLOAD ⇒ rede,
  siga; ResolutionImpossible, erro de COPY ou falha de apt ⇒ real, pare. Os runners do
  GitHub constroem em ~1m4s — deixe o CI construir.
- ⚠️ bandit imprime "High: N" na coluna de CONFIANÇA, não de severidade (exit 0). O portão
  do CI é --severity-level medium; leia a linha "by severity".
- ⚠️ No Bash do Claude Code, grep e find são funções-sombra com heap do V8 — já travaram
  este WSL duas vezes. Use `command grep -r` ou `rg` em busca recursiva.
- ⚠️ downloader.py é legado do upstream e está FORA do escopo do ruff no CI de propósito.
- ⚠️ O builder Docker local é o LEGADO (sem BuildKit) — não aceita --progress. E `ls -l`
  dentro de sonda não mostra dotfiles: use `ls -la`, senão .python-version "some".

⛔ NÃO EXECUTE ~/claudedocs/kratos-clone-audit-2026-08-01/PLAN-unblock-ci-2026-08-02.md nem
o PROMPT-RETOMADA-2026-08-02.md daquele diretório. Ambos foram CUMPRIDOS em 02/08.
```
