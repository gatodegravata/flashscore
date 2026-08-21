#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlashScore Fast Match Scraper (Versão 2.0 - Ultra-Fast)
Executa scraping multi-threaded de jogos passados usando requisições diretas à API (curl_cffi)
Consome < 5% de CPU e roda 30 a 50x mais rápido que o Selenium!

Uso:
    python scrape_jogos_passados_fast.py --workers 10
    python scrape_jogos_passados_fast.py --proxy --workers 20
"""

import os
import sys
import time
import json
import re
import argparse
import threading
import queue
from datetime import datetime
import pandas as pd

from flashscore_scraper import FlashScoreScraper
from flashscore_api_scraper import FlashScoreAPIScraper
from scrape_jogos_passados import (
    load_existing_data as load_existing_country_data,
    save_country_data,
    get_match_ids_from_league,
    extract_country_from_url,
    extract_league_name_from_url,
    extract_season_from_url
)


def update_execution_log(log_entry, log_file="log.json"):
    """
    Atualiza o arquivo log.json com informações detalhadas e horário de término de cada liga.
    """
    try:
        data = {}
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
                
        if "leagues" not in data or not isinstance(data["leagues"], list):
            data["leagues"] = []
            
        data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Chave única: country + league + season
        key = f"{log_entry.get('country')}_{log_entry.get('league')}_{log_entry.get('season')}"
        idx = next((i for i, l in enumerate(data["leagues"]) if f"{l.get('country')}_{l.get('league')}_{l.get('season')}" == key), None)
        
        if idx is not None:
            data["leagues"][idx] = log_entry
        else:
            data["leagues"].append(log_entry)
            
        data["total_leagues_processed"] = len(data["leagues"])
        
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  ⚠️ Aviso ao atualizar {log_file}: {e}")


def scrape_fast_from_config(config_file="ligas_config.csv", proxy=None, workers=10):
    """
    Executa o scraping rápido com a lista de ligas do CSV.
    """
    print("=" * 90)
    print("🚀 FLASHSCORE FAST SCRAPER 2.0 (Powered by curl_cffi & GraphQL)")
    print("=" * 90)
    print(f"📁 Lendo configurações de: {config_file}")
    print(f"⚡ Threads simultâneas (Workers): {workers}")
    print(f"🛡️  Proxy: {'Ativado' if proxy else 'Conexão Direta'}")
    print("=" * 90)
    
    if not os.path.exists(config_file):
        print(f"❌ Arquivo {config_file} não encontrado!")
        return
        
    df = pd.read_csv(config_file, sep=';', encoding='utf-8-sig')
    df_selecionadas = df[df['baixar'].astype(str).str.upper() == 'S'].copy()
    
    if df_selecionadas.empty:
        print("⚠️ Nenhuma liga com 'S' em ligas_config.csv")
        return

    for idx, row in df_selecionadas.iterrows():
        url = str(row['url']).strip()
        if pd.isna(row.get('pais')) or str(row.get('pais')).strip() in ['', 'nan']:
            df_selecionadas.at[idx, 'pais'] = extract_country_from_url(url)
        if pd.isna(row.get('liga_temporada')) or str(row.get('liga_temporada')).strip() in ['', 'nan']:
            df_selecionadas.at[idx, 'liga_temporada'] = extract_league_name_from_url(url)
        if pd.isna(row.get('temporada')) or str(row.get('temporada')).strip() in ['', 'nan']:
            df_selecionadas.at[idx, 'temporada'] = extract_season_from_url(url)

    output_dir = "jogos_passados"
    os.makedirs(output_dir, exist_ok=True)
    
    # Carrega lista de proxies se fornecido
    proxy_list = []
    if proxy and os.path.exists("proxies.txt"):
        with open("proxies.txt", "r", encoding="utf-8") as f:
            proxy_list = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            
    # Carrega metadados oficiais de temporadas_ligas.json para cruzamento de alta velocidade
    meta_json_path = "auxiliares/temporadas_ligas.json"
    url_lookup = {}
    if os.path.exists(meta_json_path):
        try:
            with open(meta_json_path, 'r', encoding='utf-8') as f_meta:
                data_meta = json.load(f_meta)
            for l in data_meta.get('leagues', []):
                l_name = l.get('league_name')
                c_name = l.get('country_name')
                c_id = l.get('country_id')
                for s in l.get('seasons', []):
                    s_u = s.get('url', '').rstrip('/')
                    info = {
                        'league_name': l_name,
                        'country_name': c_name,
                        'country_id': c_id,
                        'season_name': s.get('season_name'),
                        'tournament_id': s.get('tournament_id'),
                        'stage_id': s.get('stage_id')
                    }
                    if s_u:
                        url_lookup[s_u] = info
                        url_lookup[s_u + '/results'] = info
                    if '/football/' in s_u:
                        slug = s_u.split('/football/')[1].strip('/')
                        url_lookup[slug] = info
                        url_lookup[slug + '/results'] = info
            print(f"📖 {len(url_lookup)} URLs de temporadas mapeadas na memória via {meta_json_path}!")
        except Exception as e_meta:
            print(f"⚠️ Aviso ao carregar {meta_json_path}: {e_meta}")

    # Inicializa navegador headless APENAS para coletar a lista de IDs das ligas (leve e rápido)
    print("\n🌐 Inicializando indexador de ligas...")
    league_indexer = FlashScoreScraper(headless=True, use_cache=False, proxy=proxy)
    league_indexer.accept_cookies()

    start_total_time = datetime.now()
    
    for _, row in df_selecionadas.iterrows():
        t_league_start = datetime.now()
        league_url = str(row['url']).strip()
        league_name = str(row['liga_temporada']).strip()
        country = str(row['pais']).strip()
        season_name = str(row['temporada']).strip()
        
        # Cruzamento direto com os metadados oficiais
        norm_u = league_url.rstrip('/')
        meta_info = url_lookup.get(norm_u) or url_lookup.get(norm_u.replace('/results', ''))
        if not meta_info and '/football/' in norm_u:
            slug_u = norm_u.split('/football/')[1].strip('/')
            meta_info = url_lookup.get(slug_u)
            
        official_sub_name = meta_info.get('league_name') if meta_info else None
        official_season = meta_info.get('season_name') if meta_info else season_name
        official_tid = meta_info.get('tournament_id') if meta_info else None
        
        # Nome limpo do arquivo: usa o alias da divisão (ex: AUSTRALIA 3 -> australia_australia-3_2026)
        country_clean = re.sub(r'[/\\:*?"<>| ]+', '-', country.lower()).strip('-')
        league_clean = re.sub(r'[/\\:*?"<>| ]+', '-', league_name.lower()).strip('-')
        season_clean = re.sub(r'[/\\:*?"<>| ]+', '-', str(season_name).lower()).strip('-')
        base_name = f"{country_clean}_{league_clean}_{season_clean}"
        
        # Extrai o nome real da sub-liga a partir da URL caso não esteja no lookup
        if official_sub_name:
            sub_league_name = official_sub_name
        else:
            parts_url = league_url.split('/football/')
            if len(parts_url) > 1 and len(parts_url[1].split('/')) > 1:
                slug_raw = parts_url[1].split('/')[1]
                slug_clean = re.sub(r'[-_]20\d{2}(?:[-_]20\d{2})?', '', slug_raw).strip('-_')
                sub_league_name = slug_clean.replace('-', ' ').title() if slug_clean else league_name
                # Siglas comuns em maiúsculas
                sub_league_name = re.sub(r'\bNpl\b', 'NPL', sub_league_name, flags=re.IGNORECASE)
                sub_league_name = re.sub(r'\bNsw\b', 'NSW', sub_league_name, flags=re.IGNORECASE)
                sub_league_name = re.sub(r'\bAct\b', 'ACT', sub_league_name, flags=re.IGNORECASE)
                sub_league_name = re.sub(r'\bRfef\b', 'RFEF', sub_league_name, flags=re.IGNORECASE)
            else:
                sub_league_name = league_name
        
        filename = os.path.join(output_dir, f"{base_name}.json")
        zip_filename = f"{filename}.zip"
        
        print("\n" + "🟢" * 45)
        print(f"🏆 LIGA: [{country.upper()}] {league_name} ({season_name}) - Sub: {sub_league_name}")
        print("🟢" * 45)
        
        # Descompacta zip existente se houver
        if os.path.exists(zip_filename) and not os.path.exists(filename):
            try:
                import zipfile
                with zipfile.ZipFile(zip_filename, 'r') as zf:
                    zf.extractall(output_dir)
            except Exception:
                pass

        existing_data = load_existing_country_data(filename)
        if existing_data:
            country_data = existing_data
            if 'leagues' not in country_data or not isinstance(country_data['leagues'], list):
                country_data['leagues'] = []
        else:
            country_data = {
                'country': str(country).upper(),
                'league': league_name,
                'season': str(season_name),
                'scrape_date': datetime.now().isoformat(),
                'total_leagues': 0,
                'leagues': []
            }
            
        # Localiza a sub-liga específica pela URL dentro da lista 'leagues'
        existing_league = None
        norm_target_url = league_url.rstrip('/')
        for l_obj in country_data['leagues']:
            l_url = l_obj.get('url', '').rstrip('/')
            if l_url == norm_target_url or (l_obj.get('name') and l_obj.get('name').lower() == sub_league_name.lower()):
                existing_league = l_obj
                break
                
        if not existing_league:
            existing_league = {
                'name': sub_league_name,
                'tournament_id': official_tid,
                'season': official_season,
                'url': league_url,
                'total_matches': 0,
                'scraped_matches': 0,
                'matches': []
            }
            country_data['leagues'].append(existing_league)
            
        if official_tid and not existing_league.get('tournament_id'):
            existing_league['tournament_id'] = official_tid
        if official_season and not existing_league.get('season'):
            existing_league['season'] = official_season
            
        country_data['total_leagues'] = len(country_data['leagues'])
            
        # Extrai IDs já processados com sucesso do JSON desta sub-liga
        processed_ids = set()
        valid_matches = []
        for m in existing_league.get('matches', []):
            mid = m.get('Match_ID') or m.get('Id')
            if mid:
                processed_ids.add(mid)
                valid_matches.append(m)
                    
        existing_league['matches'] = valid_matches
        existing_league['scraped_matches'] = len(valid_matches)
        
        # Verifica se já existe o CSV consolidado para reutilizar os IDs (dispensa JSON pesado)
        csv_output_dir = "dataframes_jogos_passados"
        os.makedirs(csv_output_dir, exist_ok=True)
        csv_filename = os.path.join(csv_output_dir, f"{base_name}.csv")
        
        if not processed_ids and os.path.exists(csv_filename):
            try:
                df_prev = pd.read_csv(csv_filename, low_memory=False)
                if 'Sub_League' in df_prev.columns:
                    df_sub = df_prev[df_prev['Sub_League'].astype(str).str.lower() == sub_league_name.lower()]
                else:
                    df_sub = df_prev
                    
                for col in ['Match_ID', 'Id', 'id', 'match_id']:
                    if col in df_sub.columns:
                        csv_ids = set(df_sub[col].dropna().astype(str))
                        processed_ids.update(csv_ids)
                        if csv_ids:
                            print(f"  📊 {len(csv_ids)} jogos já salvos desta sub-liga encontrados no CSV consolidado!")
                        break
            except Exception:
                pass
        elif processed_ids:
            print(f"  📄 {len(processed_ids)} jogos já salvos no JSON para {sub_league_name}")
            
        # Coleta IDs e Metadados da liga
        res_match = get_match_ids_from_league(league_indexer, league_url)
        if isinstance(res_match, tuple):
            match_ids, match_metadata = res_match
        else:
            match_ids = res_match
            match_metadata = {}
            
        if not match_ids:
            print("  ⚠️ Nenhum jogo encontrado, pulando...")
            continue
            
        # Captura o Tournament_ID
        current_tournament_id = None
        if match_metadata:
            for m_meta in match_metadata.values():
                if m_meta.get('Tournament_ID'):
                    current_tournament_id = m_meta.get('Tournament_ID')
                    break
        if current_tournament_id:
            existing_league['tournament_id'] = current_tournament_id
            
        existing_league['total_matches'] = len(match_ids)
        new_match_ids = [mid for mid in match_ids if mid not in processed_ids]
        
        if new_match_ids:
            print(f"  ⚡ {len(new_match_ids)} novos jogos para baixar via API direta...")
            
            # Fila de processamento rápido
            work_queue = queue.Queue()
            for mid in new_match_ids:
                work_queue.put(mid)
                
            save_lock = threading.Lock()
            stop_saver = threading.Event()
            
            # Thread de Salvamento Assíncrono em Segundo Plano (Zero Bloqueio nos Workers)
            def background_saver():
                last_saved_count = len(existing_league['matches'])
                while not stop_saver.wait(3.0):
                    with save_lock:
                        curr_count = len(existing_league['matches'])
                        if curr_count > last_saved_count:
                            save_country_data(filename, country_data)
                            last_saved_count = curr_count
                            
            saver_thread = threading.Thread(target=background_saver, daemon=True)
            saver_thread.start()
            
            def api_worker(w_idx):
                w_proxy = proxy_list[w_idx % len(proxy_list)] if proxy_list else None
                scraper_api = FlashScoreAPIScraper(proxy=w_proxy)
                
                while not work_queue.empty():
                    try:
                        m_id = work_queue.get_nowait()
                    except queue.Empty:
                        break
                        
                    try:
                        t0 = time.time()
                        base_info = match_metadata.get(m_id, {"Id": m_id, "Match_ID": m_id})
                        base_info['Sub_League'] = sub_league_name
                        base_info['Season'] = official_season
                        if current_tournament_id:
                            base_info['Tournament_ID'] = current_tournament_id
                            
                        match_res = scraper_api.scrape_match(m_id, base_info=base_info)
                        match_res['Sub_League'] = sub_league_name
                        match_res['Season'] = official_season
                        if current_tournament_id:
                            match_res['Tournament_ID'] = current_tournament_id
                            
                        elapsed = time.time() - t0
                        
                        with save_lock:
                            existing_league['matches'].append(match_res)
                            existing_league['scraped_matches'] = len(existing_league['matches'])
                            curr = len(existing_league['matches'])
                            
                        print(f"  [{curr:3d}/{len(match_ids)}] ✓ [W{w_idx+1}] Match {m_id} ({elapsed:.2f}s) [OK💾]")
                    except Exception as e_w:
                        print(f"  ✗ [W{w_idx+1}] Erro no jogo {m_id}: {e_w}")
                    finally:
                        work_queue.task_done()
                        
            # Dispara as threads de API rápida
            active_threads = []
            pool_size = min(workers, len(new_match_ids))
            for w_i in range(pool_size):
                t = threading.Thread(target=api_worker, args=(w_i,))
                t.daemon = True
                t.start()
                active_threads.append(t)
                
            for t in active_threads:
                t.join()
                
            # Encerra o background saver e aguarda a finalização de qualquer escrita pendente
            stop_saver.set()
            if saver_thread.is_alive():
                saver_thread.join(timeout=5)

            # Salva o estado final consolidado com lock atômico
            with save_lock:
                save_country_data(filename, country_data)
        else:
            print(f"  ✅ Liga já completa ({len(match_ids)} jogos)")
            if os.path.exists(csv_filename):
                continue

        # --- AUTO-GERAÇÃO DO CSV E COMPACTAÇÃO .ZIP DA LIGA ---
        csv_output_dir = "dataframes_jogos_passados"
        os.makedirs(csv_output_dir, exist_ok=True)
        csv_filename = os.path.join(csv_output_dir, f"{base_name}.csv")
        
        print(f"\n📊 Gerando CSV consolidado para [{league_name} - {season_name}]...")
        csv_generated_df = None
        try:
            from generate_df_jogos_passados import generate_dataframe_from_json
            csv_generated_df = generate_dataframe_from_json(filename, csv_filename)
            print(f"  ✓ Planilha criada com sucesso: {csv_filename}")
        except Exception as e_csv:
            print(f"  ⚠️ Erro ao gerar CSV: {e_csv}")
            
        # Compacta o JSON bruto em .zip (economiza 90% de espaço) e remove o .json com segurança
        try:
            import zipfile
            with zipfile.ZipFile(zip_filename, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(filename, arcname=os.path.basename(filename))
            
            # Deleta o JSON pesado em texto plano liberando locks do Windows
            if os.path.exists(filename):
                import gc
                gc.collect()
                deleted = False
                for _ in range(5):
                    try:
                        os.remove(filename)
                        deleted = True
                        break
                    except (PermissionError, OSError):
                        time.sleep(0.1)
                        gc.collect()
                        
            print(f"  🗜️  JSON compactado com segurança: {zip_filename} ({os.path.getsize(zip_filename)/1024:.1f} KB)")
        except Exception as e_zip:
            print(f"  ⚠️ Erro ao compactar JSON: {e_zip}")

        # Registra métricas detalhadas de execução no log.json
        t_league_end = datetime.now()
        csv_ok = os.path.exists(csv_filename)
        json_ok = os.path.exists(zip_filename) or os.path.exists(filename)
        
        matches_list = existing_league.get('matches', [])
        total_scraped = len(matches_list)
        with_odds = sum(1 for m in matches_list if m.get('Odds_1X2_FT') or m.get('Odds_OU_FT'))
        with_stats = sum(1 for m in matches_list if m.get('Statistics_FT'))
        
        csv_rows = len(csv_generated_df) if csv_generated_df is not None else 0
        csv_cols = len(csv_generated_df.columns) if csv_generated_df is not None else 0
                
        league_log = {
            "country": country.upper(),
            "league": league_name,
            "season": season_name,
            "url": league_url,
            "status": "SUCCESS" if (csv_ok and json_ok and total_scraped > 0) else "WARNING",
            "started_at": t_league_start.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": t_league_end.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round((t_league_end - t_league_start).total_seconds(), 2),
            "total_matches_expected": existing_league.get('total_matches', total_scraped),
            "total_matches_scraped": total_scraped,
            "matches_with_odds": with_odds,
            "odds_coverage_pct": f"{(with_odds / total_scraped * 100):.1f}%" if total_scraped > 0 else "0.0%",
            "matches_with_stats": with_stats,
            "stats_coverage_pct": f"{(with_stats / total_scraped * 100):.1f}%" if total_scraped > 0 else "0.0%",
            "json_saved": json_ok,
            "json_zip_path": zip_filename,
            "json_zip_size_kb": round(os.path.getsize(zip_filename)/1024, 1) if os.path.exists(zip_filename) else 0.0,
            "csv_saved": csv_ok,
            "csv_path": csv_filename,
            "csv_rows": csv_rows,
            "csv_cols": csv_cols,
            "csv_size_kb": round(os.path.getsize(csv_filename)/1024, 1) if csv_ok else 0.0
        }
        update_execution_log(league_log)
        print(f"  📝 Relatório gravado em log.json (Término: {league_log['finished_at']})")
                    
    # Limpeza final preventiva de quaisquer .json residuais que já tenham .zip correspondente
    try:
        for fname in os.listdir(output_dir):
            if fname.endswith(".json") and not fname.endswith(".json.zip"):
                j_path = os.path.join(output_dir, fname)
                z_path = f"{j_path}.zip"
                if os.path.exists(z_path) and os.path.getsize(z_path) > 100:
                    try:
                        os.remove(j_path)
                    except Exception:
                        pass
    except Exception:
        pass

    league_indexer.close()
    duration = datetime.now() - start_total_time
    print("\n" + "=" * 90)
    print(f"🎉 SCRAPING RÁPIDO E GERAÇÃO DE CSVS CONCLUÍDOS EM: {duration}")
    print("=" * 90)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FlashScore Fast Match Scraper 2.0")
    parser.add_argument("--config", default="ligas_config.csv", help="Arquivo CSV de ligas")
    parser.add_argument("--workers", type=int, default=10, help="Número de workers simultâneos (padrão: 10)")
    parser.add_argument("--proxy", action="store_true", help="Usar proxies de proxies.txt")
    args = parser.parse_args()
    
    scrape_fast_from_config(config_file=args.config, proxy=args.proxy, workers=args.workers)
