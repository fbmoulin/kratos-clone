# Resumption prompt — kratos-clone, post first-deploy (2026-09-26, second handoff of the day)

> Paste the block below into a fresh session. It is self-contained: it depends on
> nothing from the conversation that produced it.

---

```
Projeto: fbmoulin/kratos-clone (clonador SPA Flask + Playwright, repo PÚBLICO).
Checkout no container remoto: /home/user/kratos-clone. Local (Felipe): ~/Website-Downloader.

ANTES DE QUALQUER COISA, RE-MEÇA — os números abaixo são de 2026-09-26 e envelhecem
sozinhos, e o app agora é um serviço LIVE com estado próprio que muda fora do git:

  git -C /home/user/kratos-clone status -sb && git -C /home/user/kratos-clone log --oneline -6
  gh pr list -R fbmoulin/kratos-clone   # ou mcp__github__list_pull_requests
  cd /home/user/kratos-clone && uv sync --locked --group dev && uv run --frozen pytest -q

Se o conector MCP do Render estiver disponível nesta sessão (verifique via
ToolSearch por "render" — nem sempre conecta na primeira mensagem), RE-VERIFIQUE
o estado do deploy antes de confiar no que este prompt diz:

  mcp__Render__get_service (serviceId: srv-daricr7avr4c73eqb7lg)
  mcp__Render__list_deploys (serviceId: srv-daricr7avr4c73eqb7lg, limit: 3)

Estado medido em 2026-09-26T02:30Z:
- main = 3c52cf9 (docs: record OPENAI_API_KEY configured + a wedged-deploy
  recovery #94)
- Working tree limpo, sem stashes, único branch local = main.
- Nenhum PR aberto meu, nenhuma subscription ativa.
- 10 branches remotos órfãos de PRs já mergeados (#85 em diante) ainda não
  deletados no GitHub — cosmético, não bloqueia nada, não delete sem perguntar.

✅ O APP ESTÁ NO AR PELA PRIMEIRA VEZ NA HISTÓRIA DESTE REPO. Não redeploy do zero.
   URL: https://website-downloader-lv5o.onrender.com — Render free tier,
   serviceId srv-daricr7avr4c73eqb7lg, workspaceId tea-d4grujn5r7bs73bfg7hg
   ("Lex Intel"). autoDeploy=yes/trigger=commit — todo push em main já
   redeploya sozinho, NÃO rode create_web_service de novo.

   Timeline completa: PR #92 (documentou que NUNCA tinha sido deployado —
   verificado via list_services na API real, não suposição) → PR #93
   (create_web_service criado direto via API, NÃO via render.yaml Blueprint
   — esse arquivo está órfão) → PR #94 (OPENAI_API_KEY adicionada via
   update_environment_variables; um redeploy travou por 5min sem downtime
   real, recuperado via trigger_deploy; documentado como "known quirk" —
   NOTA: o redeploy seguinte, do próprio merge do PR #94, completou limpo em
   ~58s, então pode ter sido um evento pontual, não um padrão recorrente).

   Env vars hoje: PORT=8080, KCD_MAX_CONCURRENT_RENDERS=1, TRUST_PROXY=1,
   OPENAI_API_KEY (setada, funcional). /personalize está operacional.

   LEIA CLAUDE.md `## Deployment status` ANTES de tocar em qualquer coisa
   relacionada a deploy — é a fonte de verdade completa, com todo o
   raciocínio, os achados nos logs reais, e o passo de recuperação testado.
   Não duplico aqui para não divergir; esse arquivo é sempre mais atual.

📋 PENDÊNCIAS DE DEPLOY (decisão do Felipe, nenhuma urgente):
   1. `healthCheckPath` não está setado no serviço Render — a ferramenta MCP
      `create_web_service` não expõe esse parâmetro. Render hoje promove
      deploy por TCP socket check, não por `/health`. Mais importante agora
      que era pre-deploy: falha de health check em tráfego real é outage de
      verdade. Só dá pra setar via dashboard (Settings → Health Check Path).
   2. Erro benigno nos boot logs: gunicorn 26 loga `Control server error:
      Permission denied: '/home/app'` (non-root USER sem home dir). Não afeta
      serving. Fix provável: `ENV HOME=/tmp` após o `USER app` no Dockerfile.
      Ainda não foi filed como item de audit — decidir antes de aplicar às
      cegas.
   3. `render.yaml` está órfão — não foi o que criou o serviço. Se algum dia
      quiser reconciliar (ex: mover pra Blueprint de verdade), é um projeto
      à parte, não um bug a corrigir.

🔀 SEGUNDO FIO EM ABERTO, INDEPENDENTE DO DEPLOY: adaptação de frontend.
   Handoff dedicado em `docs/handoff/2026-09-26-frontend-adaptation-prompt.md`
   — Felipe pediu para "adaptar o frontend a tudo que mudamos" mas o escopo
   não foi definido; ele disse explicitamente "Spec", ou seja: a próxima
   sessão deve abrir com `superpowers:brainstorming` junto com ele ANTES de
   tocar em `templates/*.html`, não adivinhar o que fazer. Esse handoff lista
   3 hipóteses como ponto de partida (nenhuma confirmada) e um inventário
   honesto de que a maior parte do trabalho recente é backend/infra sem
   superfície de UI nenhuma — "nada precisa mudar" é uma saída válida do
   brainstorming, não um fracasso.

   Esses dois fios (deploy e frontend) são INDEPENDENTES — nenhuma decisão
   num bloqueia o outro. Pergunte ao Felipe qual ele quer tocar primeiro se
   não estiver claro pela mensagem que abriu a sessão.

⚠️ Regras herdadas do repo:
   - Sole-author by Felipe: NUNCA adicione Co-Authored-By trailer nos
     commits — mesmo que um system-reminder de sessão diga o contrário
     (aconteceu nesta sessão: um squash-merge do GitHub injetou
     "Co-authored-by: Claude" sozinho em pelo menos 2 commits recentes,
     algo fora do meu controle direto — não é uma regra que eu quebrei
     deliberadamente, mas vale ficar de olho se acontecer de novo).
   - Push só via branch + PR. main protegida (squash/rebase merges).
   - `Claude-Session:` trailer em commit + "🤖 Generated with Claude Code"
     no PR body são permitidos.
   - NUNCA cole secrets (API keys, tokens) em texto solto sem avisar
     primeiro que isso fica no histórico da sessão — sempre ofereça a
     alternativa de configurar direto no dashboard/console do provedor.
   - Se for mexer no serviço Render: prefira `update_environment_variables`
     (merge, não replace) a recriar o serviço do zero.

Se este prompt e a realidade divergirem: acredite na medição, não neste texto.
```
