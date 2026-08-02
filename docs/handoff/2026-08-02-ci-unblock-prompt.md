# Resumption prompt — kratos-clone, post CI unblock (2026-08-02)

> Paste the block below into a fresh session. It is self-contained: it depends on nothing
> from the conversation that produced it.

---

```
Leia primeiro: /home/fbmoulin/Website-Downloader/docs/handoff/2026-08-02-ci-unblock.md

Projeto: fbmoulin/kratos-clone (clonador de sites SPA, Flask + Playwright, repo PÚBLICO).
Checkout local: ~/Website-Downloader, branch main.

ANTES DE QUALQUER COISA, RE-MEÇA — os números abaixo são de 2026-08-02 ~06:30 -03 e
envelhecem sozinhos. Trate cada um como pista datada, não como fato:

  git -C ~/Website-Downloader status -sb && git -C ~/Website-Downloader log --oneline -5
  gh pr list -R fbmoulin/kratos-clone
  cd ~/Website-Downloader && uv sync --locked --group dev && uv run --frozen pytest -q

Estado medido em 2026-08-02: main em dfff995, árvore limpa (só AGENTS.md untracked),
358 passed / 3 skipped, mypy strict limpo, CI 9/9 verde, pip-audit sem vulnerabilidades,
0 alertas do dependabot, 1 PR aberto (#72).

▶ PRÓXIMA AÇÃO: mergear o PR #72.
  gh pr merge 72 -R fbmoulin/kratos-clone --rebase
Ele está MERGEABLE/CLEAN com 9/9 verdes e é só comentários. Corrige três lugares que ainda
ensinam o comando de relock ERRADO. Ficou sem mergear apenas porque toca .github/, que na
política de push do Felipe exige autorização explícita — PERGUNTE antes de mergear.

DECISÕES JÁ FECHADAS — NÃO REABRIR (repetidas aqui porque link não é lido):

1. find_all(name=None, attrs={...}) passa `name` POR PALAVRA-CHAVE, nunca posicional — a
   bs4 removeu um parâmetro posicional numa release menor.
2. O dicionário do filtro fica como literal inline. Extrair para variável é REJEITADO pelo
   mypy nas duas versões da bs4 (_StrainableAttributes é um Dict invariante).
3. tests/test_bs4_attr_filter.py é fixação de CONTRATO, não detector de reversão — não
   importa downloader.py e a distinção name=None é invisível em runtime. Quem pega reversão
   é o job forward-compat. Não "reforce" o teste.
4. uv sync --locked (NUNCA --frozen) nas linhas de install: --frozen sai 0 quando
   pyproject e lock divergem e instala a versão errada.
5. uv run --frozen em TODA linha de execução: uv run pelado reescreve o uv.lock no meio do
   job.
6. UV_FROZEN nunca no nível do workflow — é mutuamente exclusivo com --locked (exit 2).
7. uv pinado em 0.12.1 (medido, não o fallback 0.10.12). setup-uv pinado por SHA, não tag.
8. strict_required_status_checks_policy fica FALSE de propósito — ligar obriga rebase de
   todo PR aberto do dependabot a cada push na main. Decisão do Felipe.
9. /health devolve a string literal "unknown" quando não resolve o SHA; nunca omite a
   chave, nunca devolve "" ou null. Valor em branco cai para a próxima fonte. Lido a cada
   requisição, nunca cacheado no import.
10. Todo merge com --rebase, nunca squash.

JÁ TENTADO E DESCARTADO — não repita:

- "@dependabot rebase" e "@dependabot recreate" NÃO consertam a divergência da guarda
  requirements.txt ⇄ uv.lock. O recreate reproduziu a mesma lacuna de 12 pacotes. É
  comportamento sistemático do ecossistema uv do dependabot.
- scripts/relock.sh com os pacotes DIRETOS faz overshoot: --upgrade-package resolve para a
  ÚLTIMA versão permitida, não a do PR (mediu-se openai -> 2.52.0 e playwright -> 1.62.0,
  além do que o PR declarava). Nomeie os TRANSITIVOS que o diff da guarda lista.
- "uv export" sozinho para consertar a guarda REBAIXA 12 transitivos, certifi incluído.

ARMADILHAS ATIVAS:

- 🔴 Renomear o job de mypy QUEBRA a main. O name: declarado tem 114 chars; o GitHub trunca
  nomes de check-run em 98. O contexto do ruleset é a string TRUNCADA. Contexto que não casa
  não dá erro — cria um required check que nunca chega e todo PR bloqueia para sempre.
- 🔴 AGENTS.md é untracked em cópia única. NUNCA `git add -A` ou `git add .` neste checkout.
- ⚠️ Todo PR de produção do dependabot chega com a guarda de drift vermelha. É esperado.
- ⚠️ bandit imprime "High: 10" na coluna de CONFIANÇA, não de severidade (Severity é
  Low: 10, Medium: 0, High: 0; exit 0).
- ⚠️ No Bash do Claude Code, grep e find são funções-sombra com heap do V8 — já travaram
  este WSL duas vezes. Use `command grep -r` ou `rg` em busca recursiva.
- ⚠️ downloader.py é legado do upstream e está FORA do escopo do ruff no CI de propósito.
  Seus 28 achados não são dívida nova.

EM ABERTO (não bloqueia): ampliar o escopo do ruff para personalize/ e tests/ (ambos limpos
hoje); zero métricas/tracing; actions/checkout@v7 ainda em tag mutável; limpar branches
remotas já mergeadas. Tudo em TODO.md.

⛔ NÃO EXECUTE ~/claudedocs/kratos-clone-audit-2026-08-01/PLAN-unblock-ci-2026-08-02.md nem
o PROMPT-RETOMADA-2026-08-02.md daquele diretório. Ambos foram CUMPRIDOS em 02/08. A cópia
do plano no repo (docs/superpowers/plans/) traz no topo a tabela das 5 verificações dele
que a execução refutou — leia essa tabela antes de reaproveitar qualquer sonda de lá.
```
