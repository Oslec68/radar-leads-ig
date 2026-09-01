"""
RADAR DE LEADS B2B - CP Comercial

Busca perfis empresariais no Instagram, filtra pessoas fisicas e gera um CSV
priorizado para prospeccao comercial. Nao usa Supabase nem Google Sheets.

Secrets necessarios:
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
import unicodedata
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
PONTUACAO_MINIMA = 3

SEGMENTOS = {
    "Supermercado/Mercado": [
        "supermercado", "mercado", "minimercado", "mercearia", "rede de mercados",
        "rede de lojas", "varejo alimentar", "hortifruti", "conveniencia",
    ],
    "Distribuidor/Atacado": [
        "distribuidora", "distribuidor", "distribuicao", "atacado", "atacadista",
        "representacao comercial", "food service", "foodservice",
    ],
    "Emporio/Produtos naturais": [
        "emporio", "produtos naturais", "loja natural", "mundo verde", "organicos",
        "saudavel", "healthy food",
    ],
    "Academia/Suplementos": [
        "academia", "crossfit", "fitness", "suplementos", "nutricao esportiva",
        "loja de suplementos",
    ],
    "Restaurante/Food service": [
        "restaurante", "lanchonete", "cafeteria", "padaria", "hotel", "pousada",
        "bar", "quiosque", "delivery",
    ],
    "Farmacia/Bem-estar": [
        "farmacia", "drogaria", "bem estar", "wellness", "nutricionista",
    ],
}

TERMOS_EXCLUSAO = [
    "influencer", "criador de conteudo", "creator", "blog pessoal", "personal blog",
    "blogger", "modelo", "digital creator", "figura publica", "fan page",
]

TERMOS_SP = [
    "sao paulo", "sp", "capital paulista", "campinas", "jundiai", "vinhedo",
    "louveira", "valinhos", "sorocaba", "ribeirao preto", "santos", "guarulhos",
    "osasco", "abc paulista", "barueri", "piracicaba", "limeira", "americana",
    "indaiatuba", "itu", "braganca paulista", "bauru", "marilia",
]

CAMPOS_CSV = [
    "pontuacao",
    "prioridade_sp",
    "segmento",
    "motivos_qualificacao",
    "username",
    "nome",
    "bio",
    "seguidores",
    "verificado",
    "categoria_ig",
    "email",
    "telefone",
    "site",
    "cidade",
    "url_perfil",
    "hashtag_origem",
    "coletado_em",
]

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"(\(?\d{2}\)?\s?)?9?\d{4}[-.\s]?\d{4}")


def normalizar(texto) -> str:
    texto = str(texto or "").lower()
    return "".join(
        caractere for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    )


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


def extrair_contato(info):
    bio = info.biography or ""
    email_bio = EMAIL_REGEX.search(bio)
    telefone_bio = PHONE_REGEX.search(bio)
    email = getattr(info, "public_email", "") or (email_bio.group(0) if email_bio else "")
    telefone = (
        getattr(info, "contact_phone_number", "")
        or getattr(info, "public_phone_number", "")
        or (telefone_bio.group(0) if telefone_bio else "")
    )
    return email, telefone


def qualificar_perfil(info, email: str, telefone: str):
    if bool(getattr(info, "is_private", False)):
        return None

    nome = info.full_name or ""
    bio = info.biography or ""
    categoria = str(getattr(info, "category", "") or "")
    cidade = str(getattr(info, "city_name", "") or "")
    site = str(getattr(info, "external_url", "") or "")
    texto = normalizar(" ".join([nome, bio, categoria, cidade]))

    if any(termo in texto for termo in TERMOS_EXCLUSAO):
        return None

    pontos = 0
    motivos = []
    segmento = ""

    for nome_segmento, palavras in SEGMENTOS.items():
        encontrados = [palavra for palavra in palavras if palavra in texto]
        if encontrados:
            segmento = nome_segmento
            pontos += 3
            motivos.append("segmento comercial: " + encontrados[0])
            break

    categoria_normalizada = normalizar(categoria)
    categorias_pessoais = ("", "personal blog", "digital creator", "figura publica")
    if categoria_normalizada not in categorias_pessoais:
        pontos += 1
        motivos.append("categoria empresarial")

    if bool(getattr(info, "is_business", False)):
        pontos += 2
        motivos.append("conta comercial")

    if email or telefone:
        pontos += 2
        motivos.append("contato disponivel")

    if site:
        pontos += 1
        motivos.append("site na bio")

    prioridade_sp = any(
        re.search(rf"(?<![a-z]){re.escape(termo)}(?![a-z])", texto)
        for termo in TERMOS_SP
    )
    if prioridade_sp:
        pontos += 2
        motivos.append("localizacao em SP")

    if not segmento and pontos < PONTUACAO_MINIMA:
        return None

    return {
        "pontuacao": pontos,
        "prioridade_sp": "SIM" if prioridade_sp else "NAO",
        "segmento": segmento or "Empresa a revisar",
        "motivos_qualificacao": "; ".join(motivos),
        "site": site,
        "cidade": cidade,
    }


def coletar_por_hashtag(cl: Client, hashtag: str, limite: int) -> list[dict]:
    log.info("Coletando hashtag #%s (limite=%s)", hashtag, limite)
    leads = []
    vistos = set()
    descartados = 0

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
            email, telefone = extrair_contato(info)
            qualificacao = qualificar_perfil(info, email, telefone)
            if not qualificacao:
                descartados += 1
                continue

            leads.append(
                {
                    **qualificacao,
                    "username": info.username or "",
                    "nome": info.full_name or "",
                    "bio": info.biography or "",
                    "seguidores": info.follower_count or 0,
                    "verificado": bool(info.is_verified),
                    "categoria_ig": getattr(info, "category", "") or "",
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

    log.info(
        "#%s: %s leads B2B aprovados; %s perfis descartados",
        hashtag,
        len(leads),
        descartados,
    )
    return leads


def salvar_csv(leads: list[dict]):
    unicos = {}
    for lead in leads:
        username = lead.get("username")
        if username and (
            username not in unicos
            or lead["pontuacao"] > unicos[username]["pontuacao"]
        ):
            unicos[username] = lead

    ordenados = sorted(
        unicos.values(),
        key=lambda lead: (
            lead["prioridade_sp"] == "SIM",
            lead["pontuacao"],
            lead["seguidores"],
        ),
        reverse=True,
    )

    with open(ARQUIVO_CSV, "w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=CAMPOS_CSV)
        writer.writeheader()
        writer.writerows(ordenados)

    log.info("%s criado com %s leads B2B unicos", ARQUIVO_CSV, len(ordenados))


def main() -> int:
    log.info("=== Iniciando Radar de Leads B2B ===")
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
    log.info("=== Concluido: %s leads B2B aprovados ===", len(todos_os_leads))
    return 0


if __name__ == "__main__":
    sys.exit(main())
