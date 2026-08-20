#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auditor e Conferência de Jogos Coletados Flashscore (Agrupado por Nome Real / Sub_League e URL)
Cruza as ligas de ligas_config.csv com auxiliares/temporadas_ligas.json e a pasta dataframes_jogos_passados.
Gera tabelas dinâmicas por Liga Real x Temporadas com suporte total ao Google Colab.
"""

import os
import sys
import csv
import re
import json
import argparse
import pandas as pd
from datetime import datetime

# Configuração de encoding UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Caminho base do projeto
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def padronizar_temporada(temp_str):
    """Padroniza temporadas duplas para o formato 'AAAA/AAAA' (ex: 2021-2022 -> 2021/2022)"""
    temp_str = str(temp_str).strip()
    m = re.match(r'^(20\d\d)[-_/](20\d\d)$', temp_str)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return temp_str


def carregar_lookup_temporadas(json_path="auxiliares/temporadas_ligas.json"):
    """Carrega metadados oficiais de temporadas_ligas.json mapeando por URL e Slug"""
    if not os.path.isabs(json_path):
        json_path = os.path.join(ROOT_DIR, json_path)
        
    url_map = {}
    if not os.path.exists(json_path):
        print(f"⚠️ Aviso: Metadados '{json_path}' não encontrados. Usando fallback de URL.")
        return url_map

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for l in data.get('leagues', []):
        l_name = l.get('league_name')
        c_name = l.get('country_name')
        root_url = l.get('url', '').rstrip('/')
        
        # Mapeia a URL raiz da liga
        if root_url:
            url_map[root_url] = {'league_name': l_name, 'country_name': c_name}
            url_map[root_url + '/results'] = {'league_name': l_name, 'country_name': c_name}

        for s in l.get('seasons', []):
            s_url = s.get('url', '').rstrip('/')
            s_path = s.get('path', '').rstrip('/')
            t_id = s.get('tournament_id')
            s_name = s.get('season_name')

            info = {
                'league_name': l_name,
                'country_name': c_name,
                'season_name': s_name,
                'tournament_id': t_id,
                'root_url': root_url
            }

            if s_url:
                url_map[s_url] = info
                url_map[s_url + '/results'] = info
            if s_path:
                url_map[s_path] = info
                url_map[s_path + '/results'] = info

            if '/football/' in s_url:
                slug = s_url.split('/football/')[1].strip('/')
                url_map[slug] = info
                url_map[slug + '/results'] = info

    return url_map


def obter_nome_real_e_id(url, liga_alias, url_map):
    """Obtém o nome real oficial da liga cruzando com o json de temporadas"""
    norm_url = url.rstrip('/')
    info = url_map.get(norm_url)
    
    if not info and '/results' not in norm_url:
        info = url_map.get(norm_url + '/results')
        
    if not info and '/football/' in norm_url:
        slug = norm_url.split('/football/')[1].strip('/')
        info = url_map.get(slug)

    if info and info.get('league_name'):
        return info['league_name'], info.get('tournament_id')

    # Fallback caso não encontre no json: extrai do slug da URL
    if '/football/' in norm_url:
        parts = norm_url.split('/football/')[1].split('/')
        if len(parts) > 1 and parts[1]:
            slug_clean = re.sub(r'[-_]20\d{2}(?:[-_]20\d{2})?', '', parts[1]).strip('-_')
            name = slug_clean.replace('-', ' ').title()
            name = re.sub(r'\bNpl\b', 'NPL', name, flags=re.IGNORECASE)
            name = re.sub(r'\bNsw\b', 'NSW', name, flags=re.IGNORECASE)
            name = re.sub(r'\bAct\b', 'ACT', name, flags=re.IGNORECASE)
            name = re.sub(r'\bRfef\b', 'RFEF', name, flags=re.IGNORECASE)
            return name, None

    return liga_alias, None


def conferir_jogos(config_file="ligas_config.csv", csv_dir="dataframes_jogos_passados", meta_json="auxiliares/temporadas_ligas.json"):
    """
    Função principal de conferência.
    Pode ser executada no Google Colab via:
        from auxiliares.conferencia_jogos_coletados import conferir_jogos
        df = conferir_jogos()
        df
    """
    if not os.path.isabs(config_file):
        config_file = os.path.join(ROOT_DIR, config_file)
    if not os.path.isabs(csv_dir):
        csv_dir = os.path.join(ROOT_DIR, csv_dir)

    if not os.path.exists(config_file):
        print(f"❌ Arquivo '{config_file}' não encontrado.")
        return None

    url_map = carregar_lookup_temporadas(meta_json)
    
    print("=" * 95)
    print(f"📊 CONFERÊNCIA DE JOGOS COLETADOS (AGRUPADO POR NOME REAL DA LIGA / URL)")
    print(f"📁 Lendo: {os.path.basename(config_file)} | 📂 CSVs em: {csv_dir}/")
    print("=" * 95)

    registros = []
    # Rastreia quantas temporadas cada liga tem configurada com 'S'
    ligas_temps_configuradas = {}
    
    with open(config_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if not row or len(row) < 5 or row[0].startswith('#'):
                continue
            status, pais, liga_alias, temp, url = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip(), row[4].strip()
            
            if status.upper() != 'S':
                continue

            temp_padrao = padronizar_temporada(temp)
            nome_real_liga, tourn_id = obter_nome_real_e_id(url, liga_alias, url_map)

            # Localização do CSV
            country_clean = re.sub(r'[/\\:*?"<>| ]+', '-', pais.lower()).strip('-')
            league_clean = re.sub(r'[/\\:*?"<>| ]+', '-', liga_alias.lower()).strip('-')
            season_clean = re.sub(r'[/\\:*?"<>| ]+', '-', str(temp).lower()).strip('-')
            base_name = f"{country_clean}_{league_clean}_{season_clean}"
            csv_path = os.path.join(csv_dir, f"{base_name}.csv")

            total_jogos = 0
            if os.path.exists(csv_path):
                try:
                    df_csv = pd.read_csv(csv_path, low_memory=False)
                    
                    # Se tiver coluna Sub_League, filtra os jogos da sub-liga específica
                    if 'Sub_League' in df_csv.columns:
                        df_sub = df_csv[df_csv['Sub_League'].astype(str).str.lower() == nome_real_liga.lower()]
                        total_jogos = len(df_sub) if len(df_sub) > 0 else len(df_csv)
                    else:
                        total_jogos = len(df_csv)
                except Exception:
                    total_jogos = 0

            # URL canônica da liga (sem a temporada) para agrupamento limpo
            url_canonica = re.sub(r'[-_]20\d{2}(?:[-_]20\d{2})?', '', url.rstrip('/')).replace('/results', '') + '/'

            chave_liga = (pais.upper(), nome_real_liga, url_canonica)
            if chave_liga not in ligas_temps_configuradas:
                ligas_temps_configuradas[chave_liga] = set()
            ligas_temps_configuradas[chave_liga].add(temp_padrao)

            registros.append({
                'Country': pais.upper(),
                'Sub_League': nome_real_liga,
                'Season': temp_padrao,
                'Matches': total_jogos,
                'Tournament_ID': tourn_id or '-',
                'League_URL': url_canonica
            })

    if not registros:
        print("⚠️ Nenhuma liga ativa ('S') encontrada para conferência.")
        return None

    df_base = pd.DataFrame(registros)

    # Cria a Matriz Dinâmica (Pivot Table): País + Nome Real da Liga x Temporadas
    pivot = df_base.pivot_table(
        index=['Country', 'Sub_League', 'League_URL'],
        columns='Season',
        values='Matches',
        aggfunc='sum',
        fill_value=0
    )

    # Ordena as colunas de temporadas cronologicamente
    def season_sort_key(s):
        m = re.search(r'\d{4}', str(s))
        return int(m.group(0)) if m else 0

    ordered_cols = sorted(list(pivot.columns), key=season_sort_key)
    pivot = pivot[ordered_cols]

    # Total de jogos coletados
    pivot['TOTAL_JOGOS'] = pivot.sum(axis=1)
    
    # Cálculo preciso do Status baseado nas temporadas configuradas para aquela liga específica
    status_list = []
    for idx_row in pivot.index:
        c, l_name, l_url = idx_row
        temps_esperadas = ligas_temps_configuradas.get((c, l_name, l_url), set())
        total_esperado = len(temps_esperadas)
        
        coletadas = 0
        for t in temps_esperadas:
            if t in pivot.columns and pivot.loc[idx_row, t] > 0:
                coletadas += 1
                
        if coletadas == total_esperado and total_esperado > 0:
            status_list.append(f"✅ Completo ({coletadas}/{total_esperado})")
        elif coletadas > 0:
            status_list.append(f"⚠️ Parcial ({coletadas}/{total_esperado})")
        else:
            status_list.append(f"❌ Pendente (0/{total_esperado})")

    pivot['STATUS'] = status_list

    # Ordena por País e Nome da Liga
    pivot = pivot.sort_index(level=['Country', 'Sub_League'])

    # Resumo Geral
    total_linhas = len(pivot)
    completas = sum(1 for s in pivot['STATUS'] if '✅ Completo' in s)
    parciais = sum(1 for s in pivot['STATUS'] if '⚠️ Parcial' in s)
    pendentes = sum(1 for s in pivot['STATUS'] if '❌ Pendente' in s)
    total_jogos_geral = pivot['TOTAL_JOGOS'].sum()

    print(f"\n" + "📈" * 45)
    print(f"📊 RESUMO DE COBERTURA GERAL")
    print(f"📈" * 45)
    print(f"  • Total de Ligas Auditadas:       {total_linhas}")
    print(f"  • Ligas 100% Coletadas:          {completas} ({(completas/total_linhas*100):.1f}%)")
    print(f"  • Ligas Parcialmente Coletadas:  {parciais} ({(parciais/total_linhas*100):.1f}%)")
    print(f"  • Ligas Pendentes (0 jogos):     {pendentes} ({(pendentes/total_linhas*100):.1f}%)")
    print(f"  • Total de Partidas Coletadas:   {total_jogos_geral:,} jogos")
    print("=" * 95)

    # Imprime no terminal
    print("\n📋 TABELA DINÂMICA DE JOGOS POR LIGA E TEMPORADA:\n")
    pd.set_option('display.max_rows', 500)
    pd.set_option('display.max_columns', 30)
    pd.set_option('display.width', 1000)
    print(pivot.to_string())

    # Converte o MultiIndex para colunas planas (Ideal para visualização interativa no Colab e exportação)
    df_colab = pivot.reset_index()

    # Se estiver no Google Colab, ativa o formatador interativo
    try:
        from google.colab import data_table
        data_table.enable_dataframe_formatter()
    except Exception:
        pass

    return df_colab


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Conferência de Jogos Coletados por Liga Real")
    parser.add_argument("--config", default="ligas_config.csv", help="Caminho do ligas_config.csv")
    parser.add_argument("--csv_dir", default="dataframes_jogos_passados", help="Diretório dos CSVs")
    parser.add_argument("--meta", default="auxiliares/temporadas_ligas.json", help="Caminho do temporadas_ligas.json")
    args = parser.parse_args()

    df_resultado = conferir_jogos(config_file=args.config, csv_dir=args.csv_dir, meta_json=args.meta)
