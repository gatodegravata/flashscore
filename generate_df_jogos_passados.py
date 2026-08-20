#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de DataFrame para Jogos Passados (All Seasons)
Converte JSON de jogos históricos em DataFrame tabular

Baseado no gerador de jogos futuros, mas adiciona:
- Placar final (Home_Score, Away_Score)
- Minutos dos gols (Min_Goals_Home, Min_Goals_Away)
- Estatísticas FT, HT e 2T

Regras de Odds:
- Bookie preferencial: Bet365 > Betfair > Primeiro disponível
- Um jogo por linha
- Odds: 1X2 HT/FT, O/U HT (0.5, 1.5, 2.5), O/U FT (0.5-4.5), BTTS, DC
"""

import json
import os
import sys
import re
from datetime import datetime
import pandas as pd
from pathlib import Path
from league_mapping import standardize_league_name

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def find_best_bookmaker(odds_list, prefer=['bet365', 'betfair', 'pinnacle']):
    """
    Procura pela casa de apostas preferencial na lista:
    1. Prioriza Bet365
    2. Se não houver, prioriza Betfair
    3. Fallback: Seleciona a casa com a maior odd (maior valor) disponível no mercado
    """
    if not odds_list or not isinstance(odds_list, list):
        return None
    
    # 1 e 2: Procura pelas casas preferenciais em ordem (bet365, betfair)
    for preferred in prefer:
        for odd_data in odds_list:
            if isinstance(odd_data, dict):
                bookmaker = odd_data.get('Bookmaker', '').lower()
                if preferred in bookmaker:
                    return odd_data
    
    # 3. Fallback: Procura a casa com a maior odd disponível
    valid_entries = [o for o in odds_list if isinstance(o, dict)]
    if not valid_entries:
        return None
        
    def _score_entry(entry):
        vals = [v for k, v in entry.items() if k != 'Bookmaker' and isinstance(v, (int, float)) and v > 1.0]
        return max(vals) if vals else 0.0

    return max(valid_entries, key=_score_entry)


def extract_ou_line(ou_data, line, prefer=['bet365', 'betfair', 'pinnacle']):
    """
    Extrai odds Over/Under de uma linha específica
    Retorna (bookmaker, over, under)
    """
    if not ou_data or not isinstance(ou_data, dict):
        return None, None, None
    
    key = f"OU_{line}"
    if key not in ou_data:
        return None, None, None
    
    odds_list = ou_data[key]
    if not odds_list or not isinstance(odds_list, list):
        return None, None, None
    
    # Procura pela casa preferencial
    best_odd = find_best_bookmaker(odds_list, prefer)
    
    if best_odd:
        return (
            best_odd.get('Bookmaker'),
            best_odd.get('Over'),
            best_odd.get('Under')
        )
    
    return None, None, None


def extract_correct_score(cs_data, score, prefer=['bet365', 'betfair', 'pinnacle']):
    """
    Extrai odd de um placar específico (ex: "1-0", "2-1")
    Retorna (bookmaker, odd)
    """
    if not cs_data or not isinstance(cs_data, dict):
        return None, None
    
    if score not in cs_data:
        return None, None
    
    odds_list = cs_data[score]
    if not odds_list or not isinstance(odds_list, list):
        return None, None
    
    best_odd = find_best_bookmaker(odds_list, prefer)
    
    if best_odd:
        return best_odd.get('Bookmaker'), best_odd.get('Odd')
    
    return None, None


def extract_asian_handicap_line(ah_data, line, prefer=['bet365', 'betfair', 'pinnacle']):
    """
    Extrai odds Asian Handicap de uma linha específica (ex: -1.5, 0.0, +1.5)
    Retorna (bookmaker, home, away)
    """
    if not ah_data or not isinstance(ah_data, dict):
        return None, None, None
    
    # O JSON salva com prefixo "AH_"
    key = f"AH_{line}"
    if key not in ah_data:
        return None, None, None
    
    odds_list = ah_data[key]
    if not odds_list or not isinstance(odds_list, list):
        return None, None, None
    
    best_odd = find_best_bookmaker(odds_list, prefer)
    
    if best_odd:
        return (
            best_odd.get('Bookmaker'),
            best_odd.get('Home'),
            best_odd.get('Away')
        )
    
    return None, None, None


def extract_european_handicap_line(eh_data, line, prefer=['bet365', 'betfair', 'pinnacle']):
    """
    Extrai odds European Handicap de uma linha específica (ex: -2, 0, +2)
    Retorna (bookmaker, home, draw, away)
    """
    if not eh_data or not isinstance(eh_data, dict):
        return None, None, None, None
    
    # O JSON salva com prefixo "EH_"
    key = f"EH_{line}"
    if key not in eh_data:
        return None, None, None, None
    
    odds_list = eh_data[key]
    if not odds_list or not isinstance(odds_list, list):
        return None, None, None, None
    
    best_odd = find_best_bookmaker(odds_list, prefer)
    
    if best_odd:
        return (
            best_odd.get('Bookmaker'),
            best_odd.get('Home'),
            best_odd.get('Draw'),
            best_odd.get('Away')
        )
    
    return None, None, None, None


def extract_dnb(dnb_list, prefer=['bet365', 'betfair', 'pinnacle']):
    """
    Extrai odds Draw No Bet (Empate Anula Aposta)
    Retorna (bookmaker, home, away)
    """
    if not dnb_list or not isinstance(dnb_list, list):
        return None, None, None
    best_odd = find_best_bookmaker(dnb_list, prefer)
    if best_odd:
        return (
            best_odd.get('Bookmaker'),
            best_odd.get('Home'),
            best_odd.get('Away')
        )
    return None, None, None


def extract_ht_ft(ht_ft_data, selection, prefer=['bet365', 'betfair', 'pinnacle']):
    """
    Extrai odds Intervalo / Final do Jogo (ex: 1_1, X_1, 2_2)
    Retorna (bookmaker, odd)
    """
    if not ht_ft_data or not isinstance(ht_ft_data, dict):
        return None, None
    if selection not in ht_ft_data:
        return None, None
    odds_list = ht_ft_data[selection]
    if not odds_list or not isinstance(odds_list, list):
        return None, None
    best_odd = find_best_bookmaker(odds_list, prefer)
    if best_odd:
        return best_odd.get('Bookmaker'), best_odd.get('Odd')
    return None, None


def extract_odd_even(oe_list, prefer=['bet365', 'betfair', 'pinnacle']):
    """
    Extrai odds Ímpar / Par (Odd / Even)
    Retorna (bookmaker, odd, even)
    """
    if not oe_list or not isinstance(oe_list, list):
        return None, None, None
    best_odd = find_best_bookmaker(oe_list, prefer)
    if best_odd:
        return (
            best_odd.get('Bookmaker'),
            best_odd.get('Odd'),
            best_odd.get('Even')
        )
    return None, None, None


def parse_leg_info(note_str, home_score=None, away_score=None):
    """
    Extrai informações de mata-mata / primeira perna a partir de anotações do Flashscore (DM / AM).
    Retorna:
      - LegMatch: 1 (ida), 2 (volta), None (jogo único / pontos corridos)
      - First_Leg_Home_Score: Gols que o mandante atual fez no jogo de ida (como visitante)
      - First_Leg_Away_Score: Gols que o visitante atual fez no jogo de ida (como mandante)
      - Agg_Home_Score: Gols totais do mandante no agregado
      - Agg_Away_Score: Gols totais do visitante no agregado
    """
    if not note_str:
        return {'LegMatch': None, 'First_Leg_Home_Score': None, 'First_Leg_Away_Score': None, 'Agg_Home_Score': None, 'Agg_Away_Score': None}
    
    note_str = str(note_str).strip()
    
    # Caso 1: Jogo de Ida ('First leg.' ou '1st leg')
    if re.search(r'First leg\b(?!\s*result)', note_str, re.IGNORECASE) or re.search(r'1st leg\b(?!\s*result)', note_str, re.IGNORECASE):
        return {
            'LegMatch': 1,
            'First_Leg_Home_Score': None,
            'First_Leg_Away_Score': None,
            'Agg_Home_Score': None,
            'Agg_Away_Score': None
        }
        
    # Caso 2: Jogo de Volta ('First leg result: X-Y. Aggregate: A-B.')
    m_res = re.search(r'(?:First|1st)\s*leg\s*result:\s*(\d+)-(\d+)', note_str, re.IGNORECASE)
    m_agg = re.search(r'Aggregate:\s*(\d+)-(\d+)', note_str, re.IGNORECASE)
    
    if m_res or m_agg:
        agg_h, agg_a = None, None
        first_h, first_a = None, None
        
        if m_agg:
            agg_h = int(m_agg.group(1))
            agg_a = int(m_agg.group(2))
            if home_score is not None:
                first_h = agg_h - int(home_score)
            if away_score is not None:
                first_a = agg_a - int(away_score)
                
        if first_h is None and m_res:
            # No resultado da ida X-Y: X foi o mandante da ida (visitante atual), Y foi o visitante da ida (mandante atual)
            first_a = int(m_res.group(1))
            first_h = int(m_res.group(2))
            if agg_h is None and home_score is not None:
                agg_h = first_h + int(home_score)
            if agg_a is None and away_score is not None:
                agg_a = first_a + int(away_score)
                
        return {
            'LegMatch': 2,
            'First_Leg_Home_Score': first_h,
            'First_Leg_Away_Score': first_a,
            'Agg_Home_Score': agg_h,
            'Agg_Away_Score': agg_a
        }
        
    return {'LegMatch': None, 'First_Leg_Home_Score': None, 'First_Leg_Away_Score': None, 'Agg_Home_Score': None, 'Agg_Away_Score': None}


def process_match_to_row(match_data, league_name, country, season, prefer_bookmakers=['bet365', 'betfair', 'pinnacle'], sub_league=None, tournament_id=None):
    """
    Converte dados de um jogo em uma linha de DataFrame
    """
    row = {}
    
    # Informações básicas
    row['Match_ID'] = match_data.get('Match_ID', match_data.get('Id'))
    row['Country'] = country
    row['Season'] = season
    
    # Div = nome/alias da divisão (ex: "AUSTRALIA 3" ou "Torneo Betano 2024")
    row['Div'] = league_name
    
    # Sub_League = nome real individual da liga (ex: "NPL NSW", "Primera RFEF Group 1")
    row['Sub_League'] = sub_league or match_data.get('Sub_League') or match_data.get('Tournament_Name') or league_name
    
    # Tournament_ID = código oficial de 8 caracteres do torneio no Flashscore (ex: "IDVz16ES")
    row['Tournament_ID'] = tournament_id or match_data.get('Tournament_ID') or match_data.get('tournament_id')
    
    # League = nome padronizado (ex: "AUSTRALIA 3")
    row['League'] = standardize_league_name(country=country, league=league_name)
    
    # Formatação de Data para DD/MM/AAAA
    raw_date = match_data.get('Date')
    formatted_date = raw_date
    if raw_date and isinstance(raw_date, str):
        if '-' in raw_date:
            parts = raw_date.split('-')
            if len(parts) == 3:
                formatted_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
        elif '.' in raw_date:
            parts = raw_date.split('.')
            if len(parts) == 3:
                formatted_date = f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"
            elif len(parts) == 2:
                day = int(parts[0])
                month = int(parts[1])
                # Quando o Flashscore omite o ano, refere-se invariavelmente ao ano corrente
                current_year = datetime.now().year
                formatted_date = f"{day:02d}/{month:02d}/{current_year}"
                
    # Limpeza de nomes de times (remove textos de playoff como 'Advancing to next round')
    def clean_team_name(name):
        if not name:
            return name
        name = re.sub(r'Advancing to next round.*$', '', str(name), flags=re.IGNORECASE).strip()
        name = re.sub(r'Winner:.*$', '', name, flags=re.IGNORECASE).strip()
        return name

    row['Date'] = formatted_date
    row['Time'] = match_data.get('Time')
    row['Round'] = match_data.get('Round')
    row['Home'] = clean_team_name(match_data.get('Home'))
    row['Home_ID'] = match_data.get('Home_ID')
    row['Away'] = clean_team_name(match_data.get('Away'))
    row['Away_ID'] = match_data.get('Away_ID')
    row['Neutral_Location'] = bool(match_data.get('Neutral_Location', match_data.get('Is_Neutral', False)))
    
    # === PLACAR FINAL (NOVO!) ===
    row['Home_Score'] = match_data.get('Home_Score')
    row['Away_Score'] = match_data.get('Away_Score')
    
    # === INFORMAÇÕES DE MATA-MATA / CONFRONTO DE 2 JOGOS ===
    note_str = match_data.get('Match_Note') or match_data.get('DM') or match_data.get('AM') or ''
    leg_data = parse_leg_info(note_str, row['Home_Score'], row['Away_Score'])
    row['LegMatch'] = leg_data['LegMatch']
    row['First_Leg_Home_Score'] = leg_data['First_Leg_Home_Score']
    row['First_Leg_Away_Score'] = leg_data['First_Leg_Away_Score']
    row['Agg_Home_Score'] = leg_data['Agg_Home_Score']
    row['Agg_Away_Score'] = leg_data['Agg_Away_Score']
    
    # === MINUTOS DOS GOLS (NOVO!) ===
    min_goals_home = match_data.get('Min_Goals_Home', [])
    min_goals_away = match_data.get('Min_Goals_Away', [])
    
    # Mantém como lista (será salvo como string no CSV mas pode ser parseado de volta)
    row['Min_Goals_Home'] = min_goals_home if isinstance(min_goals_home, list) else []
    row['Min_Goals_Away'] = min_goals_away if isinstance(min_goals_away, list) else []
    
    # === MATCH ODDS HALF TIME (1X2 HT) ===
    odds_1x2_ht = match_data.get('Odds_1X2_HT', [])
    best_ht = find_best_bookmaker(odds_1x2_ht, prefer_bookmakers)
    
    if best_ht:
        row['Bookie_1X2_HT'] = best_ht.get('Bookmaker')
        row['Odd_1_HT'] = best_ht.get('Odd_1', 0)
        row['Odd_X_HT'] = best_ht.get('Odd_X', 0)
        row['Odd_2_HT'] = best_ht.get('Odd_2', 0)
    else:
        row['Bookie_1X2_HT'] = None
        row['Odd_1_HT'] = 0
        row['Odd_X_HT'] = 0
        row['Odd_2_HT'] = 0
        
    # === MATCH ODDS 2ND HALF (1X2 2T) ===
    odds_1x2_2t = match_data.get('Odds_1X2_2T', [])
    best_2t = find_best_bookmaker(odds_1x2_2t, prefer_bookmakers)
    
    if best_2t:
        row['Bookie_1X2_2T'] = best_2t.get('Bookmaker')
        row['Odd_1_2T'] = best_2t.get('Odd_1', 0)
        row['Odd_X_2T'] = best_2t.get('Odd_X', 0)
        row['Odd_2_2T'] = best_2t.get('Odd_2', 0)
    else:
        row['Bookie_1X2_2T'] = None
        row['Odd_1_2T'] = 0
        row['Odd_X_2T'] = 0
        row['Odd_2_2T'] = 0
    
    # === MATCH ODDS FULL TIME (1X2 FT) ===
    odds_1x2_ft = match_data.get('Odds_1X2_FT', [])
    best_ft = find_best_bookmaker(odds_1x2_ft, prefer_bookmakers)
    
    if best_ft:
        row['Bookie_1X2_FT'] = best_ft.get('Bookmaker')
        row['Odd_1_FT'] = best_ft.get('Odd_1', 0)
        row['Odd_X_FT'] = best_ft.get('Odd_X', 0)
        row['Odd_2_FT'] = best_ft.get('Odd_2', 0)
    else:
        row['Bookie_1X2_FT'] = None
        row['Odd_1_FT'] = 0
        row['Odd_X_FT'] = 0
        row['Odd_2_FT'] = 0
    
    # === OVER/UNDER HALF TIME (0.5, 1.5, 2.5) ===
    ou_ht = match_data.get('Odds_OU_HT', {})
    
    for line in [0.5, 1.5, 2.5]:
        bookie, over, under = extract_ou_line(ou_ht, line, prefer_bookmakers)
        line_str = str(line).replace('.', '_')
        row[f'Bookie_OU_HT_{line_str}'] = bookie
        row[f'Over_HT_{line_str}'] = over if over is not None else 0
        row[f'Under_HT_{line_str}'] = under if under is not None else 0
        
    # === OVER/UNDER 2ND HALF (0.5, 1.5, 2.5) ===
    ou_2t = match_data.get('Odds_OU_2T', {})
    
    for line in [0.5, 1.5, 2.5]:
        bookie, over, under = extract_ou_line(ou_2t, line, prefer_bookmakers)
        line_str = str(line).replace('.', '_')
        row[f'Bookie_OU_2T_{line_str}'] = bookie
        row[f'Over_2T_{line_str}'] = over if over is not None else 0
        row[f'Under_2T_{line_str}'] = under if under is not None else 0
    
    # === OVER/UNDER FULL TIME (0.5, 1.5, 2.5, 3.5, 4.5) ===
    ou_ft = match_data.get('Odds_OU_FT', {})
    
    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        bookie, over, under = extract_ou_line(ou_ft, line, prefer_bookmakers)
        line_str = str(line).replace('.', '_')
        row[f'Bookie_OU_FT_{line_str}'] = bookie
        row[f'Over_FT_{line_str}'] = over if over is not None else 0
        row[f'Under_FT_{line_str}'] = under if under is not None else 0
    
    # === BOTH TEAMS TO SCORE (BTTS FT, HT, 2T) ===
    for scope_key, suffix in [('Odds_BTTS_FT', 'FT'), ('Odds_BTTS_HT', 'HT'), ('Odds_BTTS_2T', '2T')]:
        btts_list = match_data.get(scope_key, [])
        best_btts = find_best_bookmaker(btts_list, prefer_bookmakers)
        prefix = 'Bookie_BTTS' if suffix == 'FT' else f'Bookie_BTTS_{suffix}'
        y_col = 'BTTS_Yes' if suffix == 'FT' else f'BTTS_Yes_{suffix}'
        n_col = 'BTTS_No' if suffix == 'FT' else f'BTTS_No_{suffix}'
        if best_btts:
            row[prefix] = best_btts.get('Bookmaker')
            row[y_col] = best_btts.get('Yes', 0)
            row[n_col] = best_btts.get('No', 0)
        else:
            row[prefix] = None
            row[y_col] = 0
            row[n_col] = 0
    
    # === DOUBLE CHANCE (DC FT, HT, 2T) ===
    for scope_key, suffix in [('Odds_DC_FT', 'FT'), ('Odds_DC_HT', 'HT'), ('Odds_DC_2T', '2T')]:
        dc_list = match_data.get(scope_key, [])
        best_dc = find_best_bookmaker(dc_list, prefer_bookmakers)
        prefix = 'Bookie_DC' if suffix == 'FT' else f'Bookie_DC_{suffix}'
        c1x = 'DC_1X' if suffix == 'FT' else f'DC_1X_{suffix}'
        c12 = 'DC_12' if suffix == 'FT' else f'DC_12_{suffix}'
        cx2 = 'DC_X2' if suffix == 'FT' else f'DC_X2_{suffix}'
        if best_dc:
            row[prefix] = best_dc.get('Bookmaker')
            row[c1x] = best_dc.get('Odd_1X', 0)
            row[c12] = best_dc.get('Odd_12', 0)
            row[cx2] = best_dc.get('Odd_X2', 0)
        else:
            row[prefix] = None
            row[c1x] = 0
            row[c12] = 0
            row[cx2] = 0
            
    # === DRAW NO BET (DNB FT, HT, 2T) ===
    for scope_key, suffix in [('Odds_DNB_FT', 'FT'), ('Odds_DNB_HT', 'HT'), ('Odds_DNB_2T', '2T')]:
        dnb_list = match_data.get(scope_key, [])
        b_dnb, h_dnb, a_dnb = extract_dnb(dnb_list, prefer_bookmakers)
        row[f'Bookie_DNB_{suffix}'] = b_dnb
        row[f'DNB_Home_{suffix}'] = h_dnb if h_dnb is not None else 0
        row[f'DNB_Away_{suffix}'] = a_dnb if a_dnb is not None else 0
    
    # === HALF / FULL TIME (HT/FT - 9 Combinações) ===
    ht_ft = match_data.get('Odds_HT_FT', {})
    ht_ft_combos = ['1_1', '1_X', '1_2', 'X_1', 'X_X', 'X_2', '2_1', '2_X', '2_2']
    first_b = None
    for combo in ht_ft_combos:
        b, _ = extract_ht_ft(ht_ft, combo, prefer_bookmakers)
        if b:
            first_b = b
            break
    row['Bookie_HT_FT'] = first_b
    for combo in ht_ft_combos:
        _, odd = extract_ht_ft(ht_ft, combo, prefer_bookmakers)
        row[f'HT_FT_{combo}'] = odd if odd is not None else 0
        
    # === ODD / EVEN (ÍMPAR / PAR FT, HT, 2T) ===
    for scope_key, suffix in [('Odds_OE_FT', 'FT'), ('Odds_OE_HT', 'HT'), ('Odds_OE_2T', '2T')]:
        oe_list = match_data.get(scope_key, [])
        b_oe, odd_val, even_val = extract_odd_even(oe_list, prefer_bookmakers)
        row[f'Bookie_OE_{suffix}'] = b_oe
        row[f'OE_Odd_{suffix}'] = odd_val if odd_val is not None else 0
        row[f'OE_Even_{suffix}'] = even_val if even_val is not None else 0
    
    # === CORRECT SCORE FT ===
    cs_ft = match_data.get('Odds_CS_FT', {})
    common_scores = ['0:0', '1:0', '0:1', '1:1', '2:0', '0:2', '2:1', '1:2', 
                     '2:2', '3:0', '0:3', '3:1', '1:3', '3:2', '2:3']
    
    for score in common_scores:
        bookie, odd = extract_correct_score(cs_ft, score, prefer_bookmakers)
        score_key = score.replace(':', '_')
        row[f'Bookie_CS_{score_key}'] = bookie
        row[f'CS_{score_key}'] = odd if odd is not None else 0
    
    # === ASIAN HANDICAP FT (Linhas mais comuns) ===
    ah_ft = match_data.get('Odds_AH_FT', {})
    ah_lines = ['-2.5', '-2.0', '-1.5', '-1.0', '-0.5', '+0.5', '+1.0', '+1.5', '+2.0', '+2.5']
    
    for line in ah_lines:
        bookie, home, away = extract_asian_handicap_line(ah_ft, line, prefer_bookmakers)
        line_key = line.replace('-', 'neg_').replace('+', 'pos_').replace('.', '_')
        row[f'Bookie_AH_{line_key}'] = bookie
        row[f'AH_Home_{line_key}'] = home if home is not None else 0
        row[f'AH_Away_{line_key}'] = away if away is not None else 0
    
    # === EUROPEAN HANDICAP FT (Linhas mais comuns) ===
    eh_ft = match_data.get('Odds_EH_FT', {})
    eh_lines = ['-3', '-2', '-1', '+1', '+2', '+3', '1', '2', '3']
    
    for line in ['-3', '-2', '-1', '+1', '+2', '+3']:
        bookie, home, draw, away = extract_european_handicap_line(eh_ft, line, prefer_bookmakers)
        line_key = line.replace('-', 'neg_').replace('+', 'pos_')
        row[f'Bookie_EH_{line_key}'] = bookie
        row[f'EH_Home_{line_key}'] = home if home is not None else 0
        row[f'EH_Draw_{line_key}'] = draw if draw is not None else 0
        row[f'EH_Away_{line_key}'] = away if away is not None else 0
    
    # === ESTATÍSTICAS COMPLETAS (34 campos x 2 times x 3 períodos = 204 colunas) ===
    stats_ft = match_data.get('Statistics_FT', {})
    stats_ht = match_data.get('Statistics_HT', {})
    stats_2t = match_data.get('Statistics_2T', {})
    
    # Função auxiliar para extrair estatística
    def extract_stat(stat_dict, key):
        if not stat_dict or not isinstance(stat_dict, dict):
            return None, None
        data = stat_dict.get(key, {})
        if isinstance(data, dict):
            return data.get('Home'), data.get('Away')
        return None, None

    ALL_STATS_MAPPING = [
        ('xG', 'Expected goals (xG)'),
        ('xGOT', 'xG on target (xGOT)'),
        ('xA', 'Expected assists (xA)'),
        ('xGOT_Faced', 'xGOT faced'),
        ('Goals_Prevented', 'Goals prevented'),
        ('Possession', 'Ball possession'),
        ('Passes_Pct', 'Passes'),
        ('Long_Passes_Pct', 'Long passes'),
        ('Passes_Final_Third_Pct', 'Passes in final third'),
        ('Through_Passes', 'Accurate through passes'),
        ('Crosses_Pct', 'Crosses'),
        ('Total_Shots', 'Total shots'),
        ('Shots_On_Target', 'Shots on target'),
        ('Shots_Off_Target', 'Shots off target'),
        ('Blocked_Shots', 'Blocked shots'),
        ('Shots_Inside_Box', 'Shots inside the box'),
        ('Shots_Outside_Box', 'Shots outside the box'),
        ('Big_Chances', 'Big chances'),
        ('Hit_Woodwork', 'Hit the woodwork'),
        ('Touches_Box', 'Touches in opposition box'),
        ('Corners', 'Corner kicks'),
        ('Free_Kicks', 'Free kicks'),
        ('Throw_Ins', 'Throw ins'),
        ('Fouls', 'Fouls'),
        ('Yellow_Cards', 'Yellow cards'),
        ('Red_Cards', 'Red cards'),
        ('Offsides', 'Offsides'),
        ('Goalkeeper_Saves', 'Goalkeeper saves'),
        ('Tackles_Pct', 'Tackles'),
        ('Duels_Won', 'Duels won'),
        ('Clearances', 'Clearances'),
        ('Interceptions', 'Interceptions'),
        ('Errors_Shot', 'Errors leading to shot'),
        ('Errors_Goal', 'Errors leading to goal'),
    ]

    for suffix, stat_dict in [('FT', stats_ft), ('HT', stats_ht), ('2T', stats_2t)]:
        for col_name, fs_key in ALL_STATS_MAPPING:
            if stat_dict:
                h_val, a_val = extract_stat(stat_dict, fs_key)
                row[f'{col_name}_Home_{suffix}'] = h_val
                row[f'{col_name}_Away_{suffix}'] = a_val
            else:
                row[f'{col_name}_Home_{suffix}'] = None
                row[f'{col_name}_Away_{suffix}'] = None
    
    return row


def generate_dataframe_from_json(json_file, output_csv=None, prefer_bookmakers=['bet365', 'betfair', 'pinnacle']):
    """
    Gera DataFrame a partir de um arquivo JSON de país/temporada
    
    Args:
        json_file: Caminho para o arquivo JSON
        output_csv: Caminho para salvar CSV (opcional)
        prefer_bookmakers: Lista de bookmakers preferenciais em ordem
    
    Returns:
        DataFrame pandas
    """
    print(f"\n📂 Lendo: {json_file}")
    
    if str(json_file).endswith('.zip'):
        import zipfile
        with zipfile.ZipFile(json_file, 'r') as zf:
            json_names = [n for n in zf.namelist() if n.endswith('.json')]
            if not json_names:
                print("⚠️ Nenhum arquivo .json encontrado dentro do zip")
                return None
            with zf.open(json_names[0]) as f:
                data = json.load(f)
    else:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    
    country = data.get('country', 'Unknown')
    season = data.get('season', 'Unknown')
    leagues = data.get('leagues', [])
    
    print(f"   País: {country} | Temporada: {season} | Ligas: {len(leagues)}")
    
    if not leagues:
        print("⚠️ Nenhuma liga no arquivo")
        return None
    
    # Processa cada liga e seus jogos
    all_rows = []
    total_matches = 0
    root_league_alias = data.get('league')
    
    for league_data in leagues:
        sub_league_name = league_data.get('name', 'Unknown')
        t_id = league_data.get('tournament_id')
        matches = league_data.get('matches', [])
        
        if not matches:
            continue
        
        print(f"   🔄 {sub_league_name}: {len(matches)} jogos")
        total_matches += len(matches)
        
        main_div_name = root_league_alias if root_league_alias else sub_league_name
        
        for match in matches:
            row = process_match_to_row(
                match, 
                main_div_name, 
                country, 
                season, 
                prefer_bookmakers,
                sub_league=match.get('Sub_League', sub_league_name),
                tournament_id=match.get('Tournament_ID', t_id)
            )
            all_rows.append(row)
    
    if not all_rows:
        print("⚠️ Nenhum jogo processado")
        return None
    
    # Cria DataFrame
    df = pd.DataFrame(all_rows)
    
    # Se já existir um CSV prévio, une os dados preservando o histórico e atualizando novos jogos
    if output_csv and os.path.exists(output_csv):
        try:
            df_existing = pd.read_csv(output_csv, low_memory=False)
            df = pd.concat([df_existing, df], ignore_index=True)
            for id_col in ['Match_ID', 'Id', 'id', 'match_id']:
                if id_col in df.columns:
                    df = df.drop_duplicates(subset=[id_col], keep='last')
                    break
        except Exception:
            pass
            
    print(f"✓ DataFrame consolidado: {len(df)} linhas x {len(df.columns)} colunas")
    
    # Salva CSV se solicitado
    if output_csv:
        df.to_csv(output_csv, index=False, encoding='utf-8')
        file_size_kb = os.path.getsize(output_csv) / 1024
        print(f"✓ Salvo: {output_csv} ({file_size_kb:.1f} KB)")
    
    return df


def process_all_historical_games(input_dir='jogos_passados', output_dir='dataframes_jogos_passados', 
                                  prefer_bookmakers=['bet365', 'betfair', 'pinnacle']):
    """
    Processa todos os arquivos JSON ou JSON.ZIP de jogos históricos (all seasons)
    """
    if not os.path.exists(input_dir):
        print(f"❌ Diretório não encontrado: {input_dir}")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    
    print("=" * 80)
    print("📊 GERADOR DE DATAFRAMES - JOGOS HISTÓRICOS (ALL SEASONS)")
    print("=" * 80)
    print(f"📂 Entrada: {input_dir}/")
    print(f"💾 Saída: {output_dir}/")
    print(f"🎯 Bookmakers preferenciais: {', '.join(prefer_bookmakers)}")
    print("=" * 80)
    
    # Lista arquivos JSON e ZIP
    all_files = os.listdir(input_dir)
    target_files = [f for f in all_files if f.endswith('.json.zip') or f.endswith('.json') or f.endswith('.zip')]
    
    # Remove redundância se existirem .json e .json.zip do mesmo jogo
    seen_bases = set()
    unique_files = []
    for f in sorted(target_files):
        base = f.replace('.json.zip', '').replace('.zip', '').replace('.json', '')
        if base not in seen_bases:
            seen_bases.add(base)
            unique_files.append(f)
    
    if not unique_files:
        print(f"\n❌ Nenhum arquivo JSON ou ZIP encontrado em {input_dir}/")
        return
    
    print(f"\n✓ {len(unique_files)} arquivo(s) encontrado(s)")
    
    total_games = 0
    
    # Processa cada arquivo
    for file_name in sorted(unique_files):
        input_path = os.path.join(input_dir, file_name)
        base_name = file_name.replace('.json.zip', '').replace('.zip', '').replace('.json', '')
        output_csv = os.path.join(output_dir, f"{base_name}.csv")
        
        try:
            df = generate_dataframe_from_json(input_path, output_csv, prefer_bookmakers)
            if df is not None:
                total_games += len(df)
        except Exception as e_file:
            print(f"  ⚠️ Erro ao processar {file_name}: {e_file}")
    
    print("\n" + "=" * 80)
    print("✅ PROCESSAMENTO CONCLUÍDO")
    print("=" * 80)
    print(f"📊 Total de jogos processados: {total_games}")
    print(f"💾 CSVs salvos em: {output_dir}/")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Modo específico: processa um arquivo
        json_file = sys.argv[1]
        output_csv = sys.argv[2] if len(sys.argv) > 2 else json_file.replace('.json', '.csv')
        
        df = generate_dataframe_from_json(json_file, output_csv)
        
        if df is not None:
            print("\n📋 Primeiras linhas:")
            print(df.head())
            
            print("\n📊 Colunas disponíveis:")
            for i, col in enumerate(df.columns, 1):
                print(f"  {i:2d}. {col}")
    else:
        # Modo padrão: processa todos os arquivos
        process_all_historical_games()
