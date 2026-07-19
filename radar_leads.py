"""
RADAR DE LEADS - CP Comercial
Raspagem de contas do Instagram por hashtag (bebidas funcionais, kombucha,
fibra, proteina, suco de uva, agua mineral) para geracao de leads B2B.

FLUXO:
1. Login no Instagram (via instagrapi)
2. Para cada hashtag configurada, busca N contas recentes
3. Extrai dados de perfil (nome, username, bio, seguidores, contato)
4. Deduplica e salva no Supabase
5. Sincroniza tabela com Google Sheets

USO:
    python radar_leads.py

VARIAVEIS DE AMBIENTE NECESSARIAS (configurar no Render/Vercel):
    IG_USERNAME, IG_PASSWORD
    SUPABASE_URL, SUPABASE_KEY
    GOOGLE_SHEETS_CREDS_JSON (conteudo do service account, como string JSON)
    GOOGLE_SHEET_ID
"""

import os
import re
import json
import time
import random
import logging
from datetime import datetime, timezone

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("radar_leads")

# ---------------------------------------------------------------------------
# CONFIGURACAO
# ---------------------------------------------------------------------------

HASHTAGS = [
    "kombucha",
    "energeticocomproteina",
    "bebidasfuncionais",
    "bebidacomproteina",
    "bebidasenergeticas",
    "aguamineral",
    "sucodeuvaintegral",
    "bebidasfuncionaiscomfibra",
]

CONTAS_POR_HASHTAG = 60          # meta: 50-100 por hashtag
INTERVALO_ENTRE_ACOES = (3, 8)   # segundos, randomizado, para reduzir risco de bloqueio
SESSION_FILE = "ig_session.json"

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"(\(?\d{2}\)?\s?)?9?\d{4}[-.\s]?\d{4}")

# ---------------------------------------------------------------------------
# CLIENTES EXTERNOS
# ---------------------------------------------------------------------------

def get_instagram_client() -> Client:
    cl = Client()
    cl.delay_range = INTERVALO_ENTRE_ACOES

    if os.path.exists(SESSION_FILE):
        cl.load_settings(SESSION_FILE)
        try:
            cl.login(os.environ["IG_USERNAME"], os.environ["IG_PASSWORD"])
            cl.get_timeline_feed()  # valida sessao
        except (LoginRequired, ClientError):
            log.info("Sessao expirada, fazendo novo login...")
            cl.login(os.environ["IG_USERNAME"], os.environ["IG_PASSWORD"])
    else:
        cl.login(os.environ["IG_USERNAME"], os.environ["IG_PASSWORD"])

    cl.dump_settings(SESSION_FILE)
    return cl


def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


# ---------------------------------------------------------------------------
# EXTRACAO
# ---------------------------------------------------------------------------

def extrair_contato(bio: str):
    email = EMAIL_REGEX.search(bio or "")
    telefone = PHONE_REGEX.search(bio or "")
    return (email.group(0) if email else None,
            telefone.group(0) if telefone else None)


def coletar_por_hashtag(cl: Client, hashtag: str, limite: int) -> list[dict]:
    log.info(f"Coletando hashtag #{hashtag} (limite={limite})")
    leads = []
    vistos = set()

    try:
        medias = cl.hashtag_medias_recent(hashtag, amount=limite)
    except Exception as e:
        log.warning(f"Falha ao buscar #{hashtag}: {e}")
        return leads

    for media in medias:
        try:
            user_id = media.user.pk
            if user_id in vistos:
                continue
            vistos.add(user_id)

            info = cl.user_info(user_id)
            email, telefone = extrair_contato(info.biography)

            leads.append({
                "username": info.username,
                "nome": info.full_name,
                "bio": info.biography,
                "seguidores": info.follower_count,
                "verificado": info.is_verified,
                "categoria_ig": info.category or None,
                "email": email,
                "telefone": telefone,
                "url_perfil": f"https://instagram.com/{info.username}",
                "hashtag_origem": hashtag,
                "coletado_em": datetime.now(timezone.utc).isoformat(),
            })
            time.sleep(random.uniform(*INTERVALO_ENTRE_ACOES))
        except Exception as e:
            log.warning(f"Erro ao processar conta: {e}")
            continue

    log.info(f"#{hashtag}: {len(leads)} contas coletadas")
    return leads


# ---------------------------------------------------------------------------
# PERSISTENCIA
# ---------------------------------------------------------------------------

def salvar_supabase(sb, leads: list[dict]):
    if not leads:
        return
    # upsert por username para evitar duplicados
    sb.table("radar_leads_ig").upsert(leads, on_conflict="username").execute()
    log.info(f"{len(leads)} leads gravados/atualizados no Supabase")


def sincronizar_google_sheets(sb):
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds_dict = json.loads(os.environ["GOOGLE_SHEETS_CREDS_JSON"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)

        sh = gc.open_by_key(os.environ["GOOGLE_SHEET_ID"])
        ws = sh.sheet1

        dados = sb.table("radar_leads_ig").select("*").order("coletado_em", desc=True).execute().data
        if not dados:
            return

        cabecalho = list(dados[0].keys())
        linhas = [cabecalho] + [[str(d.get(c, "")) for c in cabecalho] for d in dados]

        ws.clear()
        ws.update(linhas)
        log.info(f"Google Sheets sincronizado com {len(dados)} leads")
    except Exception as e:
        log.warning(f"Falha ao sincronizar Google Sheets: {e}")


# ---------------------------------------------------------------------------
# EXECUCAO PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    log.info("=== Iniciando Radar de Leads ===")
    cl = get_instagram_client()
    sb = get_supabase()

    total = 0
    for tag in HASHTAGS:
        leads = coletar_por_hashtag(cl, tag, CONTAS_POR_HASHTAG)
        salvar_supabase(sb, leads)
        total += len(leads)
        time.sleep(random.uniform(15, 30))  # pausa entre hashtags

    sincronizar_google_sheets(sb)
    log.info(f"=== Concluido: {total} leads processados ===")


if __name__ == "__main__":
    main()
