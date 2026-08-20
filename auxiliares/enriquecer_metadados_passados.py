#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enriquecedor de Metadados Flashscore (Jogos Passados)
Atualiza arquivos JSON e CSV existentes com:
  - Sub_League (Nome Real da Liga)
  - Tournament_ID (ID oficial do torneio no Flashscore)
Cruzando as URLs de jogos_passados com auxiliares/temporadas_ligas.json
"""

import os
import sys
import json
import zipfile
import re
import argparse
from datetime import datetime

# Garante que a saída do console aceite emojis e caracteres UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Adiciona o diretório raiz do projeto ao sys.path para importar generate_df_jogos_passados
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Importa a função geradora de DataFrames
from generate_df_jogos_passados import generate_dataframe_from_json


def load_seasons_lookup(json_path="auxiliares/temporadas_ligas.json"):
    """
    Carrega temporadas_ligas.json e cria índices rápidos por URL e por Slug
    """
    if not os.path.exists(json_path):
        print(f"❌ Erro: Arquivo {json_path} não encontrado!")
        sys.exit(1)
        
    print(f"📖 Carregando base de metadados de {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    url_map = {}
    slug_map = {}
    
    for l in data.get('leagues', []):
        l_name = l.get('league_name')
        c_name = l.get('country_name')
        
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
                'url': s_url
            }
            
            if s_url:
                url_map[s_url] = info
                url_map[s_url + '/results'] = info
            if s_path:
                url_map[s_path] = info
                url_map[s_path + '/results'] = info
                
            if '/football/' in s_url:
                slug = s_url.split('/football/')[1].strip('/')
                slug_map[slug] = info
                slug_map[slug + '/results'] = info
                
    print(f"✓ {len(url_map)} URLs mapeadas com sucesso!")
    return url_map, slug_map


def get_league_info_from_url(league_url, url_map, slug_map):
    """
    Retorna as informações da liga (nome real e tournament_id) a partir da URL
    """
    if not league_url:
        return None
        
    norm_url = league_url.rstrip('/')
    if norm_url in url_map:
        return url_map[norm_url]
    if norm_url + '/results' in url_map:
        return url_map[norm_url + '/results']
        
    # Busca por slug
    if '/football/' in norm_url:
        slug = norm_url.split('/football/')[1].strip('/')
        if slug in slug_map:
            return slug_map[slug]
        if slug + '/results' in slug_map:
            return slug_map[slug + '/results']
            
    return None


def enrich_historical_data(input_dir="jogos_passados", output_csv_dir="dataframes_jogos_passados", 
                           temporadas_json="auxiliares/temporadas_ligas.json"):
    """
    Varre todos os JSONs/JSON.ZIPs e CSVs existentes e injeta Sub_League e Tournament_ID
    """
    if not os.path.exists(input_dir):
        print(f"❌ Diretório de entrada {input_dir} não encontrado.")
        return

    os.makedirs(output_csv_dir, exist_ok=True)
    url_map, slug_map = load_seasons_lookup(temporadas_json)
    
    # Lista arquivos
    all_files = sorted(os.listdir(input_dir))
    json_or_zip_files = [f for f in all_files if f.endswith('.json') or f.endswith('.json.zip')]
    
    print("\n" + "=" * 90)
    print(f"🚀 INICIANDO ENRIQUECIMENTO DE METADADOS ({len(json_or_zip_files)} arquivos)")
    print("=" * 90)
    
    updated_count = 0
    t_start = datetime.now()
    
    for idx, fname in enumerate(json_or_zip_files, 1):
        file_path = os.path.join(input_dir, fname)
        base_name = fname.replace('.json.zip', '').replace('.json', '')
        
        raw_json_path = os.path.join(input_dir, f"{base_name}.json")
        zip_path = os.path.join(input_dir, f"{base_name}.json.zip")
        csv_path = os.path.join(output_csv_dir, f"{base_name}.csv")
        
        # Carrega dados do JSON (descompactando se for zip)
        json_data = None
        is_zip = fname.endswith('.json.zip')
        
        try:
            if is_zip:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    internal_name = zf.namelist()[0]
                    json_data = json.load(zf.open(internal_name))
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
        except Exception as e:
            print(f"[{idx}/{len(json_or_zip_files)}] ✗ Erro ao ler {fname}: {e}")
            continue
            
        if not json_data or 'leagues' not in json_data:
            continue
            
        # Atualiza as sub-ligas e partidas
        modified = False
        for league_obj in json_data.get('leagues', []):
            l_url = league_obj.get('url', '')
            info = get_league_info_from_url(l_url, url_map, slug_map)
            
            real_name = info['league_name'] if info else league_obj.get('name')
            tourn_id = info['tournament_id'] if info else league_obj.get('tournament_id')
            
            if real_name and league_obj.get('name') != real_name:
                league_obj['name'] = real_name
                modified = True
            if tourn_id and league_obj.get('tournament_id') != tourn_id:
                league_obj['tournament_id'] = tourn_id
                modified = True
                
            # Atualiza cada partida
            for m in league_obj.get('matches', []):
                if real_name and m.get('Sub_League') != real_name:
                    m['Sub_League'] = real_name
                    modified = True
                if tourn_id and m.get('Tournament_ID') != tourn_id:
                    m['Tournament_ID'] = tourn_id
                    modified = True
                    
        # Salva o JSON enriquecido e atualiza o ZIP
        temp_extracted = False
        try:
            with open(raw_json_path, 'w', encoding='utf-8') as f_out:
                json.dump(json_data, f_out, ensure_ascii=False, indent=2)
            temp_extracted = True
            
            # Re-compacta em ZIP
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                zf.write(raw_json_path, arcname=f"{base_name}.json")
                
            if temp_extracted and os.path.exists(raw_json_path):
                os.remove(raw_json_path)
                
            # Regenera o CSV consolidado com as novas colunas
            generate_dataframe_from_json(zip_path, csv_path)
            
            updated_count += 1
            print(f"[{idx:3d}/{len(json_or_zip_files)}] ✓ {base_name} -> Sub_League & Tournament_ID OK! 💾")
        except Exception as e_save:
            print(f"[{idx:3d}/{len(json_or_zip_files)}] ✗ Erro ao salvar {base_name}: {e_save}")
            if temp_extracted and os.path.exists(raw_json_path):
                try:
                    os.remove(raw_json_path)
                except Exception:
                    pass

    duration = datetime.now() - t_start
    print("\n" + "=" * 90)
    print(f"🎉 ENRIQUECIMENTO CONCLUÍDO COM SUCESSO!")
    print(f"✓ Total de arquivos atualizados: {updated_count} de {len(json_or_zip_files)}")
    print(f"⏱️ Tempo total: {duration}")
    print("=" * 90)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enriquecedor de Metadados Flashscore")
    parser.add_argument("--json_dir", default="jogos_passados", help="Diretório dos JSONs")
    parser.add_argument("--csv_dir", default="dataframes_jogos_passados", help="Diretório dos CSVs")
    parser.add_argument("--meta", default="auxiliares/temporadas_ligas.json", help="Caminho do temporadas_ligas.json")
    args = parser.parse_args()
    
    enrich_historical_data(input_dir=args.json_dir, output_csv_dir=args.csv_dir, temporadas_json=args.meta)
