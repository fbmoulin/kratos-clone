# 🚂 Deploy no Railway

> **Status (verificado 2026-09-26):** este guia nunca foi executado — não há
> nenhum serviço Railway ou Render conectado a este repositório. É um
> how-to, não um registro de deploy. Detalhe em `CLAUDE.md ## Deployment
> status`.

## Vantagens do Railway:
- ✅ 8GB RAM (vs 512MB do Render Starter)
- ✅ $5/mês (vs $7/mês do Render)
- ✅ Deploy automático do GitHub
- ✅ Interface moderna e simples
- ✅ Melhor para aplicações com Playwright

---

## 📋 Passo a Passo Completo:

### 1️⃣ Criar Conta no Railway

1. Acesse [railway.app](https://railway.app)
2. Clique em **"Login"** (canto superior direito)
3. Selecione **"Login with GitHub"**
4. Autorize o Railway a acessar seus repositórios

---

### 2️⃣ Criar Novo Projeto

1. No dashboard, clique em **"New Project"**
2. Selecione **"Deploy from GitHub repo"**
3. Procure e selecione: **`asimov-academy/Website-Downloader`**
4. Railway vai detectar automaticamente o Dockerfile

---

### 3️⃣ Configurar Variáveis de Ambiente (Opcional)

Não precisa configurar nada, mas se quiser otimizar:

1. Clique no serviço (card do projeto)
2. Vá em **"Variables"**
3. Adicione (opcional):
   ```
   PORT=8080
   PLAYWRIGHT_BROWSERS_PATH=/app/.cache
   ```

---

### 4️⃣ Aguardar Deploy

- O build vai levar ~3-5 minutos
- Acompanhe em **"Deployments"** → **"View Logs"**

Você deve ver:
```
==> Building Dockerfile
==> Pulling mcr.microsoft.com/playwright/python:v1.41.0-jammy
==> Build successful
==> Starting service
==> Service is live
```

---

### 5️⃣ Gerar URL Pública

1. No card do serviço, clique em **"Settings"**
2. Vá em **"Networking"**
3. Clique em **"Generate Domain"**
4. Railway vai gerar uma URL como: `website-downloader-production.up.railway.app`

---

### 6️⃣ Configurar Domínio Customizado (sd.asimov.academy)

#### A) No Railway:

1. Em **"Settings"** → **"Networking"**
2. Clique em **"Custom Domain"**
3. Digite: `sd.asimov.academy`
4. Railway vai mostrar um registro CNAME:
   ```
   Type: CNAME
   Name: sd
   Value: website-downloader-production.up.railway.app
   ```

#### B) No seu provedor de DNS:

1. Acesse o painel do seu provedor (GoDaddy, Namecheap, Cloudflare, etc.)
2. Vá em **DNS Settings** para o domínio `asimov.academy`
3. Adicione/Edite o registro CNAME:
   ```
   Type: CNAME
   Name: sd
   Value: website-downloader-production.up.railway.app
   TTL: 3600 (ou Auto)
   ```
4. Salve as mudanças

#### C) Aguarde propagação DNS (5-30 minutos)

- Teste em: [dnschecker.org](https://dnschecker.org)
- Digite: `sd.asimov.academy`

---

### 7️⃣ Configurar Deploy Automático

✅ Já vem ativado por padrão!

Toda vez que você fizer push na branch `main`:
```bash
git add .
git commit -m "Minha atualização"
git push
```

Railway automaticamente:
1. Detecta o push
2. Faz rebuild
3. Deploy automático

---

## 📊 Monitoramento

### Ver Logs em Tempo Real:
1. Clique no serviço
2. Vá em **"Deployments"**
3. Clique no deployment ativo
4. Veja os logs em tempo real

### Métricas:
1. No card do serviço
2. Vá em **"Metrics"**
3. Veja uso de CPU, RAM, Network

---

## 💰 Custos

Railway cobra por uso:
- **Base**: $5/mês (crédito incluído)
- **Uso típico**: $5-10/mês
- **Se passar**: ~$0.000231/GB RAM/min

**Estimativa para este projeto**: $5-8/mês

---

## 🎯 Próximos Passos Após Deploy:

1. ✅ Aguarde deploy completar (3-5 min)
2. ✅ Teste com a URL gerada pelo Railway
3. ✅ Configure domínio customizado
4. ✅ Teste novamente com `sd.asimov.academy`

---

## 🔧 Troubleshooting

### Deploy falhou?
- Verifique logs em "Deployments"
- Dockerfile está correto? (deve estar)

### Site não carrega?
- Verifique se o serviço está "Running" (bolinha verde)
- Teste a URL gerada pelo Railway primeiro

### Domínio customizado não funciona?
- Aguarde propagação DNS (pode levar até 48h, geralmente 5-30min)
- Verifique CNAME no DNS com: `dig sd.asimov.academy`

### Erro de memória ainda?
- Railway tem 8GB RAM, deve funcionar
- Se não funcionar, pode ter outro problema no código

---

## 📞 Suporte

- Documentação: [docs.railway.app](https://docs.railway.app)
- Discord: [discord.gg/railway](https://discord.gg/railway)
- Twitter: [@Railway](https://twitter.com/Railway)

---

## 🔄 Migração Completa:

Quando tudo estiver funcionando no Railway:

1. ✅ Teste completamente
2. ✅ Configure domínio
3. ✅ Delete o serviço do Render (economize $7/mês)

**Economia**: $2/mês + Muito mais RAM (8GB vs 512MB)
