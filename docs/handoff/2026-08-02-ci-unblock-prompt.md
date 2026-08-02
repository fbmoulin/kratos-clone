# Resumption prompt — kratos-clone, post CI unblock (2026-08-02)

> Paste the block below into a fresh session. It is self-contained: it depends on nothing
> from the conversation that produced it.

---

```
Leia primeiro: /home/fbmoulin/Website-Downloader/docs/handoff/2026-08-02-ci-unblock.md

Projeto: fbmoulin/kratos-clone (clonador de sites SPA, Flask + Playwright, repo PÚBLICO).
Checkout local: ~/Website-Downloader, branch main.

ANTES DE QUALQUER COISA, RE-MEÇA — os números abaixo são de 2026-08-02 ~06:55 -03 e
envelhecem sozinhos. Trate cada um como pista datada, não como fato:

  git -C ~/Website-Downloader status -sb && git -C ~/Website-Downloader log --oneline -5
  gh pr list -R fbmoulin/kratos-clone
  cd ~/Website-Downloader && uv sync --locked --group dev && uv run --frozen pytest -q

Estado medido em 2026-08-02 ~07:00: main em bf85066, árvore limpa (só AGENTS.md untracked),
358 passed / 3 skipped, mypy strict limpo, CI 9/9 verde, pip-audit sem vulnerabilidades,
0 alertas do dependabot, 3 PRs abertos (#73, #74, #75 — dependabot, abertos 09:55 UTC).

🔴 ARMADILHA RECORRENTE — o PR de `pydantic-core`. O #73 JÁ FOI FECHADO pelo Felipe, mas
ELE VOLTA. Quando voltar (1 arquivo, requirements.txt, +1/-1 — parece inofensivo):
NÃO MERGEIE. Sobe pydantic-core para 2.47.0 sem tocar o uv.lock, mas o pydantic 2.13.4
declara pydantic-core==2.46.4 como pin EXATO ⇒ `pip install -r` dá ResolutionImpossible e
o build do Docker quebra. NÃO É TEÓRICO: o PR #43, com assinatura IDÊNTICA, foi MERGEADO e
quebrou o build; o #48 consertou. Já apareceu 4× (#43 merged, #53, #73, e a próxima).
⚠️ Fechar NÃO impede o retorno — o próprio dependabot avisa isso no PR.
❌ NÃO tente "subir o pydantic p/ puxar um core compatível": MEDIDO, não funciona —
   2.13.4 é a ÚLTIMA release e é ela que pina o core em 2.46.4.
❌ NÃO use scripts/relock.sh: não há drift a reconciliar, o estado pedido é INALCANÇÁVEL.
❌ NÃO ponha `ignore` amplo no pydantic-core: `ignore` também suprime SECURITY updates
   (confirmado na doc do GitHub) ⇒ criaria ponto cego permanente para CVE.
✅ Saídas boas: (a) apagar o requirements.txt e o Dockerfile instalar do uv.lock — é a
   causa raiz (artefato gerado que PARECE manifesto) e era o 1º item dos "Known deferrals"
   do plano; (b) não fazer nada e fechar quando aparecer — a guarda pega sempre.
ℹ️ Sem pressa de segurança: 0 advisories em pydantic/pydantic-core, pip-audit limpo.
#74 (structlog 25.5→26.1, MAJOR) e #75 (types-requests, dev) estavam CLEAN, 9/9 verdes.

▶ O trabalho de CI terminou e está mergeado. Fora o #73, nada bloqueia neste repo.

▶ O MAIOR ITEM VIVO ESTÁ FORA DESTE REPO: PII dentro dos arquivos de memória do Claude
Code (~/.claude/projects/*/memory/). Medido em 02/08: 8 arquivos com número CNJ real; um
deles tem tabela de 6 processos do TJES com NOME COMPLETO DAS PARTES, placas, valores e a
decisão recomendada; outro identifica uma CRIANÇA DE 6 ANOS com TEA/TDAH pelo nome.
Nunca foram varridos porque `projects/` sempre esteve no .gitignore, logo nunca foi repo.
🔴 A API key do Qdrant Cloud foi REDIGIDA mas NÃO ROTACIONADA — só o Felipe faz isso
(dashboard do Qdrant: criar nova → atualizar consumidores → revogar a velha).
Detalhe e comandos:
~/.claude/projects/-home-fbmoulin/memory/reference_pii-inside-the-memory-files-2026-08-02.md

Opcionais neste repo, em ordem: (1) ampliar o escopo do ruff para personalize/ e tests/
(ambos limpos hoje — mudar duas linhas `run:` do job lint deve passar de primeira);
(2) apagar as 4 branches remotas já mergeadas (fix/bs4-find_all-overloads,
ci/pin-jobs-to-lockfile, feat/health-build-sha, docs/relock-name-transitives-not-directs);
(3) zero métricas/tracing; (4) actions/checkout@v7 ainda em tag mutável. Tudo em TODO.md.

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
11. NÃO versionar ~/.claude/projects/*/memory/ enquanto houver a PII acima. A regra
    `projects/` no .gitignore está certa pelo alvo real: 1.221 transcripts .jsonl contêm
    CNJ (1,8 GB). Quando limpar, des-ignorar só */memory/ com pii-sweep como pre-commit.

JÁ TENTADO E DESCARTADO — não repita:

- "@dependabot rebase" e "@dependabot recreate" NÃO consertam a divergência da guarda
  requirements.txt ⇄ uv.lock. O recreate reproduziu a mesma lacuna de 12 pacotes. É
  comportamento sistemático do ecossistema uv do dependabot.
- scripts/relock.sh com os pacotes DIRETOS faz overshoot: --upgrade-package resolve para a
  ÚLTIMA versão permitida, não a do PR. Nomeie os TRANSITIVOS que o diff da guarda lista.
  (O header do script e o dependabot.yml já dizem isso desde o PR #72.)
- "uv export" sozinho para consertar a guarda REBAIXA 12 transitivos, certifi incluído.

ARMADILHAS ATIVAS:

- 🔴 Renomear o job de mypy QUEBRA a main. O name: declarado tem 114 chars; o GitHub trunca
  nomes de check-run em 98. O contexto do ruleset é a string TRUNCADA. Contexto que não casa
  não dá erro — cria um required check que nunca chega e todo PR bloqueia para sempre.
- 🔴 AGENTS.md é untracked em cópia única. NUNCA `git add -A` ou `git add .` neste checkout.
- ⚠️ Todo PR de produção do dependabot chega com a guarda de drift vermelha. É esperado.
- ⚠️ bandit imprime "High: 10" na coluna de CONFIANÇA, não de severidade (exit 0).
- ⚠️ No Bash do Claude Code, grep e find são funções-sombra com heap do V8 — já travaram
  este WSL duas vezes. Use `command grep -r` ou `rg` em busca recursiva.
- ⚠️ downloader.py é legado do upstream e está FORA do escopo do ruff no CI de propósito.
- ⚠️ Diretórios em ~/.claude/projects/ começam com "-", então `cp ./"$d"/*.md` precisa do
  ./ — sem ele o cp lê o caminho como flag e falha em silêncio.

⛔ NÃO EXECUTE ~/claudedocs/kratos-clone-audit-2026-08-01/PLAN-unblock-ci-2026-08-02.md nem
o PROMPT-RETOMADA-2026-08-02.md daquele diretório. Ambos foram CUMPRIDOS em 02/08. A cópia
do plano no repo (docs/superpowers/plans/) traz no topo a tabela das 5 verificações dele
que a execução refutou — leia essa tabela antes de reaproveitar qualquer sonda de lá.
```
