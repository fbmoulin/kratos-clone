# 🚀 Deploy no Render

> **Status (verificado 2026-09-26 via Render API):** este guia nunca foi
> executado. Não existe serviço na conta Render conectado a este repositório
> — `render.yaml` é só uma definição de Blueprint inerte até alguém seguir os
> passos abaixo manualmente. Leia como instruções para fazer, não como
> registro de que foi feito. Detalhe em `CLAUDE.md ## Deployment status`.

## Opção Recomendada: Render.com

### Passo a Passo Completo:

#### 1. Preparar Repositório GitHub
```bash
# Se ainda não inicializou o git
git init
git add .
git commit -m "Preparar projeto para deploy"

# Criar repositório no GitHub e fazer push
git remote add origin https://github.com/SEU_USUARIO/website-downloader.git
git branch -M main
git push -u origin main
```

#### 2. Configurar no Render

1. **Criar conta**: Acesse [render.com](https://render.com) e faça login com GitHub

2. **Novo Web Service**:
   - Clique em "New +" → "Web Service"
   - Conecte seu repositório GitHub
   - Selecione o repositório `website-downloader`

3. **Configurações**:
   - O Render detectará automaticamente o `Dockerfile`
   - Se não detectar, configure manualmente:
     ```
     Name: website-downloader (ou qualquer nome)
     Environment: Docker
     ```
   - Não precisa configurar Build/Start Command (o Dockerfile já tem isso)

4. **Plano**: 
   - Selecione o plano **Starter** ($7/mês)
   - Plano gratuito NÃO funciona (precisa de mais RAM para Playwright)

5. **Deploy**: Clique em "Create Web Service"

#### 3. Configurar Domínio Customizado

1. No dashboard do Render, vá em **Settings** → **Custom Domain**
2. Adicione: `sd.asimov.academy`
3. Render vai mostrar um registro CNAME:
   ```
   Type: CNAME
   Name: sd
   Value: website-downloader.onrender.com (ou similar)
   ```

4. **Configure no seu provedor de domínio** (ex: GoDaddy, Namecheap, Cloudflare):
   - Adicione o registro CNAME mostrado pelo Render
   - Aguarde propagação DNS (5-30 minutos)

5. Render vai provisionar SSL automaticamente (gratuito)

#### 4. Deploy Automático

✅ **PRONTO!** Agora toda vez que você fizer push na branch `main`:

```bash
git add .
git commit -m "Atualização do site"
git push
```

O Render automaticamente:
1. Detecta o push
2. Rebuilda a aplicação
3. Faz deploy automático
4. Atualiza o site em produção

### Monitoramento

- **Logs**: Dashboard do Render → Logs
- **Status**: Dashboard mostra se está rodando
- **Builds**: Veja histórico de deploys

---

## 🔄 Outras Opções

### Opção 2: Railway.app
**Prós**: Ainda mais fácil, UI moderna
**Contras**: ~$10-15/mês (mais caro)
**Setup**: Similar ao Render, conecta GitHub e deploy automático

### Opção 3: Fly.io
**Prós**: Bom desempenho, infraestrutura moderna
**Contras**: Requer configuração de Dockerfile
**Preço**: ~$5-10/mês

### Opção 4: DigitalOcean App Platform
**Prós**: Infraestrutura robusta
**Contras**: Interface menos intuitiva
**Preço**: $5-12/mês

---

## 🛠️ Troubleshooting

### Erro: "Out of memory"
- Aumente o plano no Render (precisa de pelo menos 512MB RAM)

### Erro: "Playwright/Chromium não encontrado"
- Verifique se o build command inclui: `playwright install --with-deps chromium`

### Deploy não acontece automaticamente
- Vá em Settings → GitHub e verifique se "Auto-Deploy" está ativado na branch `main`

### Domínio não funciona
- Verifique se adicionou o CNAME correto no seu DNS
- Aguarde propagação DNS (pode demorar até 48h, geralmente 5-30min)
- Use [dnschecker.org](https://dnschecker.org) para verificar

---

## 💰 Custos Estimados

| Serviço | Plano | Custo/mês |
|---------|-------|-----------|
| Render | Starter | $7 |
| Railway | Hobby | $10-15 |
| Fly.io | Pay-as-you-go | $5-10 |
| DigitalOcean | Basic | $5-12 |

**Recomendação**: Comece com Render ($7/mês) pela praticidade.
