# @title Busca URL temporadas
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validador de Temporadas Flashscore (>= 2021)
- Identifica a Temporada Atual na URL Canônica Raiz (ex: /football/australia/npl-nsw/)
- Extrai as Temporadas Passadas com sufixos de ano (ex: /football/australia/npl-nsw-2025/)
- Captura o tournament_id oficial de cada temporada em 1 único request HTTP
- Absorve todos os campos do menu: is_cup, tipo, nivel, principal, mod, country.
"""

import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

JSON_LOCAL = "auxiliares/paises_ligas.json"
JSON_URL = "https://raw.githubusercontent.com/gatodegravata/flashscore/refs/heads/main/auxiliares/paises_ligas.json"
BASE_URL = "https://www.flashscore.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Temporadas a testar (2021 a 2027)
ANOS_SIMPLES = [str(a) for a in range(2021, 2028)]
ANOS_DUPLOS = [f"{a}-{a+1}" for a in range(2021, 2027)]
PADROES = sorted(list(set(ANOS_SIMPLES + ANOS_DUPLOS)), reverse=True)


def eh_feminino(league_name: str) -> bool:
    name = league_name.lower()
    return any(w in name for w in ["women", "femin", "frauen", "dames", "femminile"])


def eh_base(league_name: str, path: str = "") -> bool:
    name = league_name.lower().strip()
    if name == "premier league 2" or ("/england/" in path and "premier-league-2" in path):
        return True
    return (
        bool(re.search(r'(?i)\b(u|sub-?)\d{2}\b', name)) or
        bool(re.search(r'(?i)\by-league\b', name)) or
        any(w in name for w in ["reserve", "reserva", "youth", "primavera", "aspirante", "junior", "juvenil", "academy", "development", "jeugd", "ungdom"])
    )


def definir_modalidade(league_name: str, path: str = "") -> str | None:
    is_w = eh_feminino(league_name)
    is_y = eh_base(league_name, path)

    if is_w and is_y:
        return "WY"
    if is_w:
        return "W"
    if is_y:
        return "Y"
    return None


def checar_e_extrair_temporada(url: str):
    """
    Testa se a URL da temporada existe (200 OK) e extrai o tournament_id e título do HTML.
    Retorna (existe: bool, tournament_id: str | None, title: str)
    """
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                html = resp.read().decode('utf-8', errors='ignore')
                m_tid = re.search(r'\"tournament\"[:=]\s*\"?([a-zA-Z0-9]{8})\"?', html)
                tournament_id = m_tid.group(1) if m_tid else None
                m_title = re.search(r'<title>(.*?)</title>', html)
                title = m_title.group(1) if m_title else ""
                return True, tournament_id, title
    except Exception:
        pass
    return False, None, ""


def extrair_temporadas_liga(league: dict) -> dict:
    base_url = league.get("url", "").rstrip('/')
    seasons = []
    seen_seasons = set()

    if base_url:
        # 1. Analisa a página raiz para a TEMPORADA ATUAL (URL Canônica Raiz)
        root_url = f"{base_url}/"
        ok_root, root_tid, root_title = checar_e_extrair_temporada(root_url)
        
        if ok_root:
            # Procura anos no título da página raiz (ex: "2025/2026", "2026-2027", "2026")
            m_year_double = re.search(r'\b(20\d{2})[-/](20\d{2})\b', root_title)
            m_year_single = re.search(r'\b(20\d{2})\b', root_title)
            
            curr_season_key = None
            if m_year_double:
                curr_season_key = f"{m_year_double.group(1)}-{m_year_double.group(2)}"
                curr_season_name = f"{m_year_double.group(1)}/{m_year_double.group(2)}"
            elif m_year_single:
                curr_season_key = m_year_single.group(1)
                curr_season_name = m_year_single.group(1)
                
            if curr_season_key:
                seen_seasons.add(curr_season_key)
                seasons.append({
                    "season_name": curr_season_name,
                    "tournament_id": root_tid,
                    "url": root_url,
                    "path": root_url.replace(BASE_URL, '')
                })

        # 2. Testa temporadas anteriores com sufixo de ano
        for padrao in PADROES:
            if padrao in seen_seasons:
                continue
                
            season_url = f"{base_url}-{padrao}/"
            existe, tournament_id, _ = checar_e_extrair_temporada(season_url)
            if existe:
                seen_seasons.add(padrao)
                seasons.append({
                    "season_name": padrao.replace('-', '/'),
                    "tournament_id": tournament_id,
                    "url": season_url,
                    "path": season_url.replace(BASE_URL, '')
                })

    # Ordena temporadas da mais recente para a mais antiga
    def parse_season_sort_key(s):
        s_name = s.get("season_name", "")
        nums = re.findall(r'\d+', s_name)
        return int(nums[-1]) if nums else 0

    seasons.sort(key=parse_season_sort_key, reverse=True)

    # Copia todas as chaves existentes (is_cup, tipo, nivel, principal, mod, country)
    resultado = dict(league)
    if not resultado.get("mod"):
        resultado["mod"] = definir_modalidade(league.get("league_name", ""), league.get("path", ""))
    resultado["total_seasons"] = len(seasons)
    resultado["seasons"] = seasons

    return resultado


def main(output_file="auxiliares/temporadas_ligas.json", max_workers=30):
    if os.path.exists(JSON_LOCAL):
        print(f"[*] Lendo arquivo local: {JSON_LOCAL}")
        with open(JSON_LOCAL, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        print(f"[*] Baixando do GitHub: {JSON_URL}...")
        req = urllib.request.Request(JSON_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))

    todas_ligas = []

    # Processa países e competições preservando dados do grupo
    for grupo in data.get("countries", []) + data.get("other_competitions", []):
        c_id = grupo.get("id")
        c_name = grupo.get("name")
        for l in grupo.get("leagues", []):
            item = dict(l)
            item.setdefault("country_id", c_id)
            item.setdefault("country_name", c_name)
            todas_ligas.append(item)

    ligas_unicas = list({l['url']: l for l in todas_ligas if 'url' in l}.values())
    total = len(ligas_unicas)
    print(f"[*] Validando temporadas e extraindo tournament_ids de {total} ligas ({max_workers} threads)...")

    resultados = []
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(extrair_temporadas_liga, liga): liga for liga in ligas_unicas}
        for future in as_completed(futures):
            resultados.append(future.result())
            done += 1
            if done % 50 == 0 or done == total:
                print(f"    Progresso: {done}/{total} ligas...")

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "metadata": {
                "source": "Flashscore Football Seasons & Tournament IDs Validator",
                "total_leagues": total,
                "total_seasons_collected": sum(r["total_seasons"] for r in resultados)
            },
            "leagues": resultados
        }, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"[+] SUCESSO! Temporadas e Tournament IDs salvos em: {output_file}")
    print(f"   * Total de Ligas: {total}")
    print(f"   * Total de Temporadas válidas encontradas: {sum(r['total_seasons'] for r in resultados)}")
    print("=" * 80)


if __name__ == "__main__":
    main()