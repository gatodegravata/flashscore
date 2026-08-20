#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extrator do Menu Lateral da Flashscore (Países, Continentes e Ligas)
Identifica com precisão:
- Países e Continentes
- Ligas, Copas, Supercopas, Torneios de Base e Feminino
- Nível da Liga (Tier 1, Tier 2, Tier 3...) e Liga Principal
"""

import json
import os
import re
import sys
import argparse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

BASE_URL = "https://www.flashscore.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


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


def identificar_tipo(league_name: str, path: str = "") -> str:
    name_lower = league_name.lower()
    if bool(re.search(r'\b(super\s*cup|supercup|supercopa|supercoppa|supertaça|supertaca|superpokal|recopa)\b', name_lower)):
        return "Supercopa"
    if bool(re.search(r'\b(cup|cupen|copa|taca|taça|pokal|pokalen|coupe|coppa|trofeo|trophy|shield|puchar|beker|bikar|kauss|taure|kupa|kup|fa cup|dfb-pokal)\b', name_lower)):
        return "Copa"
    if bool(re.search(r'\b(verano|amistoso|friendly|summer)\b', name_lower)):
        return "Amistoso"
    if eh_base(league_name, path):
        return "Base/Reserva"
    return "Liga"


def extrair_nome_base_liga(league_name: str) -> str:
    """Remove sufixos de playoffs, promoção, rebaixamento, grupos regionais e fases de pós-temporada."""
    name = league_name.strip()
    
    # 1. Remove sufixos de playoffs, playouts, promoção, rebaixamento e fases finais
    playoff_patterns = [
        r'(?i)\s*[-–]?\s*\b(promotion|relegation|rebaixamento|promocao|acesso|permanencia)\s*[-–]?\s*(play\s*offs?|play\s*outs?|playoffs?|playouts?)\b.*$',
        r'(?i)\s*[-–]?\s*\b(play\s*offs?|play\s*outs?|playoffs?|playouts?|finals?\s*series|championship\s*round|relegation\s*round|championship\s*group|relegation\s*group|placement\s*matches|winners\s*stage|losers\s*stage)\b.*$',
        r'(?i)\s*[-–]?\s*\b(relegation|promotion)\b.*$'
    ]
    for pat in playoff_patterns:
        name = re.sub(pat, '', name)
        
    # 2. Remove sufixos de grupos regionais e zonas
    name = re.sub(r'(?i)\s*[-–]?\s*\b(group|grupo|gruppe|poule|zone|zona|section|conference)\s*[a-z0-9]+\b.*$', '', name)
    name = re.sub(r'(?i)\s*[-–]?\s*\b(north|south|east|west|central|interior|capital)\b.*$', '', name)
    
    return name.strip()


def classificar_ligas_do_pais(leagues_list, har_zg_map=None):
    """
    Atribui tipo, modalidade, is_cup e nível às ligas de um país:
    1. Agrupa grupos regionais da mesma divisão no mesmo nível (ex: Serie C Group A, B, C -> Nível 3)
    2. Mantém contagem independente de nível para cada modalidade (Masculino, Feminino, Base).
    """
    if har_zg_map is None:
        har_zg_map = {}
        
    classified = []
    mod_counters = {'M': 1, 'W': 1, 'Y': 1, 'WY': 1}
    mod_base_levels = {'M': {}, 'W': {}, 'Y': {}, 'WY': {}}
    
    for l in leagues_list:
        name = l['league_name']
        path = l.get('path', '')
        url = l.get('url', '')
        
        mod = definir_modalidade(name, path)
        tipo = identificar_tipo(name, path)
        
        # Identifica se é copa (is_cup):
        # 1. Se presente no mapa ZG do Flashscore: ZG=2 -> True, ZG=1 -> False
        # 2. Caso contrário, verifica se o tipo é Copa ou Supercopa
        if path in har_zg_map:
            is_cup = bool(har_zg_map[path] == '2')
        elif url in har_zg_map:
            is_cup = bool(har_zg_map[url] == '2')
        else:
            is_cup = bool(tipo in ["Copa", "Supercopa"])
            
        # Sincroniza tipo se o Flashscore marcou ZG=2 (Copa)
        if is_cup and tipo == "Liga":
            tipo = "Copa"
            
        nivel = None
        principal = False
        mod_key = mod if mod is not None else 'M'
        
        # Apenas ligas regulares de pontos corridos (não-copas) recebem nível ordinal
        if not is_cup and tipo in ["Liga", "Base/Reserva"]:
            base_name = extrair_nome_base_liga(name)
            if base_name in mod_base_levels[mod_key]:
                nivel = mod_base_levels[mod_key][base_name]
            else:
                nivel = mod_counters[mod_key]
                mod_base_levels[mod_key][base_name] = nivel
                mod_counters[mod_key] += 1
                
            if nivel == 1:
                principal = True
            
        classified.append({
            "league_name": name,
            "is_cup": is_cup,
            "tipo": tipo,
            "nivel": nivel,
            "principal": principal,
            "mod": mod,
            "url": l.get('url', f"{BASE_URL}{path}" if path else ""),
            "path": path
        })
        
    return classified


def extrair_ligas_de_pagina_pais(country_path):
    """Busca a página do país/continente e extrai as ligas na ordem canônica do menu."""
    url = f"{BASE_URL}{country_path}"
    req = urllib.request.Request(url, headers=HEADERS)
    raw_leagues = []
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            
            seen_urls = set()
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text(strip=True)
                
                if (href.startswith(country_path) and 
                    href != country_path and
                    href.count('/') >= 4 and 
                    href not in seen_urls and
                    not any(x in href for x in ['standings', 'results', 'fixtures', 'draw', 'archive'])):
                    
                    seen_urls.add(href)
                    league_name = text if text else href.strip('/').split('/')[-1].replace('-', ' ').title()
                    
                    raw_leagues.append({
                        "league_name": league_name,
                        "url": f"{BASE_URL}{href}",
                        "path": href
                    })
    except Exception:
        pass
        
    return raw_leagues


def extrair_menu(har_path="auxiliares/home.har", output_json="auxiliares/paises_ligas.json", expand_leagues=True, max_workers=15):
    if not os.path.exists(har_path):
        print(f"[-] Arquivo nao encontrado: {har_path}")
        return None

    print(f"[*] Lendo: {har_path}...")
    with open(har_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data.get('log', {}).get('entries', [])
    html_content = ""
    for entry in entries:
        req_url = entry.get('request', {}).get('url', '')
        resp_text = entry.get('response', {}).get('content', {}).get('text', '')
        if '/football/' in req_url and resp_text and len(resp_text) > 10000:
            html_content = resp_text
            break

    if not html_content and len(entries) > 0:
        html_content = entries[0].get('response', {}).get('content', {}).get('text', '')

    countries_list = []
    other_competitions_list = []

    start_idx = html_content.find('rawData:')
    if start_idx != -1:
        bracket_start = html_content.find('[', start_idx)
        count = 0
        bracket_end = -1
        for i in range(bracket_start, len(html_content)):
            if html_content[i] == '[':
                count += 1
            elif html_content[i] == ']':
                count -= 1
                if count == 0:
                    bracket_end = i + 1
                    break
        
        if bracket_end != -1:
            try:
                raw_sections = json.loads(html_content[bracket_start:bracket_end])
                for sec in raw_sections:
                    sec_name = sec.get('SCN', '')
                    items = sec.get('SCC', [])
                    for it in items:
                        item_obj = {
                            "id": it.get("MC"),
                            "name": it.get("MCN"),
                            "url": f"{BASE_URL}{it.get('ML')}" if it.get('ML') else None,
                            "path": it.get("ML"),
                            "leagues": []
                        }
                        if sec_name.lower() == "countries":
                            countries_list.append(item_obj)
                        else:
                            other_competitions_list.append(item_obj)
            except Exception as e:
                print(f"[-] Erro ao parsear rawData: {e}")

    # Extrai mapeamento de ZG (Copa vs Liga) presente nos feeds do HAR
    har_zg_map = {}
    for entry in entries:
        text = entry.get('response', {}).get('content', {}).get('text', '')
        if 'ZA' in text:
            for b in re.split(r'~ZA[\xac\xf7\xc3\xb7\xc2\xac÷\ufffd]', text)[1:]:
                m_url = re.search(r'ZL[\xac\xf7÷]([^\xac\xf7÷~]+)', b)
                m_zg = re.search(r'ZG[\xac\xf7÷]([^\xac\xf7÷~]+)', b)
                if m_url and m_zg:
                    har_zg_map[m_url.group(1).strip()] = m_zg.group(1).strip()

    # Se solicitado, busca e expande as ligas de TODOS os países na ordem oficial da federação
    all_targets = countries_list + other_competitions_list
    if expand_leagues:
        print(f"\n[*] Expandindo ligas de {len(all_targets)} paises/continentes (Workers: {max_workers})...")
        
        def _fetch_leagues(item):
            leagues = extrair_ligas_de_pagina_pais(item['path'])
            return item['id'], leagues

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {executor.submit(_fetch_leagues, it): it for it in all_targets}
            done_count = 0
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    c_id, fetched_leagues = future.result()
                    if fetched_leagues:
                        item['leagues'] = classificar_ligas_do_pais(fetched_leagues, har_zg_map)
                except Exception:
                    pass
                done_count += 1
                if done_count % 25 == 0 or done_count == len(all_targets):
                    print(f"   Progresso: {done_count}/{len(all_targets)} processados...")

    total_leagues = sum(len(c['leagues']) for c in countries_list) + sum(len(r['leagues']) for r in other_competitions_list)
    
    result = {
        "metadata": {
            "source": "Flashscore Football Menu",
            "total_countries": len(countries_list),
            "total_other_competitions": len(other_competitions_list),
            "total_leagues_found": total_leagues,
            "base_url": BASE_URL
        },
        "countries": countries_list,
        "other_competitions": other_competitions_list
    }

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"[+] SUCESSO! Menu extraido e salvo em: {output_json}")
    print(f"   * Total de Paises: {len(countries_list)}")
    print(f"   * Total de Outras Competicoes/Continentes: {len(other_competitions_list)}")
    print(f"   * Total de Ligas catalogadas: {total_leagues}")
    print("=" * 80)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrator do Menu Lateral Flashscore")
    parser.add_argument("--har", default="auxiliares/home.har", help="Caminho do arquivo home.har")
    parser.add_argument("--output", default="auxiliares/paises_ligas.json", help="Arquivo JSON de saida")
    parser.add_argument("--expand", action="store_true", default=True, help="Expandir todas as ligas de todos os países online (padrão: True)")
    parser.add_argument("--no-expand", action="store_true", help="Desativar expansão online de ligas")
    parser.add_argument("--workers", type=int, default=20, help="Workers simultâneos para expansão (padrão: 20)")
    args = parser.parse_args()

    should_expand = False if args.no_expand else True

    extrair_menu(
        har_path=args.har, 
        output_json=args.output, 
        expand_leagues=should_expand, 
        max_workers=args.workers
    )