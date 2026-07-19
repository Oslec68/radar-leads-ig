# Radar de Leads IG — CP Comercial

Raspa contas do Instagram por hashtag (kombucha, funcionais, fibra, proteína,
suco de uva, água mineral) e organiza os leads no Supabase + Google Sheets.

## ⚠️ Aviso importante antes de rodar

Este script usa `instagrapi`, uma biblioteca **não-oficial** que simula um
app de Instagram logado. Isso viola os Termos de Uso do Instagram, e o risco
real é a **conta usada correr risco de bloqueio ou banimento** se rodar
agressivo demais. Para reduzir esse risco:

- Use uma conta secundária (não a principal do CP Comercial/GROKO) para login.
- Mantenha o limite de 50–100 contas/hashtag e rode só 1x por dia — já está
  configurado assim no script.
- Se a conta cair em bloqueio temporário, pare por 48–72h antes de tentar de novo.

**Alternativa mais segura (sem risco de banimento):** a API oficial do
Instagram Graph (Business) permite buscar hashtags, mas exige que as contas
pesquisadas sejam Business/Creator e tem limites mais restritos de volume.
Se preferir estabilidade a longo prazo, posso montar essa versão também —
é mais lenta pra coletar, mas não arrisca sua conta.

## Setup (passo a passo)

1. **Conta Instagram dedicada**: crie ou use uma conta separada para o robô.
2. **Supabase**: crie um projeto gratuito em supabase.com, rode o arquivo
   `supabase_schema.sql` no SQL Editor pra criar a tabela.
3. **Google Sheets**: crie uma planilha, ative a Google Sheets API no Google
   Cloud Console, gere uma Service Account, compartilhe a planilha com o
   email da service account (permissão de editor).
4. **Deploy no Render** (grátis pra cron jobs leves):
   - Suba esta pasta num repositório GitHub.
   - No Render, crie um novo "Blueprint" apontando pro repo (ele lê o
     `render.yaml` automaticamente).
   - Preencha as variáveis de ambiente (IG_USERNAME, IG_PASSWORD, SUPABASE_URL,
     SUPABASE_KEY, GOOGLE_SHEETS_CREDS_JSON, GOOGLE_SHEET_ID).
5. Pronto — roda sozinho todo dia às 02h (horário de Brasília) e atualiza a
   planilha automaticamente.

## Ajustando hashtags depois

Edite a lista `HASHTAGS` no topo do `radar_leads.py` e faça novo deploy
(ou peça pra mim que eu atualizo e te devolvo o arquivo).

## Colunas que chegam na planilha

username, nome, bio, seguidores, verificado, categoria_ig, email, telefone,
url_perfil, hashtag_origem, coletado_em, status, responsavel, observacoes

As três últimas (`status`, `responsavel`, `observacoes`) são pra você
preencher manualmente conforme for qualificando e trabalhando os leads.
