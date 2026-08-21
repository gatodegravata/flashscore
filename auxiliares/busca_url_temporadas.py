# @title Busca URL temporadas (Powered by Flashscore GraphQL API)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validador e Coletor Ultrarrápido de Temporadas Flashscore (>= 2021)
- Extrai todas as temporadas, tournament_id, stage_id e campeões históricos diretamente via GraphQL
- Identifica com 100% de precisão a Temporada Atual (isCurrent: True) e as Temporadas Passadas
- Absorve todos os campos do menu: is_cup, tipo, nivel, principal, mod, country.
"""

import json
import os
import re
import sys
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

JSON_LOCAL = "auxiliares/paises_ligas.json"
JSON_URL = "https://raw.githubusercontent.com/gatodegravata/flashscore/refs/heads/main/auxiliares/paises_ligas.json"
OUTPUT_FILE = "auxiliares/temporadas_ligas.json"
BASE_URL = "https://www.flashscore.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.flashscore.com/"
}


def obter_temporadas_da_liga(league: dict) -> dict:
    """
    Consulta o GraphQL do Flashscore e extrai todas as temporadas, tournament_ids e stage_ids
    """
    root_url = league.get("url")
    if not root_url:
        league_copy = dict(league)
        league_copy["total_seasons"] = 0
        league_copy["seasons"] = []
        return league_copy

    t_id = league.get("tournament_id")
    s_id = league.get("stage_id")

    # Se já tiver os IDs enriquecidos, pula o download do HTML
    if not t_id or not s_id:
        archive_url = root_url.rstrip('/') + '/archive/'
        try:
            r_page = requests.get(archive_url, headers=HEADERS, timeout=10)
            if r_page.status_code != 200:
                r_page = requests.get(root_url, headers=HEADERS, timeout=10)

            html = r_page.text
            
            # Extrai tournamentId e tournamentStage do dataLayer
            m_tourn = re.search(r'\"tournamentId\":\"([a-zA-Z0-9]{8})\"', html)
            m_stage = re.search(r'\"tournamentStage\":\"([a-zA-Z0-9]{8})\"', html)
            
            if not m_tourn:
                m_tourn = re.search(r'\"tournament\":\"([a-zA-Z0-9]{8})\"', html)
            if not m_tourn:
                m_tourn = re.search(r'1_\d+_([a-zA-Z0-9]{8})_', html)

            t_id = t_id or (m_tourn.group(1) if m_tourn else None)
            s_id = s_id or (m_stage.group(1) if m_stage else None)
        except Exception:
            pass

    if not t_id:
        league_copy = dict(league)
        league_copy["total_seasons"] = 0
        league_copy["seasons"] = []
        return league_copy

    try:

        # Chama a API GraphQL
        gql_url = f"https://2.ds.lsapp.eu/pq_graphql?_hash=lph&tournamentId={t_id}&tournamentStageId={s_id or ''}&projectId=2"
        r_gql = requests.get(gql_url, headers=HEADERS, timeout=10)

        if r_gql.status_code != 200:
            league_copy = dict(league)
            league_copy["total_seasons"] = 0
            league_copy["seasons"] = []
            return league_copy

        data = r_gql.json()
        seasons_data = data.get('data', {}).get('getTournamentSeasons', {})

        requested = seasons_data.get('requested')
        others = seasons_data.get('other', [])
        all_seasons_raw = ([requested] if requested else []) + others

        root_base_url = root_url.rstrip('/') + '/'
        seasons_list = []

        for s in all_seasons_raw:
            if not s:
                continue
            start = str(s.get('start', '')).strip()
            end = str(s.get('end', '')).strip()
            is_current = bool(s.get('isCurrent', False))
            season_tid = s.get('tournamentId')

            # Formata o nome da temporada (ex: "2025/2026" ou "2026")
            if end and end != start:
                s_name = f"{start}/{end}"
                url_suffix = f"{start}-{end}"
            else:
                s_name = start
                url_suffix = start

            # Filtra apenas temporadas >= 2021
            ano_ref = int(end) if (end and end.isdigit()) else (int(start) if start.isdigit() else 0)
            if ano_ref < 2021:
                continue

            # Extrai stage_id oficial
            stages_obj = s.get('tournamentStages', {})
            stage_req = stages_obj.get('requested', {})
            stage_others = stages_obj.get('other', [])
            stage_id_season = stage_req.get('id') if stage_req else (stage_others[0].get('id') if stage_others else None)

            # Define a URL canônica correta
            if is_current:
                s_url = root_base_url
            else:
                s_url = root_base_url.rstrip('/') + f"-{url_suffix}/"

            # Campeão
            winner = s.get('winners', [{}])[0].get('name') if s.get('winners') else None

            seasons_list.append({
                'season_name': s_name,
                'tournament_id': season_tid,
                'stage_id': stage_id_season,
                'is_current': is_current,
                'winner': winner,
                'url': s_url,
                'path': s_url.replace("https://www.flashscore.com", "")
            })

        # Ordena temporadas da mais recente para a mais antiga
        def sort_key(x):
            m = re.search(r'\d{4}', x['season_name'])
            return int(m.group(0)) if m else 0

        seasons_list.sort(key=sort_key, reverse=True)

        league_copy = dict(league)
        league_copy["total_seasons"] = len(seasons_list)
        league_copy["seasons"] = seasons_list
        return league_copy

    except Exception:
        league_copy = dict(league)
        league_copy["total_seasons"] = 0
        league_copy["seasons"] = []
        return league_copy


def carregar_paises_ligas() -> list[dict]:
    """Carrega todas as ligas achatadas a partir de paises_ligas.json (local ou remoto)"""
    raw_data = None
    if os.path.exists(JSON_LOCAL):
        print(f"📖 Carregando ligas de {JSON_LOCAL}...")
        with open(JSON_LOCAL, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    else:
        print(f"🌐 Baixando ligas do GitHub: {JSON_URL}...")
        r = requests.get(JSON_URL, headers=HEADERS, timeout=15)
        raw_data = r.json()

    if isinstance(raw_data, list):
        return raw_data
        
    if "leagues" in raw_data and isinstance(raw_data["leagues"], list):
        return raw_data["leagues"]

    todas_ligas = []
    
    # 1. Extrai ligas dos países
    for c in raw_data.get("countries", []):
        c_id = c.get("id")
        c_name = c.get("name")
        for l in c.get("leagues", []):
            l_dict = dict(l)
            l_dict["country_id"] = c_id
            l_dict["country_name"] = c_name
            todas_ligas.append(l_dict)

    # 2. Extrai ligas de outras competições
    for o in raw_data.get("other_competitions", []):
        o_id = o.get("id")
        o_name = o.get("name")
        for l in o.get("leagues", []):
            l_dict = dict(l)
            l_dict["country_id"] = o_id
            l_dict["country_name"] = o_name
            todas_ligas.append(l_dict)

    return todas_ligas


def main():
    print("=" * 80)
    print("🚀 FLASHSCORE SEASONS & STAGES EXTRACTION (Powered by GraphQL)")
    print("=" * 80)

    leagues = carregar_paises_ligas()
    total_leagues = len(leagues)
    print(f"📋 Total de ligas a processar: {total_leagues}\n")

    resultado = []
    total_temporadas_coletadas = 0

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(obter_temporadas_da_liga, l): l for l in leagues}

        for i, future in enumerate(as_completed(futures), 1):
            res = future.result()
            resultado.append(res)
            n_seasons = res.get("total_seasons", 0)
            total_temporadas_coletadas += n_seasons
            
            nome = res.get('league_name', 'Liga')
            pais = res.get('country_name', 'País')
            if n_seasons > 0:
                print(f"[{i:4d}/{total_leagues}] ✓ [{pais}] {nome} ➔ {n_seasons} temporadas encontradas")
            else:
                print(f"[{i:4d}/{total_leagues}] ⚪ [{pais}] {nome} ➔ 0 temporadas")

    # Garante a ordem original
    url_to_index = {l.get("url"): idx for idx, l in enumerate(leagues)}
    resultado.sort(key=lambda x: url_to_index.get(x.get("url"), 999999))

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "source": "Flashscore GraphQL Seasons & Stages Extractor",
                "total_leagues": len(resultado),
                "total_seasons_collected": total_temporadas_coletadas
            },
            "leagues": resultado
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"🎉 Processamento concluído com sucesso!")
    print(f"✓ Total de Ligas: {len(resultado)}")
    print(f"✓ Total de Temporadas Coletadas: {total_temporadas_coletadas}")
    print(f"💾 Salvo em: {OUTPUT_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    main()