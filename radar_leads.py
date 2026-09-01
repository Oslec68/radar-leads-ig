"""
RADAR DE LEADS - CP Comercial

Busca contas do Instagram por hashtags e gera um arquivo CSV compativel
com Excel. Nao depende de Supabase nem de Google Sheets.

Variaveis de ambiente:
    IG_USERNAME
    IG_PASSWORD
"""

import csv
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

from instagrapi import Client
from instagrapi.exceptions import ClientError, LoginRequired

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("radar_leads")

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

CONTAS_POR_HASHTAG = 60
INTERVALO_ENTRE_ACOES = (3, 8)
SESSION_FILE = "ig_session.json"
ARQUIVO_CSV = "leads.csv"

CAMPOS_CSV = [
    "username",
    "nome",
    "bio",
    "seguidores",
    "verificado",
    "categoria_ig",
    "email",
    "telefone",
    "url_perfil",
    "hashtag_origem",
    "coletado_em",
]

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"(\(?\d{2}\)?\s?)?9?\d{4}[-.\s]?\d{4}")


def validar_configuracao():
    ausentes = [nome for nome in ("IG_USERNAME", "IG_PASSWORD") if not os.getenv(nome)]
    if ausentes:
        raise RuntimeError("Secrets ausentes no GitHub: " + ", ".join(ausentes))


def criar_csv_vazio():
    with open(ARQUIVO_CSV, "w", newline="", encoding="utf-8-sig") as arquivo:
        csv.DictWriter(arquivo, fieldnames=CAMPOS_CSV).writeheader()


def get_instagram_client() -> Client:
    validar_configuracao()
    cl = Client()
    cl.delay_range = INTERVALO_ENTRE_ACOES

    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(os.environ["IG_USERNAME"], os.environ["IG_PASSWORD"])
            cl.get_timeline_feed()
            log.info("Sessao anterior do Instagram reutilizada")
        except (LoginRequired, ClientError):
            log.info("Sessao anterior expirada; renovando login")
            cl = Client()
            cl.delay_range = INTERVALO_ENTRE_ACOES
            cl.login(os.environ["IG_USERNAME"], os.environ["IG_PASSWORD"])
    else:
        cl.login(os.environ["IG_USERNAME"], os.environ["IG_PASSWORD"])

    cl.dump_settings(SESSION_FILE)
    return cl


def extrair_contato(bio: str):
    email = EMAIL_REGEX.search(bio or "")
    telefone = PHONE_REGEX.search(bio or "")
    return (
        email.group(0) if email else "",
        telefone.group(0) if telefone else "",
    )


def coletar_por_hashtag(cl: Client, hashtag: str, limite: int) -> list[dict]:
    log.info("Coletando hashtag #%s (limite=%s)", hashtag, limite)
    leads = []
    vistos = set()

    try:
        medias = cl.hashtag_medias_recent(hashtag, amount=limite)
    except Exception as erro:
        log.warning("Falha ao buscar #%s: %s", hashtag, type(erro).__name__)
        return leads

    for media in medias:
        try:
            user_id = media.user.pk
            if user_id in vistos:
                continue
            vistos.add(user_id)

            info = cl.user_info(user_id)
            email, telefone = extrair_contato(info.biography)
            leads.append(
                {
                    "username": info.username or "",
                    "nome": info.full_name or "",
                    "bio": info.biography or "",
                    "seguidores": info.follower_count or 0,
                    "verificado": bool(info.is_verified),
                    "categoria_ig": info.category or "",
                    "email": email,
                    "telefone": telefone,
                    "url_perfil": f"https://instagram.com/{info.username}",
                    "hashtag_origem": hashtag,
                    "coletado_em": datetime.now(timezone.utc).isoformat(),
                }
            )
            time.sleep(random.uniform(*INTERVALO_ENTRE_ACOES))
        except Exception as erro:
            log.warning("Conta ignorada por erro: %s", type(erro).__name__)

    log.info("#%s: %s contas coletadas", hashtag, len(leads))
    return leads


def salvar_csv(leads: list[dict]):
    unicos = {}
    for lead in leads:
        username = lead.get("username")
        if username and username not in unicos:
            unicos[username] = lead

    with open(ARQUIVO_CSV, "w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=CAMPOS_CSV)
        writer.writeheader()
        writer.writerows(unicos.values())

    log.info("%s criado com %s leads unicos", ARQUIVO_CSV, len(unicos))


def main() -> int:
    log.info("=== Iniciando Radar de Leads ===")
    criar_csv_vazio()

    try:
        cl = get_instagram_client()
    except Exception as erro:
        log.error(
            "Falha segura no login do Instagram (%s). "
            "Confira bloqueio temporario e os secrets IG_USERNAME/IG_PASSWORD.",
            type(erro).__name__,
        )
        return 1

    todos_os_leads = []
    for indice, tag in enumerate(HASHTAGS):
        todos_os_leads.extend(coletar_por_hashtag(cl, tag, CONTAS_POR_HASHTAG))
        if indice < len(HASHTAGS) - 1:
            time.sleep(random.uniform(15, 30))

    salvar_csv(todos_os_leads)
    log.info("=== Concluido: %s leads coletados ===", len(todos_os_leads))
    return 0


if __name__ == "__main__":
    sys.exit(main())
