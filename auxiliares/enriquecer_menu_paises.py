#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enriquecedor de Países e Ligas Flashscore (Powered by Country Ninja Feed c_1_{id})
Adiciona ao paises_ligas.json:
- tournament_id (ZE) da temporada atual
- stage_id (ZC) da temporada atual
- template_id (ZEE) identificador perpétuo da competição
- fs_sort_order e fs_sort_key (ZX) hierarquia nativa do Flashscore
Mantém 100% dos campos atuais intactos: is_cup, tipo, nivel, principal, mod, etc.
"""

import json
import os
import re
import sys
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

INPUT_FILE = "auxiliares/paises_ligas.json"
OUTPUT_FILE = "auxiliares/paises_ligas.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.flashscore.com/",
    "x-fsign": "SW9D1eZo"
}


def obter_feed_pais(country_id: int) -> dict:
    """Busca o feed do país e mapeia todas as ligas por URL e por Nome"""
    feed_url = f"https://global.flashscore.ninja/2/x/feed/c_1_{country_id}_-3_en_y_1"
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=10)
        if r.status_code != 200 or not r.text:
            return {}

        blocos = r.text.split('~ZA÷')
        if len(blocos) <= 1:
            return {}

        leagues_map = {}

        for idx, bloco in enumerate(blocos[1:]):
            header = bloco.split('¬')[0]
            
            def get_tag(tag):
                m = re.search(rf'~?{tag}÷([^¬]+)¬', bloco)
                return m.group(1) if m else None

            t_id = get_tag('ZE')
            s_id = get_tag('ZC')
            temp_id = get_tag('ZEE')
            path = get_tag('ZL')
            sort_key = get_tag('ZX')

            if not path:
                continue

            # URL canônica raiz limpa
            path_clean = re.sub(r'[-_]20\d{2}(?:[-_]20\d{2})?', '', path.rstrip('/')).replace('/results', '').replace('/standings', '').replace('/fixtures', '') + '/'
            
            # Extrai o índice numérico do sort_key
            m_ordem = re.search(r'007[a-zA-Z]+(\d{3})', sort_key or '')
            sort_num = int(m_ordem.group(1)) if m_ordem else idx

            info = {
                "tournament_id": t_id,
                "stage_id": s_id,
                "template_id": temp_id,
                "fs_sort_order": sort_num,
                "fs_sort_key": sort_key,
                "header_raw": header
            }

            # Mapeia por path normalizado
            if path_clean not in leagues_map:
                leagues_map[path_clean] = info
                
            # Mapeia também por slug final
            slug = path_clean.strip('/').split('/')[-1]
            if slug and slug not in leagues_map:
                leagues_map[slug] = info

        return leagues_map

    except Exception:
        return {}


def enriquecer_paises_ligas():
    print("=" * 80)
    print("🚀 ENRIQUECIMENTO DE PAÍSES E LIGAS (Powered by Country Ninja Feed)")
    print("=" * 80)

    if not os.path.exists(INPUT_FILE):
        print(f"❌ Arquivo {INPUT_FILE} não encontrado!")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    countries = data.get("countries", [])
    total_countries = len(countries)
    print(f"📋 Total de países a processar: {total_countries}\n")

    total_ligas_enriquecidas = 0
    total_ligas_geral = 0

    # Coleta os feeds de todos os países em paralelo
    feeds_por_pais = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_cid = {executor.submit(obter_feed_pais, c.get("id")): c.get("id") for c in countries if c.get("id")}
        for future in as_completed(future_to_cid):
            cid = future_to_cid[future]
            feeds_por_pais[cid] = future.result()

    # Aplica o enriquecimento nos objetos de ligas
    for c in countries:
        c_id = c.get("id")
        c_name = c.get("name")
        c_feed = feeds_por_pais.get(c_id, {})
        
        for l in c.get("leagues", []):
            total_ligas_geral += 1
            l_path = l.get("path", "")
            l_url = l.get("url", "")
            
            # Busca correspondência no feed
            path_clean = re.sub(r'[-_]20\d{2}(?:[-_]20\d{2})?', '', l_path.rstrip('/')).replace('/results', '').replace('/standings', '').replace('/fixtures', '') + '/'
            slug = path_clean.strip('/').split('/')[-1]
            
            info = c_feed.get(path_clean) or c_feed.get(slug)
            
            if info:
                l["tournament_id"] = info["tournament_id"]
                l["stage_id"] = info["stage_id"]
                l["template_id"] = info["template_id"]
                l["fs_sort_order"] = info["fs_sort_order"]
                l["fs_sort_key"] = info["fs_sort_key"]
                total_ligas_enriquecidas += 1
            else:
                l["tournament_id"] = None
                l["stage_id"] = None
                l["template_id"] = None
                l["fs_sort_order"] = None
                l["fs_sort_key"] = None

    # Atualiza metadados
    if "metadata" not in data:
        data["metadata"] = {}
    data["metadata"]["enriched_with_country_feed"] = True
    data["metadata"]["total_leagues_enriched"] = total_ligas_enriquecidas

    # Salva o arquivo enriquecido
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("🎉 Enriquecimento concluído com sucesso!")
    print(f"✓ Total de Ligas: {total_ligas_geral}")
    print(f"✓ Ligas Enriquecidas com TournamentID / StageID / SortOrder: {total_ligas_enriquecidas} ({(total_ligas_enriquecidas/total_ligas_geral*100):.1f}%)")
    print(f"💾 Salvo em: {OUTPUT_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    enriquecer_paises_ligas()
