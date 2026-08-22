#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ ULTRA SCRAPER FLASH - ATUALIZAÇÃO MASSIVA DE JOGOS ⚡
================================================================================
Modo de Operação:
1. Carrega o parquet mestre de jogos consolidados (ou URL do GitHub).
2. Faz o download ultrarrápido via API direta (df_sui, df_st, GraphQL) com N workers.
3. Salva os JSONs brutos completos compactados em ZIPs por lotes (ex: 20.000 jogos por lote)
   garantindo zero sobrecarga de i-nodes no Colab / Linux.
4. Gera simultaneamente o DataFrame tabular consolidado em Parquet e CSV único no final.
5. Permite pausar e continuar de onde parou com total segurança!
================================================================================
"""

import os
import sys
import time
import json
import queue
import zipfile
import threading
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Importa os módulos locais do projeto
from flashscore_api_scraper import FlashScoreAPIScraper
from generate_df_jogos_passados import process_match_to_row


class UltraBatchScraper:
    def __init__(
        self,
        parquet_source: str,
        output_dir: str = "output_dataset",
        batch_size: int = 20000,
        workers: int = 32,
        proxy_file: Optional[str] = None,
        slice_part: Optional[str] = None
    ):
        self.parquet_source = parquet_source
        self.output_dir = output_dir
        self.batch_size = batch_size
        self.workers = workers
        self.proxy_file = proxy_file
        self.slice_part = slice_part
        
        self.zips_dir = os.path.join(self.output_dir, "zips_json_bruto")
        self.checkpoints_dir = os.path.join(self.output_dir, "checkpoints")
        self.final_dir = os.path.join(self.output_dir, "consolidado_final")
        
        os.makedirs(self.zips_dir, exist_ok=True)
        os.makedirs(self.checkpoints_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        
        self.proxies = self._load_proxies()
        self.processed_ids = self._load_already_processed_ids()
        
    def _load_proxies(self) -> List[str]:
        # Carrega proxies apenas se o usuário especificar um arquivo local existente
        if self.proxy_file and os.path.exists(self.proxy_file):
            with open(self.proxy_file, "r", encoding="utf-8") as f:
                proxies = [l.strip() for l in f if l.strip() and not l.startswith("#")]
                if proxies:
                    print(f"🔒 Carregados {len(proxies)} proxies do arquivo local {self.proxy_file}")
                    return proxies
                    
        print("⚡ Rodando com Conexão Direta (Sem proxy).")
        return []

    def _load_already_processed_ids(self) -> set:
        """Lê todos os match_ids já salvos nos checkpoints ou zips concluídos"""
        done = set()
        # 1. Procura em checkpoint de IDs
        cp_file = os.path.join(self.checkpoints_dir, "processed_ids.txt")
        if os.path.exists(cp_file):
            with open(cp_file, "r", encoding="utf-8") as f:
                for line in f:
                    mid = line.strip()
                    if mid:
                        done.add(mid)
        print(f"💾 Checkpoint: {len(done)} partidas já processadas anteriormente.")
        return done

    def _append_processed_id(self, mid: str):
        cp_file = os.path.join(self.checkpoints_dir, "processed_ids.txt")
        with open(cp_file, "a", encoding="utf-8") as f:
            f.write(f"{mid}\n")

    def run(self):
        print("\n" + "=" * 80)
        print("🚀 INICIANDO ULTRA SCRAPER FLASH DE PARTIDAS CONSOLIDADAS")
        print("=" * 80)
        
        # 1. Carrega DataFrame mestre
        print(f"📥 Carregando base mestre de: {self.parquet_source} ...")
        if self.parquet_source.startswith("http://") or self.parquet_source.startswith("https://"):
            df_master = pd.read_parquet(self.parquet_source)
        else:
            df_master = pd.read_parquet(self.parquet_source)
            
        print(f"📊 Total de registros no Parquet Mestre: {len(df_master):,}")
        
        # Identifica coluna de ID
        id_col = 'Match_ID' if 'Match_ID' in df_master.columns else ('Id' if 'Id' in df_master.columns else df_master.columns[0])
        
        # Filtra apenas os IDs pendentes
        df_master = df_master.drop_duplicates(subset=[id_col])
        
        # Divisão da base por fatia/metade (ex: 1/2 ou 2/2) para rodar em múltiplos Colabs
        if self.slice_part:
            try:
                part_idx, total_parts = map(int, self.slice_part.split('/'))
                chunk_len = len(df_master) // total_parts
                start_row = (part_idx - 1) * chunk_len
                end_row = len(df_master) if part_idx == total_parts else part_idx * chunk_len
                df_master = df_master.iloc[start_row:end_row].copy()
                print(f"✂️ Fatia [{self.slice_part}] selecionada: Processando {len(df_master):,} partidas (linhas {start_row:,} até {end_row:,})")
            except Exception as e:
                print(f"⚠️ Erro ao interpretar --slice '{self.slice_part}': {e}. Usando base inteira.")
                
        pending_mask = ~df_master[id_col].astype(str).isin(self.processed_ids)
        df_pending = df_master[pending_mask].copy()
        
        total_pending = len(df_pending)
        print(f"⚡ Partidas pendentes para download via API: {total_pending:,} jogos!")
        
        if total_pending == 0:
            print("✅ Todas as partidas já estão baixadas e atualizadas!")
            self._consolidate_final_output()
            return
            
        # Converte linhas pendentes em dicionários para rápido acesso
        pending_records = df_pending.to_dict(orient="records")
        
        # Divide em lotes (Batches) de `batch_size` para salvar em ZIPs separados
        num_batches = (total_pending + self.batch_size - 1) // self.batch_size
        print(f"📦 As {total_pending:,} partidas serão processadas em {num_batches} lote(s) de até {self.batch_size:,} jogos.")
        
        for batch_idx in range(num_batches):
            start_i = batch_idx * self.batch_size
            end_i = min(start_i + self.batch_size, total_pending)
            batch_records = pending_records[start_i:end_i]
            
            self._process_single_batch(batch_idx + 1, num_batches, batch_records, id_col)
            
        # 4. Consolida o Parquet e CSV final
        self._consolidate_final_output()

    def _process_single_batch(self, batch_num: int, total_batches: int, records: List[Dict[str, Any]], id_col: str):
        print("\n" + "━" * 80)
        print(f"📦 INICIANDO LOTE [{batch_num}/{total_batches}] - {len(records):,} jogos")
        print("━" * 80)
        
        work_queue = queue.Queue()
        for rec in records:
            work_queue.put(rec)
            
        total_in_batch = len(records)
        completed_in_batch = [0]
        batch_results_json = []
        batch_results_rows = []
        lock = threading.Lock()
        
        t_batch_start = time.time()
        
        def worker_thread(w_id: int):
            proxy = self.proxies[w_id % len(self.proxies)] if self.proxies else None
            scraper_api = FlashScoreAPIScraper(proxy=proxy)
            
            while True:
                try:
                    meta = work_queue.get_nowait()
                except queue.Empty:
                    break
                    
                mid = str(meta.get(id_col, '')).strip()
                if not mid:
                    work_queue.task_done()
                    continue
                    
                try:
                    t0 = time.time()
                    base_info = {
                        "Id": mid,
                        "Match_ID": mid,
                        "Date": str(meta.get("Date", "")),
                        "Time": str(meta.get("Time", "")),
                        "Round": str(meta.get("Round", "")),
                        "Home": str(meta.get("Home", "")),
                        "Home_ID": str(meta.get("Home_ID", "")),
                        "Away": str(meta.get("Away", "")),
                        "Away_ID": str(meta.get("Away_ID", "")),
                        "Home_Score": meta.get("Home_Score"),
                        "Away_Score": meta.get("Away_Score"),
                        "Country": str(meta.get("Country", "")),
                        "League": str(meta.get("League", "")),
                        "Season": str(meta.get("Season", "")),
                        "Sub_League": str(meta.get("Sub_League", meta.get("League", ""))),
                        "Tournament_ID": str(meta.get("Tournament_ID", "")),
                        "Neutral_Location": meta.get("Neutral_Location", False)
                    }
                    
                    # 1. Scraping Completo via API (df_sui + df_st + GraphQL)
                    full_match = scraper_api.scrape_match(mid, base_info=base_info)
                    
                    # 2. Converte para a linha tabular oficial (400+ colunas)
                    row_data = process_match_to_row(
                        match_data=full_match,
                        league_name=base_info.get("League", ""),
                        country=base_info.get("Country", ""),
                        season=base_info.get("Season", ""),
                        sub_league=base_info.get("Sub_League"),
                        tournament_id=base_info.get("Tournament_ID")
                    )
                    
                    elapsed = time.time() - t0
                    
                    with lock:
                        batch_results_json.append(full_match)
                        batch_results_rows.append(row_data)
                        self.processed_ids.add(mid)
                        self._append_processed_id(mid)
                        completed_in_batch[0] += 1
                        curr = completed_in_batch[0]
                        
                        if curr % 50 == 0 or curr == total_in_batch:
                            speed = curr / (time.time() - t_batch_start + 0.001)
                            print(f"  [{curr:5d}/{total_in_batch:5d}] ({speed:.1f} j/s) ✓ Match {mid} ({elapsed:.2f}s) -> {base_info['Home']} vs {base_info['Away']}")
                            
                except Exception as e:
                    print(f"  ✗ [W{w_id+1}] Erro no jogo {mid}: {e}")
                finally:
                    work_queue.task_done()
                    
        # Inicia as threads
        threads = []
        num_workers = min(self.workers, total_in_batch)
        for i in range(num_workers):
            t = threading.Thread(target=worker_thread, args=(i,))
            t.daemon = True
            t.start()
            threads.append(t)
            
        for t in threads:
            t.join()
            
        # 3. Salva o Lote em ZIP de JSONs brutos e Parquet parcial
        print(f"\n💾 Salvando artefatos do Lote {batch_num}...")
        
        # A) ZIP com todos os JSONs brutos do lote
        zip_path = os.path.join(self.zips_dir, f"lote_{batch_num:03d}_{len(batch_results_json)}_jogos.zip")
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for m in batch_results_json:
                mid = m.get('Match_ID') or m.get('Id')
                m_str = json.dumps(m, ensure_ascii=False)
                zf.writestr(f"{mid}.json", m_str)
        print(f"  ✓ ZIP de JSONs Brutos: {zip_path}")
        
        # B) Parquet parcial do lote
        df_batch = pd.DataFrame(batch_results_rows)
        part_parquet_path = os.path.join(self.checkpoints_dir, f"part_{batch_num:03d}.parquet")
        df_batch.to_parquet(part_parquet_path, index=False)
        print(f"  ✓ Parquet Parcial: {part_parquet_path}")

    def _consolidate_final_output(self):
        print("\n" + "=" * 80)
        print("🏆 CONSOLIDANDO ARQUIVOS FINAIS (PARQUET & CSV ÚNICO)")
        print("=" * 80)
        
        parquet_parts = [
            os.path.join(self.checkpoints_dir, f)
            for f in sorted(os.listdir(self.checkpoints_dir))
            if f.startswith("part_") and f.endswith(".parquet")
        ]
        
        if not parquet_parts:
            print("⚠️ Nenhum parquet parcial encontrado para consolidar.")
            return
            
        print(f"📂 Combinando {len(parquet_parts)} partes parciais...")
        dfs = [pd.read_parquet(p) for p in parquet_parts]
        df_final = pd.concat(dfs, ignore_index=True)
        
        # Elimina duplicatas se houver
        id_col = 'Match_ID' if 'Match_ID' in df_final.columns else 'Id'
        df_final = df_final.drop_duplicates(subset=[id_col])
        
        final_parquet = os.path.join(self.final_dir, "jogos_consolidados_completo.parquet")
        final_csv = os.path.join(self.final_dir, "jogos_consolidados_completo.csv")
        
        print(f"💾 Gravando Parquet Final ({len(df_final):,} partidas)...")
        df_final.to_parquet(final_parquet, index=False)
        
        print(f"💾 Gravando CSV Final ({len(df_final):,} partidas)...")
        df_final.to_csv(final_csv, index=False, encoding='utf-8')
        
        print("\n" + "=" * 80)
        print("✅ PROCESSO DE ATUALIZAÇÃO CONCLUÍDO COM SUCESSO TOTAL!")
        print(f"📁 Parquet: {final_parquet}")
        print(f"📁 CSV:     {final_csv}")
        print(f"📁 Zips:    {self.zips_dir}")
        print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ultra Scraper Flash de Partidas")
    parser.add_argument(
        "--parquet", 
        type=str, 
        default="https://github.com/gatodegravata/flashscore/raw/main/db/jogos_consolidados.parquet",
        help="Caminho local ou URL do arquivo parquet mestre"
    )
    parser.add_argument("--workers", type=int, default=32, help="Número de threads simultâneas")
    parser.add_argument("--batch-size", type=int, default=20000, help="Quantidade de jogos por lote compactado")
    parser.add_argument("--output-dir", type=str, default="dataset_completo", help="Diretório de saída")
    parser.add_argument("--proxy-file", type=str, default=None, help="Caminho para arquivo de proxies (opcional)")
    parser.add_argument("--slice", type=str, default=None, help="Fatia da base para paralelismo em múltiplos Colabs (ex: '1/2', '2/2', '1/4', '2/4')")
    
    args = parser.parse_args()
    
    scraper = UltraBatchScraper(
        parquet_source=args.parquet,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        workers=args.workers,
        proxy_file=args.proxy_file,
        slice_part=args.slice
    )
    scraper.run()
