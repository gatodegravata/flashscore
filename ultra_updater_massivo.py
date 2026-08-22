#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ ULTRA SCRAPER FLASH v2 — ATUALIZAÇÃO MASSIVA DE JOGOS (ASYNC) ⚡
================================================================================
Modo de Operação:
1. Carrega o parquet mestre de jogos consolidados (ou URL do GitHub).
2. Seleciona a fatia (slice) correta para este notebook Colab.
3. Faz o download ultrarrápido via API direta (df_sui, df_st, GraphQL OCE)
   usando asyncio + curl_cffi.AsyncSession com N workers concorrentes.
4. Rotaciona proxies do .env por slot de worker (sticky — evita conflito).
5. Salva parquet parcial a cada 10.000 jogos para não perder progresso.
6. Checkpoint de IDs nomeado por slice, seguro para múltiplos Colabs.
================================================================================

Exemplo de uso (Colab notebook 1 de 4, usando proxies 1 e 3):
  !python ultra_updater_massivo.py --workers 8 --slice 1/4 --proxies 1,3

Exemplo de uso (Colab notebook 2 de 4, proxies direto):
  !python ultra_updater_massivo.py --workers 8 --slice 2/4

Parâmetros de delay por endpoint (ajuste conforme rate-limit observado):
  --delay-sumario 0.0   (df_sui   — geralmente permissivo)
  --delay-stats   0.0   (df_st    — geralmente permissivo)
  --delay-odds    0.1   (GraphQL  — mais restritivo, recomenda delay)
