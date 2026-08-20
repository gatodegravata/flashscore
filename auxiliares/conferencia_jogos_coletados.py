#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auditor e Conferência de Jogos Coletados Flashscore
Varre ligas marcadas com 'S' em ligas_config.csv e audita a pasta dataframes_jogos_passados.
Gera relatórios estatísticos e tabelas dinâmicas estilo Google Colab / Pandas.
"""

import os
import sys
import csv
import re
import pandas as pd
from datetime import datetime

# Garante suporte a UTF-8 no terminal Windows/Linux/Colab
sys.stdout.reconfigure(encoding='utf-8')

def extract_sub_league_from_url(league_url, default_name):
    """Extrai o nome real/sub-liga a partir da URL"""
    if not league_url:
        return default_name
    parts_url = league_url.split('/football/')
    if len(parts_url) > 1 and len(parts_url[1].split('/')) > 1:
        slug_raw = parts_url[1].split('/')[1]
        slug_clean = re.sub(r'[-_]20\d{2}(?:[-_]20\d{2})?', '', slug_raw).strip('-_')
        sub_name = slug_clean.replace('-', ' ').title() if slug_clean else default_name
        sub_name = re.sub(r'\bNpl\b', 'NPL', sub_name, flags=re.IGNORECASE)
        sub_name = re.sub(r'\bNsw\b', 'NSW', sub_name, flags=re.IGNORECASE)
        sub_name = re.sub(r'\bAct\b', 'ACT', sub_name, flags=re.IGNORECASE)
        sub_name = re.sub(r'\bRfef\b', 'RFEF', sub_name, flags=re.IGNORECASE)
        return sub_name
    return default_name


def audit_collected_matches(config_file="ligas_config.csv", csv_dir="dataframes_jogos_passados"):
    """
    Varre as ligas configuradas com status 'S' e confere os jogos salvos em CSV
    """
    if not os.path.exists(config_file):
        print(f"❌ Arquivo de configuração '{config_file}' não encontrado.")
        return

    print("=" * 100)
    print(f"📊 AUDITORIA DE JOGOS COLETADOS FLASHSCORE")
    print(f"📁 Configuração: {config_file} | 📂 Diretório CSVs: {csv_dir}/")
    print("=" * 100)

    records = []
    
    with open(config_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if not row or len(row) < 5 or row[0].startswith('#'):
                continue
            status, pais, liga, temp, url = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip(), row[4].strip()
            
            if status.upper() != 'S':
                continue

            country_clean = re.sub(r'[/\\:*?"<>| ]+', '-', pais.lower()).strip('-')
            league_clean = re.sub(r'[/\\:*?"<>| ]+', '-', liga.lower()).strip('-')
            season_clean = re.sub(r'[/\\:*?"<>| ]+', '-', str(temp).lower()).strip('-')
            base_name = f"{country_clean}_{league_clean}_{season_clean}"
            csv_path = os.path.join(csv_dir, f"{base_name}.csv")
            
            sub_league = extract_sub_league_from_url(url, liga)
            
            total_jogos = 0
            jogos_com_odds = 0
            data_min = "-"
            data_max = "-"
            status_coleta = "❌ Pendente"

            if os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path, low_memory=False)
                    
                    # Se tiver coluna Sub_League, filtra apenas os jogos dessa sub-liga
                    if 'Sub_League' in df.columns:
                        df_sub = df[df['Sub_League'].astype(str).str.lower() == sub_league.lower()]
                        if len(df_sub) == 0: # fallback
                            df_sub = df
                    else:
                        df_sub = df

                    total_jogos = len(df_sub)
                    
                    if total_jogos > 0:
                        status_coleta = "✅ Coletado"
                        
                        # Verifica cobertura de odds
                        odd_cols = [c for c in ['Odds_1X2_FT_H', 'Odds_1X2_H', 'Home_Odds'] if c in df_sub.columns]
                        if odd_cols:
                            jogos_com_odds = int(df_sub[odd_cols[0]].notna().sum())
                        else:
                            jogos_com_odds = total_jogos

                        # Extrai intervalo de datas
                        if 'Date' in df_sub.columns:
                            valid_dates = df_sub['Date'].dropna()
                            if len(valid_dates) > 0:
                                data_min = str(valid_dates.iloc[0])
                                data_max = str(valid_dates.iloc[-1])
                except Exception as e:
                    status_coleta = f"⚠️ Erro Leitura ({str(e)[:15]})"

            records.append({
                'Country': pais.upper(),
                'League_Alias': liga,
                'Sub_League': sub_league,
                'Season': temp,
                'Status': status_coleta,
                'Matches': total_jogos,
                'Matches_With_Odds': jogos_com_odds,
                'First_Date': data_min,
                'Last_Date': data_max,
                'CSV_File': f"{base_name}.csv",
                'URL': url
            })

    if not records:
        print("⚠️ Nenhuma liga com status 'S' encontrada no arquivo.")
        return None

    df_report = pd.DataFrame(records)

    # Estatísticas Globais
    total_ligas = len(df_report)
    ligas_coletadas = len(df_report[df_report['Status'] == '✅ Coletado'])
    total_jogos_geral = df_report['Matches'].sum()
    total_odds_geral = df_report['Matches_With_Odds'].sum()
    pct_cobertura = (total_odds_geral / total_jogos_geral * 100) if total_jogos_geral > 0 else 0

    print("\n" + "📈" * 40)
    print(f"📊 RESUMO GERAL DA BASE DE DADOS")
    print(f"📈" * 40)
    print(f"  • Total de Ligas Selecionadas (Status S): {total_ligas}")
    print(f"  • Ligas com CSVs Coletados:               {ligas_coletadas} / {total_ligas} ({(ligas_coletadas/total_ligas*100):.1f}%)")
    print(f"  • Total de Jogos Armazenados:            {total_jogos_geral:,} jogos")
    print(f"  • Jogos com Odds Completas:              {total_odds_geral:,} ({pct_cobertura:.1f}%)")
    print("=" * 100)

    # TABELA DINÂMICA (PIVOT TABLE) ESTILO GOOGLE COLAB / EXCEL
    print("\n" + "📋" * 40)
    print("📋 TABELA DINÂMICA: TOTAL DE JOGOS POR PAÍS E TEMPORADA")
    print("📋" * 40)
    
    pivot_pais_temp = df_report.pivot_table(
        index=['Country', 'League_Alias'],
        columns='Season',
        values='Matches',
        aggfunc='sum',
        fill_value=0,
        margins=True,
        margins_name='TOTAL GERAL'
    )
    print(pivot_pais_temp.to_string())

    # SEGUNDA TABELA DINÂMICA: STATUS DE COBERTURA
    print("\n" + "📋" * 40)
    print("📋 TABELA DINÂMICA: STATUS DE COLETA POR PAÍS")
    print("📋" * 40)
    
    pivot_status = df_report.pivot_table(
        index='Country',
        columns='Status',
        values='League_Alias',
        aggfunc='count',
        fill_value=0,
        margins=True,
        margins_name='TOTAL'
    )
    print(pivot_status.to_string())

    # Habilita interatividade rica se estiver rodando no Google Colab
    try:
        from google.colab import data_table
        data_table.enable_dataframe_formatter()
        print("\n✨ Google Colab Data Table ativado! Exibindo tabela interativa...")
    except ImportError:
        pass

    return df_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auditor e Conferência de Jogos Coletados")
    parser.add_argument("--config", default="ligas_config.csv", help="Caminho do arquivo ligas_config.csv")
    parser.add_argument("--csv_dir", default="dataframes_jogos_passados", help="Diretório dos CSVs")
    args = parser.parse_args()

    # Se executado a partir de outra pasta, ajusta os caminhos relativos
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_p = os.path.join(root_dir, args.config) if not os.path.exists(args.config) else args.config
    csv_d = os.path.join(root_dir, args.csv_dir) if not os.path.exists(args.csv_dir) else args.csv_dir

    df_resultado = audit_collected_matches(config_file=config_p, csv_dir=csv_d)