================================================================================
"""

import os
import sys
import asyncio
import json
import time
import zipfile
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ─── Importações assíncronas ────────────────────────────────────────────────
try:
    from curl_cffi.requests import AsyncSession
    CURL_CFFI_ASYNC = True
except ImportError:
    CURL_CFFI_ASYNC = False
    print("⚠️  curl_cffi não encontrado — usando requests síncrono como fallback.")

# ─── Módulos locais ──────────────────────────────────────────────────────────
from generate_df_jogos_passados import process_match_to_row


# ═══════════════════════════════════════════════════════════════════════════════
# CARREGAMENTO DE PROXIES DO .ENV
# ═══════════════════════════════════════════════════════════════════════════════

def load_proxies_from_env(indices: Optional[List[int]] = None) -> List[Tuple[Optional[str], str]]:
    """
    Lê as variáveis WEBSHARE_PROXY_N do arquivo .env presente no diretório atual.
    Retorna uma lista de tuplas (proxy_url, label).
    Sempre inclui (None, "IP_DIRETO") como primeira opção (slot 0) com prioridade.

    Args:
        indices: lista de índices a carregar (ex: [1, 3, 4]).
                 Se None, carrega todos os proxies encontrados.
    """
    # IP direto é sempre o slot 0 — prioridade para economizar banda dos proxies
    result: List[Tuple[Optional[str], str]] = [(None, "IP_DIRETO")]

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        # Tenta no diretório de trabalho atual (útil no Colab)
        env_path = ".env"

    proxy_map: Dict[int, str] = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip()
                    if key.startswith("WEBSHARE_PROXY_"):
                        try:
                            idx = int(key.replace("WEBSHARE_PROXY_", ""))
                            proxy_map[idx] = val
                        except ValueError:
                            pass

    if not proxy_map:
        print("⚠️  Nenhum WEBSHARE_PROXY_N encontrado no .env — rodando só com IP direto.")
        return result

    target_indices = sorted(indices) if indices else sorted(proxy_map.keys())
    for idx in target_indices:
        if idx in proxy_map:
            url = proxy_map[idx]
            result.append((url, f"proxy_{idx}"))
        else:
            print(f"⚠️  WEBSHARE_PROXY_{idx} não encontrado no .env — ignorado.")

    print(f"🔒 Slots de proxy disponíveis: {[label for _, label in result]}")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SCRAPER ASSÍNCRONO POR JOGO
# ═══════════════════════════════════════════════════════════════════════════════

FSIGN = "SW9D1eZo"
FEED_BASE = "https://global.flashscore.ninja/2/x/feed"
GRAPHQL_BASE = "https://global.ds.lsapp.eu/odds/pq_graphql"

HEADERS_FEED = {
    "Referer": "https://www.flashscore.com/",
    "Origin": "https://www.flashscore.com",
    "x-fsign": FSIGN,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
HEADERS_GRAPHQL = {
    "Referer": "https://www.flashscore.com/",
    "Origin": "https://www.flashscore.com",
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


async def _async_get_with_retry(
    session: "AsyncSession",
    url: str,
    headers: dict,
    endpoint_label: str,
    match_id: str,
    proxy_label: str,
    max_attempts: int = 3,
) -> Optional[Any]:
    """
    Realiza GET assíncrono com backoff exponencial.
    Retorna o objeto Response ou None em caso de falha.
    """
    for attempt in range(max_attempts):
        try:
            resp = await session.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(
                    f"\n🚨 [RATE LIMIT 429] endpoint={endpoint_label} | match={match_id} | "
                    f"proxy={proxy_label} | tentativa={attempt+1}/{max_attempts} | aguardando {wait}s"
                )
                await asyncio.sleep(wait)
                continue
            elif resp.status_code == 403:
                print(
                    f"\n🚫 [BLOQUEIO 403] endpoint={endpoint_label} | match={match_id} | proxy={proxy_label}"
                )
                return None
            elif resp.status_code != 200:
                # Loga status inesperado para facilitar diagnóstico de proxy
                if "IP_DIRETO" not in proxy_label:
                    print(
                        f"\n⚠️  [HTTP {resp.status_code}] endpoint={endpoint_label} | "
                        f"match={match_id} | proxy={proxy_label} | url={url[:80]}"
                    )
                return None
            return resp
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if attempt == max_attempts - 1:
                return None
            await asyncio.sleep(0.3)
    return None


async def scrape_match_async(
    session: "AsyncSession",
    match_id: str,
    base_info: Dict[str, Any],
    proxy_label: str,
    delay_sumario: float = 0.0,
    delay_stats: float = 0.0,
    delay_odds: float = 0.0,
) -> Dict[str, Any]:
    """
    Raspa assincronamente os 3 endpoints de uma partida:
      - df_sui (sumário / gols / minutos)
      - df_st  (estatísticas FT / HT / 2T)
      - GraphQL OCE (odds de todas as casas)

    Retorna o dict completo pronto para process_match_to_row().
    """
    import re

    match_data = base_info.copy()
    match_data.setdefault("Id", match_id)
    match_data.setdefault("Match_ID", match_id)

    # Flags de diagnóstico
    match_data["_scraped_sui"] = False
    match_data["_scraped_st"] = False
    match_data["_scraped_oce"] = False

    # ── 1. df_sui (Sumário) ───────────────────────────────────────────────────
    url_sui = f"{FEED_BASE}/df_sui_1_{match_id}"
    resp_sui = await _async_get_with_retry(session, url_sui, HEADERS_FEED, "df_sui", match_id, proxy_label)

    match_data["Min_Goals_Home"] = []
    match_data["Min_Goals_Away"] = []

    if resp_sui and resp_sui.text:
        raw = resp_sui.text
        match_data["_scraped_sui"] = True
        if delay_sumario > 0:
            await asyncio.sleep(delay_sumario)

        for event in raw.split('~'):
            is_goal = False
            if any(x in event for x in ['IE÷3', 'IE÷4', 'IE÷10', 'IE\xf73', 'IE\xf74', 'IE\xf710',
                                          'IE\xac3', 'IE\xac4', 'IE\xac10']):
                is_goal = True
            elif ('Goal' in event or 'Penalty' in event) and 'Missed' not in event and 'Awarded' not in event:
                is_goal = True
            elif ('IK÷Penalty' in event or 'IK\xf7Penalty' in event or 'IK\xacPenalty' in event) and 'Missed' not in event:
                is_goal = True

            if is_goal:
                is_home = any(h in event for h in ['IA÷1', 'IA\xf71', 'IA\xac1'])
                is_away = any(a in event for a in ['IA÷2', 'IA\xf72', 'IA\xac2'])
                m = re.search(r'IB[\xac\xf7÷](\d+)', event)
                if m:
                    minute = int(m.group(1))
                    if is_home:
                        match_data["Min_Goals_Home"].append(minute)
                    elif is_away:
                        match_data["Min_Goals_Away"].append(minute)

        match_data["Min_Goals_Home"].sort()
        match_data["Min_Goals_Away"].sort()

        # feed dc_1 — notas de mata-mata / local neutro
        try:
            url_dc = f"{FEED_BASE}/dc_1_{match_id}"
            resp_dc = await session.get(url_dc, headers=HEADERS_FEED, timeout=5.0)
            if resp_dc and resp_dc.status_code == 200 and resp_dc.text:
                m_dm = re.search(r'DM[\xac\xf7÷]([^\xac\xf7÷~]+)', resp_dc.text)
                if m_dm:
                    note = m_dm.group(1).strip()
                    match_data["Match_Note"] = note
                    if 'Neutral location' in note:
                        match_data["Neutral_Location"] = True
        except Exception:
            pass

    # ── 2. df_st (Estatísticas) ───────────────────────────────────────────────
    url_st = f"{FEED_BASE}/df_st_1_{match_id}"
    resp_st = await _async_get_with_retry(session, url_st, HEADERS_FEED, "df_st", match_id, proxy_label)

    stats_data = {"Statistics_FT": {}, "Statistics_HT": {}, "Statistics_2T": {}}

    if resp_st and resp_st.text:
        raw_st = resp_st.text
        match_data["_scraped_st"] = True
        if delay_stats > 0:
            await asyncio.sleep(delay_stats)

        current_stage = "Statistics_FT"
        for sec in raw_st.split('~'):
            if 'SE÷1st Half' in sec or 'SE\xf71st Half' in sec or 'SE\xac1st Half' in sec:
                current_stage = "Statistics_HT"
            elif 'SE÷2nd Half' in sec or 'SE\xf72nd Half' in sec or 'SE\xac2nd Half' in sec:
                current_stage = "Statistics_2T"
            elif 'SE÷Match' in sec or 'SE\xf7Match' in sec or 'SE\xacMatch' in sec:
                current_stage = "Statistics_FT"

            m_sg = re.search(r'SG[\xac\xf7÷]([^\xac\xf7÷~]+)', sec)
            m_sh = re.search(r'SH[\xac\xf7÷]([^\xac\xf7÷~]+)', sec)
            m_si = re.search(r'SI[\xac\xf7÷]([^\xac\xf7÷~]+)', sec)

            if m_sg and m_sh and m_si:
                stat_name = m_sg.group(1).strip()
                val_h = _parse_stat(m_sh.group(1).strip())
                val_a = _parse_stat(m_si.group(1).strip())
                stats_data[current_stage][stat_name] = {"Home": val_h, "Away": val_a}

    match_data.update(stats_data)

    # ── 3. GraphQL OCE (Odds) ─────────────────────────────────────────────────
    url_oce = (
        f"{GRAPHQL_BASE}?_hash=oce&eventId={match_id}"
        f"&projectId=2&geoIpCode=BR&geoIpSubdivisionCode=BRRS"
    )
    resp_oce = await _async_get_with_retry(session, url_oce, HEADERS_GRAPHQL, "GraphQL_OCE", match_id, proxy_label)

    odds_result = _empty_odds()
    if resp_oce:
        try:
            json_data = resp_oce.json()
            match_data["_scraped_oce"] = True
            if delay_odds > 0:
                await asyncio.sleep(delay_odds)
            odds_result = _parse_odds(json_data)
        except Exception:
            pass

    match_data.update(odds_result)
    return match_data


def _parse_stat(val_str: str) -> Any:
    import re
    if '%' in val_str:
        m = re.search(r'(\d+(?:\.\d+)?)%', val_str)
        if m:
            return round(float(m.group(1)) / 100.0, 2)
    try:
        return float(val_str) if '.' in val_str else float(int(val_str))
    except ValueError:
        return val_str


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).replace(',', '.').replace('%', '').strip())
    except (ValueError, TypeError):
        return None


def _empty_odds() -> Dict[str, Any]:
    o: Dict[str, Any] = {
        "Odds_1X2_FT": [], "Odds_1X2_HT": [], "Odds_1X2_2T": [],
        "Odds_OU_FT": {}, "Odds_OU_HT": {}, "Odds_OU_2T": {},
        "Odds_BTTS_FT": [], "Odds_BTTS_HT": [], "Odds_BTTS_2T": [],
        "Odds_DC_FT": [], "Odds_DC_HT": [], "Odds_DC_2T": [],
        "Odds_DNB_FT": [], "Odds_DNB_HT": [], "Odds_DNB_2T": [],
        "Odds_AH_FT": {}, "Odds_AH_HT": {}, "Odds_AH_2T": {},
        "Odds_EH_FT": {}, "Odds_EH_HT": {}, "Odds_EH_2T": {},
        "Odds_HT_FT": {},
        "Odds_OE_FT": [], "Odds_OE_HT": [], "Odds_OE_2T": [],
        "Odds_CS_FT": {}, "Odds_CS_HT": {}, "Odds_CS_2T": {},
        "Best_Odd_1_FT": None, "Best_Odd_X_FT": None, "Best_Odd_2_FT": None,
    }
    for line in ["0.5","1.5","2.5","3.5","4.5","5.5","6.5","7.5","8.5","9.5","10.5","11.5"]:
        o["Odds_OU_FT"][f"OU_{line}"] = []
    for line in ["0.5","1.5","2.5","3.5","4.5","5.5","6.5"]:
        o["Odds_OU_HT"][f"OU_{line}"] = []
        o["Odds_OU_2T"][f"OU_{line}"] = []
    return o


def _parse_odds(json_data: dict) -> Dict[str, Any]:
    """Parsing completo do payload GraphQL OCE."""
    result = _empty_odds()
    data_body = json_data.get("data", {}).get("findOddsByEventId", {})

    bookmaker_map: Dict[Any, str] = {}
    for pb in data_body.get("settings", {}).get("bookmakers", []):
        bm = pb.get("bookmaker", {})
        b_id = bm.get("id")
        b_name = bm.get("name")
        if b_id and b_name:
            bookmaker_map[b_id] = b_name

    odds_list = data_body.get("odds", [])

    home_p_id, away_p_id = None, None
    for item in odds_list:
        if item.get("bettingType") == "HOME_DRAW_AWAY" and item.get("bettingScope") == "FULL_TIME":
            for o in item.get("odds", []):
                p_id = o.get("eventParticipantId")
                if p_id:
                    if home_p_id is None:
                        home_p_id = p_id
                    elif away_p_id is None and p_id != home_p_id:
                        away_p_id = p_id
            if home_p_id and away_p_id:
                break

    for item in odds_list:
        b_id = item.get("bookmakerId")
        bookie_name = bookmaker_map.get(b_id, f"Bookmaker_{b_id}")
        b_type = item.get("bettingType")
        b_scope = item.get("bettingScope")
        sub_odds = item.get("odds", [])

        def _scope_key(ft_key: str, ht_key: str, t2_key: str) -> str:
            return ft_key if b_scope == "FULL_TIME" else (ht_key if b_scope == "FIRST_HALF" else t2_key)

        if b_type == "HOME_DRAW_AWAY":
            odd_1, odd_x, odd_2 = None, None, None
            for o in sub_odds:
                val = _safe_float(o.get("value"))
                p_id = o.get("eventParticipantId")
                if p_id is None:
                    odd_x = val
                elif p_id == home_p_id or (home_p_id is None and odd_1 is None):
                    odd_1 = val
                else:
                    odd_2 = val
            tkey = _scope_key("Odds_1X2_FT", "Odds_1X2_HT", "Odds_1X2_2T")
            if odd_1 or odd_x or odd_2:
                result[tkey].append({"Bookmaker": bookie_name, "Odd_1": odd_1, "Odd_X": odd_x, "Odd_2": odd_2})

        elif b_type == "OVER_UNDER":
            td = result[_scope_key("Odds_OU_FT", "Odds_OU_HT", "Odds_OU_2T")]
            for o in sub_odds:
                h_obj = o.get("handicap")
                h_val = h_obj.get("value") if isinstance(h_obj, dict) else h_obj
                sel = str(o.get("selection", "")).upper()
                val = _safe_float(o.get("value"))
                if h_val:
                    key = f"OU_{h_val}"
                    td.setdefault(key, [])
                    entry = next((e for e in td[key] if e["Bookmaker"] == bookie_name), None)
                    if not entry:
                        entry = {"Bookmaker": bookie_name, "Over": None, "Under": None}
                        td[key].append(entry)
                    if "OVER" in sel:
                        entry["Over"] = val
                    elif "UNDER" in sel:
                        entry["Under"] = val

        elif b_type == "BOTH_TEAMS_TO_SCORE":
            yes_val, no_val = None, None
            for o in sub_odds:
                val = _safe_float(o.get("value"))
                if o.get("bothTeamsToScore") is True or str(o.get("selection", "")).upper() == "YES":
                    yes_val = val
                else:
                    no_val = val
            tkey = _scope_key("Odds_BTTS_FT", "Odds_BTTS_HT", "Odds_BTTS_2T")
            if yes_val or no_val:
                result[tkey].append({"Bookmaker": bookie_name, "Yes": yes_val, "No": no_val})

        elif b_type == "DOUBLE_CHANCE":
            dc_1x, dc_12, dc_x2 = None, None, None
            for o in sub_odds:
                p_id = o.get("eventParticipantId")
                val = _safe_float(o.get("value"))
                sel = str(o.get("selection", "")).upper() if o.get("selection") else ""
                if "1X" in sel or sel == "HOME_DRAW" or p_id == home_p_id:
                    dc_1x = val
                elif "12" in sel or sel == "HOME_AWAY" or (p_id is None and val is not None):
                    dc_12 = val
                elif "X2" in sel or sel == "DRAW_AWAY" or p_id == away_p_id:
                    dc_x2 = val
            tkey = _scope_key("Odds_DC_FT", "Odds_DC_HT", "Odds_DC_2T")
            if dc_1x or dc_12 or dc_x2:
                result[tkey].append({"Bookmaker": bookie_name, "Odd_1X": dc_1x, "Odd_12": dc_12, "Odd_X2": dc_x2})

        elif b_type == "DRAW_NO_BET":
            dnb_1, dnb_2 = None, None
            for o in sub_odds:
                p_id = o.get("eventParticipantId")
                val = _safe_float(o.get("value"))
                if p_id == home_p_id or (home_p_id is None and dnb_1 is None):
                    dnb_1 = val
                else:
                    dnb_2 = val
            tkey = _scope_key("Odds_DNB_FT", "Odds_DNB_HT", "Odds_DNB_2T")
            if dnb_1 or dnb_2:
                result[tkey].append({"Bookmaker": bookie_name, "Home": dnb_1, "Away": dnb_2})

        elif b_type == "ASIAN_HANDICAP":
            td = result[_scope_key("Odds_AH_FT", "Odds_AH_HT", "Odds_AH_2T")]
            for o in sub_odds:
                p_id = o.get("eventParticipantId")
                h_obj = o.get("handicap")
                h_raw = h_obj.get("value") if isinstance(h_obj, dict) else h_obj
                val = _safe_float(o.get("value"))
                if h_raw is not None and val is not None:
                    try:
                        h_num = float(h_raw)
                    except ValueError:
                        continue
                    if p_id == away_p_id and away_p_id is not None:
                        line_key = f"{(-h_num):+.1f}" if (-h_num) != 0 else "0.0"
                        is_home_side = False
                    else:
                        line_key = f"{h_num:+.1f}" if h_num != 0 else "0.0"
                        is_home_side = True
                    key = f"AH_{line_key}"
                    td.setdefault(key, [])
                    entry = next((e for e in td[key] if e["Bookmaker"] == bookie_name), None)
                    if not entry:
                        entry = {"Bookmaker": bookie_name, "Home": None, "Away": None}
                        td[key].append(entry)
                    if is_home_side:
                        entry["Home"] = val
                    else:
                        entry["Away"] = val

        elif b_type == "EUROPEAN_HANDICAP":
            td = result[_scope_key("Odds_EH_FT", "Odds_EH_HT", "Odds_EH_2T")]
            for o in sub_odds:
                p_id = o.get("eventParticipantId")
                h_obj = o.get("handicap")
                h_raw = h_obj.get("value") if isinstance(h_obj, dict) else h_obj
                val = _safe_float(o.get("value"))
                if h_raw is not None and val is not None:
                    try:
                        h_num = int(float(h_raw))
                    except ValueError:
                        continue
                    key = f"EH_{h_num:+d}"
                    td.setdefault(key, [])
                    entry = next((e for e in td[key] if e["Bookmaker"] == bookie_name), None)
                    if not entry:
                        entry = {"Bookmaker": bookie_name, "Home": None, "Draw": None, "Away": None}
                        td[key].append(entry)
                    if p_id is None:
                        entry["Draw"] = val
                    elif p_id == home_p_id or (home_p_id is None and entry["Home"] is None):
                        entry["Home"] = val
                    else:
                        entry["Away"] = val

        elif b_type == "HALF_FULL_TIME" and b_scope == "FULL_TIME":
            for o in sub_odds:
                winner = o.get("winner")
                val = _safe_float(o.get("value"))
                if winner and val:
                    key = winner.replace("/", "_")
                    result["Odds_HT_FT"].setdefault(key, [])
                    result["Odds_HT_FT"][key].append({"Bookmaker": bookie_name, "Odd": val})

        elif b_type == "ODD_OR_EVEN":
            odd_val, even_val = None, None
            for o in sub_odds:
                sel = str(o.get("selection", "")).upper()
                val = _safe_float(o.get("value"))
                if "ODD" in sel:
                    odd_val = val
                elif "EVEN" in sel:
                    even_val = val
            tkey = _scope_key("Odds_OE_FT", "Odds_OE_HT", "Odds_OE_2T")
            if odd_val or even_val:
                result[tkey].append({"Bookmaker": bookie_name, "Odd": odd_val, "Even": even_val})

        elif b_type == "CORRECT_SCORE":
            td = result[_scope_key("Odds_CS_FT", "Odds_CS_HT", "Odds_CS_2T")]
            for o in sub_odds:
                sc = o.get("score")
                val = _safe_float(o.get("value"))
                if sc and val:
                    td.setdefault(sc, [])
                    td[sc].append({"Bookmaker": bookie_name, "Odd": val})

    # Melhores odds 1X2 FT
    if result["Odds_1X2_FT"]:
        v1 = [x["Odd_1"] for x in result["Odds_1X2_FT"] if x.get("Odd_1")]
        vx = [x["Odd_X"] for x in result["Odds_1X2_FT"] if x.get("Odd_X")]
        v2 = [x["Odd_2"] for x in result["Odds_1X2_FT"] if x.get("Odd_2")]
        if v1: result["Best_Odd_1_FT"] = max(v1)
        if vx: result["Best_Odd_X_FT"] = max(vx)
        if v2: result["Best_Odd_2_FT"] = max(v2)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# ORQUESTRADOR PRINCIPAL ASSÍNCRONO
# ═══════════════════════════════════════════════════════════════════════════════

class UltraUpdaterAsync:

    def __init__(
        self,
        parquet_source: str,
        output_dir: str,
        batch_size: int,
        workers: int,
        proxy_indices: Optional[List[int]],
        slice_part: Optional[str],
        delay_sumario: float,
        delay_stats: float,
        delay_odds: float,
        save_every: int = 10_000,
        direct_workers: int = 0,
    ):
        self.parquet_source = parquet_source
        self.output_dir = output_dir
        self.batch_size = batch_size
        self.workers = workers
        self.slice_part = slice_part
        self.delay_sumario = delay_sumario
        self.delay_stats = delay_stats
        self.delay_odds = delay_odds
        self.save_every = save_every
        # direct_workers: quantos slots são fixados no IP direto do Colab.
        # 0 = distribuição uniforme (comportamento antigo)
        # N > 0 = primeiros N slots são IP_DIRETO, restantes distribuem nos proxies
        self.direct_workers = direct_workers

        # Slug para nomes de arquivo (ex: "1_4")
        self.slice_slug = slice_part.replace("/", "_") if slice_part else "all"

        self.zips_dir = os.path.join(output_dir, "zips_json_bruto")
        self.checkpoints_dir = os.path.join(output_dir, "checkpoints")
        self.final_dir = os.path.join(output_dir, "consolidado_final")
        for d in [self.zips_dir, self.checkpoints_dir, self.final_dir]:
            os.makedirs(d, exist_ok=True)

        # Lista de (proxy_url, label) — slot 0 = IP direto
        self.proxy_slots = load_proxies_from_env(proxy_indices)

        # IDs já processados para este slice
        self.cp_ids_file = os.path.join(
            self.checkpoints_dir, f"processed_ids_{self.slice_slug}.txt"
        )
        self.processed_ids = self._load_checkpoint_ids()

    def _load_checkpoint_ids(self) -> set:
        done: set = set()
        if os.path.exists(self.cp_ids_file):
            with open(self.cp_ids_file, "r", encoding="utf-8") as f:
                for line in f:
                    mid = line.strip()
                    if mid:
                        done.add(mid)
        print(f"💾 Checkpoint [{self.slice_slug}]: {len(done):,} partidas já processadas.")
        return done

    def _append_checkpoint_id(self, mid: str):
        with open(self.cp_ids_file, "a", encoding="utf-8") as f:
            f.write(f"{mid}\n")

    def run(self):
        print("\n" + "=" * 80)
        print("🚀 ULTRA SCRAPER FLASH v2 — PARTIDAS CONSOLIDADAS (ASYNC)")
        print("=" * 80)

        # ─── Carrega Parquet mestre ────────────────────────────────────────────
        print(f"📥 Carregando base mestre: {self.parquet_source} ...")
        df_master = pd.read_parquet(self.parquet_source)
        print(f"📊 Total de registros no Parquet Mestre: {len(df_master):,}")

        id_col = (
            "Match_ID" if "Match_ID" in df_master.columns
            else ("Id" if "Id" in df_master.columns else df_master.columns[0])
        )

        df_master = df_master.drop_duplicates(subset=[id_col])

        # ─── Seleciona fatia ──────────────────────────────────────────────────
        if self.slice_part:
            try:
                part_idx, total_parts = map(int, self.slice_part.split("/"))
                chunk_len = len(df_master) // total_parts
                start_row = (part_idx - 1) * chunk_len
                end_row = len(df_master) if part_idx == total_parts else part_idx * chunk_len
                df_master = df_master.iloc[start_row:end_row].copy()
                print(
                    f"✂️  Fatia [{self.slice_part}]: {len(df_master):,} partidas "
                    f"(linhas {start_row:,} → {end_row:,})"
                )
            except Exception as e:
                print(f"⚠️  Erro ao interpretar --slice '{self.slice_part}': {e}. Usando base inteira.")

        # ─── Filtra pendentes ─────────────────────────────────────────────────
        pending_mask = ~df_master[id_col].astype(str).isin(self.processed_ids)
        df_pending = df_master[pending_mask].copy()
        total_pending = len(df_pending)
        print(f"⚡ Partidas pendentes: {total_pending:,}")

        if total_pending == 0:
            print("✅ Tudo já processado! Consolidando saída final...")
            self._consolidate_final_output()
            return

        pending_records = df_pending.to_dict(orient="records")

        # ─── Divide em lotes de batch_size ────────────────────────────────────
        num_batches = (total_pending + self.batch_size - 1) // self.batch_size
        print(
            f"📦 {total_pending:,} partidas em {num_batches} lote(s) de até {self.batch_size:,} jogos."
        )
        print(
            f"⚙️  Workers: {self.workers} | "
            f"Proxies: {[lbl for _, lbl in self.proxy_slots]} | "
            f"Delays → sui={self.delay_sumario}s st={self.delay_stats}s oce={self.delay_odds}s"
        )

        for batch_idx in range(num_batches):
            start_i = batch_idx * self.batch_size
            end_i = min(start_i + self.batch_size, total_pending)
            batch_records = pending_records[start_i:end_i]
            asyncio.run(
                self._process_batch_async(batch_idx + 1, num_batches, batch_records, id_col)
            )

        self._consolidate_final_output()

    async def _process_batch_async(
        self,
        batch_num: int,
        total_batches: int,
        records: List[Dict[str, Any]],
        id_col: str,
    ):
        print("\n" + "━" * 80)
        print(f"📦 LOTE [{batch_num}/{total_batches}] — {len(records):,} jogos")
        print("━" * 80)

        total_in_batch = len(records)
        t_batch_start = time.time()

        # Estado compartilhado (protegido por asyncio.Lock — sem threads)
        completed = 0
        errors = 0
        accumulated_rows: List[Dict[str, Any]] = []  # buffer para parquet parcial
        accumulated_json: List[Dict[str, Any]] = []  # buffer para ZIP
        all_json_this_batch: List[Dict[str, Any]] = []
        save_lock = asyncio.Lock()
        save_counter = [0]  # contador de saves intermediários para nomear arquivos

        semaphore = asyncio.Semaphore(self.workers)
        num_slots = len(self.proxy_slots)  # inclui slot 0 = IP_DIRETO
        num_proxies = max(1, num_slots - 1)  # apenas os proxies pagos

        # Calcula quantos workers ficam no IP direto
        # Se direct_workers=0, distribui uniforme (1 slot por worker ciclicamente)
        # Se direct_workers=N, os N primeiros slots são sempre IP_DIRETO
        dw = self.direct_workers if self.direct_workers > 0 else 0

        def _proxy_for_slot(slot_id: int) -> Tuple[Optional[str], str]:
            """Mapeia slot_id -> (proxy_url, label), respeitando direct_workers."""
            if dw > 0:
                if slot_id < dw:
                    # Slot reservado para IP direto
                    return self.proxy_slots[0]  # (None, "IP_DIRETO")
                else:
                    # Slots restantes distribuem-se entre os proxies pagos
                    proxy_only = self.proxy_slots[1:]  # exclui IP_DIRETO
                    if not proxy_only:
                        return self.proxy_slots[0]
                    return proxy_only[(slot_id - dw) % len(proxy_only)]
            else:
                # Distribuição uniforme original
                return self.proxy_slots[slot_id % num_slots]

        async def process_one(slot_id: int, meta: Dict[str, Any]):
            nonlocal completed, errors

            mid = str(meta.get(id_col, "")).strip()
            if not mid:
                return

            proxy_url, proxy_label = _proxy_for_slot(slot_id % self.workers)

            async with semaphore:
                t0 = time.time()
                try:
                    # Cria AsyncSession por tarefa (leve, sem overhead)
                    session_kwargs = {}
                    if CURL_CFFI_ASYNC:
                        session_kwargs["impersonate"] = "chrome120"
                    if proxy_url:
                        session_kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}

                    async with AsyncSession(**session_kwargs) as session:
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
                            "Neutral_Location": meta.get("Neutral_Location", False),
                        }

                        full_match = await scrape_match_async(
                            session=session,
                            match_id=mid,
                            base_info=base_info,
                            proxy_label=proxy_label,
                            delay_sumario=self.delay_sumario,
                            delay_stats=self.delay_stats,
                            delay_odds=self.delay_odds,
                        )

                    row_data = process_match_to_row(
                        match_data=full_match,
                        league_name=base_info["League"],
                        country=base_info["Country"],
                        season=base_info["Season"],
                        sub_league=base_info["Sub_League"],
                        tournament_id=base_info["Tournament_ID"],
                    )

                    elapsed = time.time() - t0
                    sui_ok = "✓" if full_match.get("_scraped_sui") else "✗"
                    st_ok = "✓" if full_match.get("_scraped_st") else "✗"
                    oce_ok = "✓" if full_match.get("_scraped_oce") else "✗"

                    async with save_lock:
                        completed += 1
                        accumulated_rows.append(row_data)
                        accumulated_json.append(full_match)
                        all_json_this_batch.append(full_match)
                        self.processed_ids.add(mid)
                        self._append_checkpoint_id(mid)
                        curr = completed

                        if curr % 25 == 0 or curr == total_in_batch:
                            speed = curr / (time.time() - t_batch_start + 0.001)
                            print(
                                f"  [{curr:6d}/{total_in_batch:6d}] "
                                f"({speed:5.1f} j/s) | "
                                f"SUI{sui_ok} ST{st_ok} OCE{oce_ok} | "
                                f"{proxy_label} | "
                                f"{base_info['Home']} vs {base_info['Away']} "
                                f"({elapsed:.2f}s)"
                            )

                        # ── Salva parquet intermediário a cada save_every jogos ──
                        if len(accumulated_rows) >= self.save_every:
                            save_counter[0] += 1
                            self._save_intermediate_parquet(
                                rows=accumulated_rows[:],
                                batch_num=batch_num,
                                save_idx=save_counter[0],
                            )
                            accumulated_rows.clear()
                            accumulated_json.clear()

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    async with save_lock:
                        errors += 1
                    print(f"  ✗ [slot {slot_id}] Erro no jogo {mid} ({proxy_label}): {exc}")

        # Cria tarefas distribuindo os records entre slots de proxy
        tasks = [
            asyncio.create_task(process_one(slot_id=i % self.workers, meta=rec))
            for i, rec in enumerate(records)
        ]
        await asyncio.gather(*tasks)

        # ─── Salva o que sobrou no buffer ─────────────────────────────────────
        if accumulated_rows:
            save_counter[0] += 1
            self._save_intermediate_parquet(
                rows=accumulated_rows,
                batch_num=batch_num,
                save_idx=save_counter[0],
            )

        # ─── ZIP de JSONs brutos do lote inteiro ──────────────────────────────
        zip_path = os.path.join(
            self.zips_dir,
            f"lote_{self.slice_slug}_{batch_num:03d}_{len(all_json_this_batch)}_jogos.zip",
        )
        print(f"\n💾 Compactando ZIP do lote {batch_num} ({len(all_json_this_batch):,} jogos)...")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for m in all_json_this_batch:
                mid_key = m.get("Match_ID") or m.get("Id", "unknown")
                zf.writestr(f"{mid_key}.json", json.dumps(m, ensure_ascii=False))
        print(f"  ✓ ZIP: {zip_path}")

        elapsed_batch = time.time() - t_batch_start
        speed_final = completed / (elapsed_batch + 0.001)
        print(
            f"\n✅ Lote {batch_num} concluído: {completed:,} ok | {errors:,} erros | "
            f"{elapsed_batch:.0f}s | {speed_final:.1f} j/s"
        )

    def _save_intermediate_parquet(
        self, rows: List[Dict[str, Any]], batch_num: int, save_idx: int
    ):
        """Salva parquet parcial no disco (checkpoint a cada SAVE_EVERY jogos)."""
        fname = f"part_{self.slice_slug}_{batch_num:03d}_{save_idx:03d}.parquet"
        path = os.path.join(self.checkpoints_dir, fname)
        df = pd.DataFrame(rows)
        df.to_parquet(path, index=False)
        print(f"\n  💾 [CHECKPOINT] {len(rows):,} jogos gravados → {path}")

    def _consolidate_final_output(self):
        print("\n" + "=" * 80)
        print("🏆 CONSOLIDANDO ARQUIVOS FINAIS")
        print("=" * 80)

        parquet_parts = [
            os.path.join(self.checkpoints_dir, f)
            for f in sorted(os.listdir(self.checkpoints_dir))
            if f.startswith("part_") and f.endswith(".parquet")
        ]

        if not parquet_parts:
            print("⚠️  Nenhum parquet parcial encontrado para consolidar.")
            return

        print(f"📂 Combinando {len(parquet_parts)} partes parciais...")
        dfs = [pd.read_parquet(p) for p in parquet_parts]
        df_final = pd.concat(dfs, ignore_index=True)

        id_col = "Match_ID" if "Match_ID" in df_final.columns else "Id"
        df_final = df_final.drop_duplicates(subset=[id_col])

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        final_parquet = os.path.join(
            self.final_dir, f"jogos_consolidados_{self.slice_slug}_{ts}.parquet"
        )
        final_csv = os.path.join(
            self.final_dir, f"jogos_consolidados_{self.slice_slug}_{ts}.csv"
        )

        print(f"💾 Gravando Parquet Final ({len(df_final):,} partidas)...")
        df_final.to_parquet(final_parquet, index=False)

        print(f"💾 Gravando CSV Final ({len(df_final):,} partidas)...")
        df_final.to_csv(final_csv, index=False, encoding="utf-8")

        print("\n" + "=" * 80)
        print("✅ PROCESSO DE ATUALIZAÇÃO CONCLUÍDO!")
        print(f"📁 Parquet: {final_parquet}")
        print(f"📁 CSV:     {final_csv}")
        print(f"📁 Zips:    {self.zips_dir}")
        print("=" * 80)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ultra Scraper Flash v2 — Atualização Massiva de Partidas (Async)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:

  # Notebook 1/4 no Colab, proxies 1 e 3, delay de 0.1s nas odds
  !python ultra_updater_massivo.py --slice 1/4 --proxies 1,3 --delay-odds 0.1

  # Notebook 2/4 no Colab, apenas IP direto, 12 workers
  !python ultra_updater_massivo.py --slice 2/4 --workers 12

  # Teste local com parquet local
  !python ultra_updater_massivo.py --parquet ./db/jogos.parquet --slice 1/1 --workers 4
""",
    )

    parser.add_argument(
        "--parquet",
        type=str,
        default="https://github.com/gatodegravata/flashscore/raw/main/db/jogos_consolidados.parquet",
        help="Caminho local ou URL do parquet mestre",
    )
    parser.add_argument("--workers", type=int, default=8, help="Número de coroutines simultâneas")
    parser.add_argument(
        "--batch-size", type=int, default=10_000,
        help="Tamanho do lote (também é o intervalo de salvar o ZIP bruto)"
    )
    parser.add_argument("--output-dir", type=str, default="dataset_completo", help="Diretório de saída")
    parser.add_argument(
        "--proxies",
        type=str,
        default=None,
        help="Índices dos proxies do .env a usar, separados por vírgula (ex: '1,3,4'). "
             "IP direto do Colab é sempre incluído como slot 0.",
    )
    parser.add_argument(
        "--slice",
        type=str,
        default=None,
        help="Fatia da base para paralelismo em múltiplos Colabs (ex: '1/4', '2/4')",
    )

    # Delays por endpoint
    parser.add_argument(
        "--delay-sumario", type=float, default=0.0,
        help="Delay (segundos) após cada request bem-sucedido ao df_sui (sumário)"
    )
    parser.add_argument(
        "--delay-stats", type=float, default=0.0,
        help="Delay (segundos) após cada request bem-sucedido ao df_st (estatísticas)"
    )
    parser.add_argument(
        "--delay-odds", type=float, default=0.0,
        help="Delay (segundos) após cada request bem-sucedido ao GraphQL OCE (odds)"
    )
    parser.add_argument(
        "--save-every", type=int, default=10_000,
        help="Salva parquet parcial a cada N jogos processados (default: 10000)"
    )
    parser.add_argument(
        "--direct-workers", type=int, default=0,
        help=(
            "Número de workers exclusivamente no IP direto do Colab (slot 0). "
            "Os demais workers distribuem-se entre os proxies. "
            "0 = distribuição uniforme entre IP + proxies (default)."
        )
    )

    args = parser.parse_args()

    # Parse dos índices de proxy
    proxy_indices: Optional[List[int]] = None
    if args.proxies:
        try:
            proxy_indices = [int(x.strip()) for x in args.proxies.split(",") if x.strip()]
        except ValueError:
            print(f"⚠️  --proxies inválido: '{args.proxies}'. Usando apenas IP direto.")

    updater = UltraUpdaterAsync(
        parquet_source=args.parquet,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        workers=args.workers,
        proxy_indices=proxy_indices,
        slice_part=args.slice,
        delay_sumario=args.delay_sumario,
        delay_stats=args.delay_stats,
        delay_odds=args.delay_odds,
        save_every=args.save_every,
        direct_workers=args.direct_workers,
    )
    updater.run()
