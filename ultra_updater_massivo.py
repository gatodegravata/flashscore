#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ ULTRA SCRAPER FLASH v3 — LOG JSON POR ENDPOINT + SYNC GITHUB ⚡
================================================================================
Novidades v3.0:
- SliceLog: log JSON por endpoint (sui/st/oce) por partida
  → Re-processa APENAS os endpoints faltantes (não pula a partida inteira)
  → Nunca rebaixa True → False: acumula o que já foi coletado
- Retry automático de endpoints incompletos antes de salvar o Parquet
  → 3 rounds com pausa de 15s e concorrência reduzida (menos agressivo)
- Parquet criado APENAS quando os 3 endpoints estão completos
- JSON individual por partida salvo atomicamente em json_cache/
- Sync do SliceLog com GitHub via API (sem commits sujos no histórico)
  → GITHUB_TOKEN lido do .env
  → log/ está no .gitignore — nunca vai parar no histórico do repo
================================================================================

Exemplo (Colab 1/4, proxies 1,2, 8 workers direto + 4 via proxy):
  !python ultra_updater_massivo.py --slice 1/4 --proxies 1,2 --workers 12 \\
      --direct-workers 8 --delay-odds 0.05 --save-every 500
================================================================================
"""

import os
import sys
import asyncio
import json
import time
import zipfile
import argparse
import re
import base64
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

try:
    from curl_cffi.requests import AsyncSession
    CURL_CFFI_ASYNC = True
except ImportError:
    CURL_CFFI_ASYNC = False
    print("Warning: curl_cffi nao encontrado — usando requests como fallback.")

from generate_df_jogos_passados import process_match_to_row


# ═══════════════════════════════════════════════════════════════════════════════
# LEITURA DO .ENV
# ═══════════════════════════════════════════════════════════════════════════════

def _read_env_file() -> Dict[str, str]:
    """Lê todas as variáveis do .env no diretório do script ou CWD."""
    env_map: Dict[str, str] = {}
    for env_path in [
        ".env",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    ]:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env_map[k.strip()] = v.strip()
            break
    return env_map


# ═══════════════════════════════════════════════════════════════════════════════
# CARREGAMENTO DE PROXIES DO .ENV
# ═══════════════════════════════════════════════════════════════════════════════

def load_proxies_from_env(
    indices: Optional[List[int]] = None,
    env_map: Optional[Dict[str, str]] = None,
) -> List[Tuple[Optional[str], str]]:
    """
    Lê WEBSHARE_PROXY_N do .env e retorna lista de (proxy_url, label).
    Slot 0 é sempre (None, "IP_DIRETO") — prioridade para economizar banda.
    """
    result: List[Tuple[Optional[str], str]] = [(None, "IP_DIRETO")]
    if env_map is None:
        env_map = _read_env_file()

    proxy_map: Dict[int, str] = {}
    for k, v in env_map.items():
        if k.startswith("WEBSHARE_PROXY_"):
            try:
                idx = int(k.replace("WEBSHARE_PROXY_", ""))
                proxy_map[idx] = v
            except ValueError:
                pass

    if not proxy_map:
        print("Aviso: Nenhum WEBSHARE_PROXY_N no .env — rodando so com IP direto.")
        return result

    targets = sorted(indices) if indices else sorted(proxy_map.keys())
    for idx in targets:
        if idx in proxy_map:
            result.append((proxy_map[idx], f"proxy_{idx}"))
        else:
            print(f"Aviso: WEBSHARE_PROXY_{idx} nao encontrado no .env.")

    print(f"Slots de proxy: {[lbl for _, lbl in result]}")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SLICE LOG — RASTREAMENTO POR ENDPOINT + SYNC GITHUB
# ═══════════════════════════════════════════════════════════════════════════════

class SliceLog:
    """
    Rastreia o status de scraping por endpoint (sui/st/oce) para cada match_id.
    Persistido como JSON local em log/slice_X_Y.json.
    Sincronizado com GitHub via Contents API (sem criar commits no histórico).

    Estrutura do JSON:
    {
      "matchABC": {"sui": true,  "st": true,  "oce": false, "ts": "2026-08-22T10:05:31"},
      "matchDEF": {"sui": true,  "st": true,  "oce": true,  "ts": "2026-08-22T10:06:00"}
    }

    Regra de "completo": sui AND st AND oce == True
    Uma entrada True NUNCA é rebaixada para False.
    """

    LOG_DIR = "log"

    def __init__(self, slice_slug: str, github_token: Optional[str], github_repo: str):
        self.slice_slug = slice_slug
        self.github_token = github_token
        self.github_repo = github_repo
        self.log_filename = f"slice_{slice_slug}.json"
        self.log_path = os.path.join(self.LOG_DIR, self.log_filename)
        self.github_api_path = f"log/{self.log_filename}"
        self._sha: Optional[str] = None  # SHA necessário para update via GitHub API
        self.data: Dict[str, Dict] = {}
        os.makedirs(self.LOG_DIR, exist_ok=True)

    # ── Carregamento ──────────────────────────────────────────────────────────

    def load(self):
        """Tenta carregar do GitHub (estado mais atual); fallback para arquivo local."""
        if self.github_token:
            remote = self._fetch_from_github()
            if remote is not None:
                self.data = remote
                print(f"[GITHUB] Log carregado: {len(self.data):,} partidas rastreadas.")
                self._save_local()
                return

        if os.path.exists(self.log_path):
            with open(self.log_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            print(f"[LOCAL] Log carregado: {len(self.data):,} partidas rastreadas.")
        else:
            self.data = {}
            print(f"[NOVO] Log criado para slice [{self.slice_slug}].")

    def _fetch_from_github(self) -> Optional[Dict]:
        """GET via GitHub Contents API. Retorna dict ou None."""
        url = (
            f"https://api.github.com/repos/{self.github_repo}"
            f"/contents/{self.github_api_path}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read())
                self._sha = payload.get("sha")
                raw = base64.b64decode(payload["content"]).decode("utf-8")
                return json.loads(raw)
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code != 404:
                print(f"Aviso: erro ao buscar log do GitHub: {exc}")
            return None

    # ── Persistência ──────────────────────────────────────────────────────────

    def _save_local(self):
        """Escrita atômica: arquivo temporário + rename (seguro contra crash)."""
        tmp = self.log_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, self.log_path)

    def save(self):
        """Salva no disco local."""
        self._save_local()

    def push_to_github(self) -> bool:
        """
        PUT do log para GitHub via Contents API.
        Cria o arquivo se não existir (sem SHA), atualiza se existir (com SHA).
        Retorna True se bem-sucedido.
        """
        if not self.github_token:
            return False

        content_b64 = base64.b64encode(
            json.dumps(self.data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")

        url = (
            f"https://api.github.com/repos/{self.github_repo}"
            f"/contents/{self.github_api_path}"
        )
        payload: Dict[str, Any] = {
            "message": (
                f"[log] slice {self.slice_slug}: "
                f"{self.count_complete():,}/{self.count_total():,} completas"
            ),
            "content": content_b64,
        }
        if self._sha:
            payload["sha"] = self._sha

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
            },
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                result = json.loads(resp.read())
                self._sha = result.get("content", {}).get("sha")
            print(
                f"[GITHUB] Log sincronizado: "
                f"{self.count_complete():,}/{self.count_total():,} completas."
            )
            return True
        except Exception as exc:
            print(f"Aviso: erro ao sincronizar log com GitHub: {exc}")
            return False

    # ── Consultas ──────────────────────────────────────────────────────────────

    def is_complete(self, mid: str) -> bool:
        """True se os 3 endpoints foram coletados com sucesso."""
        e = self.data.get(mid, {})
        return bool(e.get("sui") and e.get("st") and e.get("oce"))

    def get_missing(self, mid: str) -> Tuple[bool, bool, bool]:
        """Retorna (need_sui, need_st, need_oce). True = precisa coletar."""
        e = self.data.get(mid, {})
        return (
            not e.get("sui", False),
            not e.get("st", False),
            not e.get("oce", False),
        )

    def update(self, mid: str, sui: bool, st: bool, oce: bool):
        """Atualiza status. Nunca rebaixa True para False."""
        e = self.data.get(mid, {})
        self.data[mid] = {
            "sui": e.get("sui", False) or sui,
            "st":  e.get("st",  False) or st,
            "oce": e.get("oce", False) or oce,
            "ts":  datetime.now().isoformat(),
        }

    def count_complete(self) -> int:
        return sum(
            1 for v in self.data.values()
            if v.get("sui") and v.get("st") and v.get("oce")
        )

    def count_total(self) -> int:
        return len(self.data)

    def stats_str(self) -> str:
        """Resumo legível: sui=N st=N oce=N completos=N/total"""
        sui = sum(1 for v in self.data.values() if v.get("sui"))
        st  = sum(1 for v in self.data.values() if v.get("st"))
        oce = sum(1 for v in self.data.values() if v.get("oce"))
        return (
            f"sui={sui:,} st={st:,} oce={oce:,} "
            f"completos={self.count_complete():,}/{self.count_total():,}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTES HTTP
# ═══════════════════════════════════════════════════════════════════════════════

FSIGN = "SW9D1eZo"
FEED_BASE  = "https://global.flashscore.ninja/2/x/feed"
GRAPHQL_BASE = "https://global.ds.lsapp.eu/odds/pq_graphql"

HEADERS_FEED = {
    "Referer": "https://www.flashscore.com/",
    "Origin":  "https://www.flashscore.com",
    "x-fsign": FSIGN,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}
HEADERS_GRAPHQL = {
    "Referer": "https://www.flashscore.com/",
    "Origin":  "https://www.flashscore.com",
    "Accept":  "*/*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP HELPER ASSÍNCRONO
# ═══════════════════════════════════════════════════════════════════════════════

async def _async_get_with_retry(
    session: Any,
    url: str,
    headers: dict,
    endpoint_label: str,
    match_id: str,
    proxy_label: str,
    max_attempts: int = 3,
) -> Optional[Any]:
    """GET assíncrono com backoff exponencial. Retorna Response ou None."""
    for attempt in range(max_attempts):
        try:
            resp = await session.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(
                    f"\n[RATE LIMIT 429] endpoint={endpoint_label} | match={match_id} | "
                    f"proxy={proxy_label} | tentativa={attempt+1}/{max_attempts} | wait={wait}s"
                )
                await asyncio.sleep(wait)
                continue
            elif resp.status_code == 403:
                print(
                    f"\n[BLOQUEIO 403] endpoint={endpoint_label} | "
                    f"match={match_id} | proxy={proxy_label}"
                )
                return None
            elif resp.status_code != 200:
                if proxy_label != "IP_DIRETO":
                    print(
                        f"\n[HTTP {resp.status_code}] endpoint={endpoint_label} | "
                        f"match={match_id} | proxy={proxy_label}"
                    )
                return None
            return resp
        except asyncio.CancelledError:
            raise
        except Exception:
            if attempt == max_attempts - 1:
                return None
            await asyncio.sleep(0.3)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SCRAPER ASSÍNCRONO POR JOGO
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_match_async(
    session: Any,
    match_id: str,
    base_info: Dict[str, Any],
    proxy_label: str,
    delay_sumario: float = 0.0,
    delay_stats: float = 0.0,
    delay_odds: float = 0.0,
    need_sui: bool = True,
    need_st: bool = True,
    need_oce: bool = True,
) -> Dict[str, Any]:
    """
    Raspa os endpoints necessários de uma partida.

    Args:
        base_info: dados base + quaisquer campos já coletados anteriormente.
                   O dict retornado começa como cópia de base_info, garantindo
                   que campos existentes (de scrapers anteriores) sejam preservados.
        need_sui / need_st / need_oce:
                   False = endpoint já foi coletado — pular completamente.

    Flags de diagnóstico no dict retornado:
        _scraped_sui / _scraped_st / _scraped_oce : bool
        (preservados de base_info se o endpoint foi pulado)
    """
    match_data = base_info.copy()
    match_data.setdefault("Id", match_id)
    match_data.setdefault("Match_ID", match_id)
    # Preserva flags de scrapers anteriores (setdefault não sobrescreve)
    match_data.setdefault("_scraped_sui", False)
    match_data.setdefault("_scraped_st",  False)
    match_data.setdefault("_scraped_oce", False)

    # ── 1. df_sui (Sumário / Gols) ────────────────────────────────────────────
    if need_sui:
        url_sui = f"{FEED_BASE}/df_sui_1_{match_id}"
        resp_sui = await _async_get_with_retry(
            session, url_sui, HEADERS_FEED, "df_sui", match_id, proxy_label
        )
        match_data["Min_Goals_Home"] = []
        match_data["Min_Goals_Away"] = []

        if resp_sui and resp_sui.text:
            match_data["_scraped_sui"] = True
            if delay_sumario > 0:
                await asyncio.sleep(delay_sumario)

            for event in resp_sui.text.split('~'):
                is_goal = False
                if any(x in event for x in [
                    'IE÷3','IE÷4','IE÷10',
                    'IE\xf73','IE\xf74','IE\xf710',
                    'IE\xac3','IE\xac4','IE\xac10',
                ]):
                    is_goal = True
                elif ('Goal' in event or 'Penalty' in event) and 'Missed' not in event and 'Awarded' not in event:
                    is_goal = True
                elif ('IK÷Penalty' in event or 'IK\xf7Penalty' in event or 'IK\xacPenalty' in event) and 'Missed' not in event:
                    is_goal = True

                if is_goal:
                    is_home = any(h in event for h in ['IA÷1','IA\xf71','IA\xac1'])
                    is_away = any(a in event for a in ['IA÷2','IA\xf72','IA\xac2'])
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
                resp_dc = await session.get(
                    f"{FEED_BASE}/dc_1_{match_id}", headers=HEADERS_FEED, timeout=5.0
                )
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
    if need_st:
        url_st = f"{FEED_BASE}/df_st_1_{match_id}"
        resp_st = await _async_get_with_retry(
            session, url_st, HEADERS_FEED, "df_st", match_id, proxy_label
        )
        stats_data: Dict[str, Any] = {
            "Statistics_FT": {}, "Statistics_HT": {}, "Statistics_2T": {}
        }
        if resp_st and resp_st.text:
            match_data["_scraped_st"] = True
            if delay_stats > 0:
                await asyncio.sleep(delay_stats)

            current_stage = "Statistics_FT"
            for sec in resp_st.text.split('~'):
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
                    stats_data[current_stage][stat_name] = {
                        "Home": _parse_stat(m_sh.group(1).strip()),
                        "Away": _parse_stat(m_si.group(1).strip()),
                    }
        match_data.update(stats_data)

    # ── 3. GraphQL OCE (Odds) ─────────────────────────────────────────────────
    if need_oce:
        url_oce = f"{GRAPHQL_BASE}?_hash=oce&eventId={match_id}&projectId=2"
        resp_oce = await _async_get_with_retry(
            session, url_oce, HEADERS_GRAPHQL, "GraphQL_OCE", match_id, proxy_label
        )
        if resp_oce:
            try:
                match_data["_scraped_oce"] = True
                if delay_odds > 0:
                    await asyncio.sleep(delay_odds)
                match_data.update(_parse_odds(resp_oce.json()))
            except Exception:
                match_data.update(_empty_odds())
        else:
            # Garante que as chaves existam (vazias) mesmo sem dados
            for k, v in _empty_odds().items():
                match_data.setdefault(k, v)

    return match_data


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_stat(val_str: str) -> Any:
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
        "Odds_OU_FT":  {}, "Odds_OU_HT":  {}, "Odds_OU_2T":  {},
        "Odds_BTTS_FT": [], "Odds_BTTS_HT": [], "Odds_BTTS_2T": [],
        "Odds_DC_FT":  [], "Odds_DC_HT":  [], "Odds_DC_2T":  [],
        "Odds_DNB_FT": [], "Odds_DNB_HT": [], "Odds_DNB_2T": [],
        "Odds_AH_FT":  {}, "Odds_AH_HT":  {}, "Odds_AH_2T":  {},
        "Odds_EH_FT":  {}, "Odds_EH_HT":  {}, "Odds_EH_2T":  {},
        "Odds_HT_FT":  {},
        "Odds_OE_FT":  [], "Odds_OE_HT":  [], "Odds_OE_2T":  [],
        "Odds_CS_FT":  {}, "Odds_CS_HT":  {}, "Odds_CS_2T":  {},
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

    bk_map: Dict[Any, str] = {}
    for pb in data_body.get("settings", {}).get("bookmakers", []):
        bm = pb.get("bookmaker", {})
        if bm.get("id") and bm.get("name"):
            bk_map[bm["id"]] = bm["name"]

    odds_list = data_body.get("odds", [])
    home_p_id, away_p_id = None, None
    for item in odds_list:
        if item.get("bettingType") == "HOME_DRAW_AWAY" and item.get("bettingScope") == "FULL_TIME":
            for o in item.get("odds", []):
                p = o.get("eventParticipantId")
                if p:
                    if home_p_id is None:
                        home_p_id = p
                    elif away_p_id is None and p != home_p_id:
                        away_p_id = p
            if home_p_id and away_p_id:
                break

    for item in odds_list:
        b_id   = item.get("bookmakerId")
        bname  = bk_map.get(b_id, f"Bookmaker_{b_id}")
        b_type = item.get("bettingType")
        b_scope = item.get("bettingScope")
        sub    = item.get("odds", [])

        def _sk(ft: str, ht: str, t2: str) -> str:
            return ft if b_scope == "FULL_TIME" else (ht if b_scope == "FIRST_HALF" else t2)

        def _td(ft: str, ht: str, t2: str) -> Dict:
            return result[_sk(ft, ht, t2)]

        if b_type == "HOME_DRAW_AWAY":
            o1 = ox = o2 = None
            for o in sub:
                v = _safe_float(o.get("value"))
                p = o.get("eventParticipantId")
                if p is None: ox = v
                elif p == home_p_id or (home_p_id is None and o1 is None): o1 = v
                else: o2 = v
            k = _sk("Odds_1X2_FT", "Odds_1X2_HT", "Odds_1X2_2T")
            if o1 or ox or o2:
                result[k].append({"Bookmaker": bname, "Odd_1": o1, "Odd_X": ox, "Odd_2": o2})

        elif b_type == "OVER_UNDER":
            td = _td("Odds_OU_FT", "Odds_OU_HT", "Odds_OU_2T")
            for o in sub:
                h_obj = o.get("handicap")
                h_val = h_obj.get("value") if isinstance(h_obj, dict) else h_obj
                sel = str(o.get("selection", "")).upper()
                v = _safe_float(o.get("value"))
                if h_val:
                    key = f"OU_{h_val}"
                    td.setdefault(key, [])
                    entry = next((e for e in td[key] if e["Bookmaker"] == bname), None)
                    if not entry:
                        entry = {"Bookmaker": bname, "Over": None, "Under": None}
                        td[key].append(entry)
                    if "OVER" in sel: entry["Over"] = v
                    elif "UNDER" in sel: entry["Under"] = v

        elif b_type == "BOTH_TEAMS_TO_SCORE":
            yes_v = no_v = None
            for o in sub:
                v = _safe_float(o.get("value"))
                if o.get("bothTeamsToScore") is True or str(o.get("selection","")).upper()=="YES":
                    yes_v = v
                else:
                    no_v = v
            k = _sk("Odds_BTTS_FT", "Odds_BTTS_HT", "Odds_BTTS_2T")
            if yes_v or no_v:
                result[k].append({"Bookmaker": bname, "Yes": yes_v, "No": no_v})

        elif b_type == "DOUBLE_CHANCE":
            dc1x = dc12 = dcx2 = None
            for o in sub:
                p = o.get("eventParticipantId")
                v = _safe_float(o.get("value"))
                sel = str(o.get("selection","")).upper() if o.get("selection") else ""
                if "1X" in sel or sel == "HOME_DRAW" or p == home_p_id: dc1x = v
                elif "12" in sel or sel == "HOME_AWAY" or (p is None and v is not None): dc12 = v
                elif "X2" in sel or sel == "DRAW_AWAY" or p == away_p_id: dcx2 = v
            k = _sk("Odds_DC_FT", "Odds_DC_HT", "Odds_DC_2T")
            if dc1x or dc12 or dcx2:
                result[k].append({"Bookmaker": bname, "Odd_1X": dc1x, "Odd_12": dc12, "Odd_X2": dcx2})

        elif b_type == "DRAW_NO_BET":
            d1 = d2 = None
            for o in sub:
                p = o.get("eventParticipantId")
                v = _safe_float(o.get("value"))
                if p == home_p_id or (home_p_id is None and d1 is None): d1 = v
                else: d2 = v
            k = _sk("Odds_DNB_FT", "Odds_DNB_HT", "Odds_DNB_2T")
            if d1 or d2:
                result[k].append({"Bookmaker": bname, "Home": d1, "Away": d2})

        elif b_type == "ASIAN_HANDICAP":
            td = _td("Odds_AH_FT", "Odds_AH_HT", "Odds_AH_2T")
            for o in sub:
                p = o.get("eventParticipantId")
                h_obj = o.get("handicap")
                h_raw = h_obj.get("value") if isinstance(h_obj, dict) else h_obj
                v = _safe_float(o.get("value"))
                if h_raw is not None and v is not None:
                    try: h_num = float(h_raw)
                    except ValueError: continue
                    if p == away_p_id and away_p_id is not None:
                        lk = f"{(-h_num):+.1f}" if (-h_num) != 0 else "0.0"; hs = False
                    else:
                        lk = f"{h_num:+.1f}" if h_num != 0 else "0.0"; hs = True
                    key = f"AH_{lk}"
                    td.setdefault(key, [])
                    entry = next((e for e in td[key] if e["Bookmaker"] == bname), None)
                    if not entry:
                        entry = {"Bookmaker": bname, "Home": None, "Away": None}
                        td[key].append(entry)
                    if hs: entry["Home"] = v
                    else:  entry["Away"] = v

        elif b_type == "EUROPEAN_HANDICAP":
            td = _td("Odds_EH_FT", "Odds_EH_HT", "Odds_EH_2T")
            for o in sub:
                p = o.get("eventParticipantId")
                h_obj = o.get("handicap")
                h_raw = h_obj.get("value") if isinstance(h_obj, dict) else h_obj
                v = _safe_float(o.get("value"))
                if h_raw is not None and v is not None:
                    try: h_num = int(float(h_raw))
                    except ValueError: continue
                    key = f"EH_{h_num:+d}"
                    td.setdefault(key, [])
                    entry = next((e for e in td[key] if e["Bookmaker"] == bname), None)
                    if not entry:
                        entry = {"Bookmaker": bname, "Home": None, "Draw": None, "Away": None}
                        td[key].append(entry)
                    if p is None: entry["Draw"] = v
                    elif p == home_p_id or (home_p_id is None and entry["Home"] is None): entry["Home"] = v
                    else: entry["Away"] = v

        elif b_type == "HALF_FULL_TIME" and b_scope == "FULL_TIME":
            for o in sub:
                winner = o.get("winner")
                v = _safe_float(o.get("value"))
                if winner and v:
                    key = winner.replace("/", "_")
                    result["Odds_HT_FT"].setdefault(key, [])
                    result["Odds_HT_FT"][key].append({"Bookmaker": bname, "Odd": v})

        elif b_type == "ODD_OR_EVEN":
            ov = ev = None
            for o in sub:
                sel = str(o.get("selection","")).upper()
                v = _safe_float(o.get("value"))
                if "ODD" in sel: ov = v
                elif "EVEN" in sel: ev = v
            k = _sk("Odds_OE_FT", "Odds_OE_HT", "Odds_OE_2T")
            if ov or ev:
                result[k].append({"Bookmaker": bname, "Odd": ov, "Even": ev})

        elif b_type == "CORRECT_SCORE":
            td = _td("Odds_CS_FT", "Odds_CS_HT", "Odds_CS_2T")
            for o in sub:
                sc = o.get("score")
                v = _safe_float(o.get("value"))
                if sc and v:
                    td.setdefault(sc, [])
                    td[sc].append({"Bookmaker": bname, "Odd": v})

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
# ORQUESTRADOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class UltraUpdaterAsync:
    MAX_RETRY_ROUNDS  = 3   # rounds de retry de endpoints incompletos por batch
    RETRY_PAUSE_SEC   = 15  # pausa entre rounds (deixa rate-limit esfriar)
    RETRY_CONCURRENCY = 3   # semaphore nos retries (mais conservador)

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
        save_every: int = 500,
        direct_workers: int = 0,
        github_repo: str = "gatodegravata/flashscore",
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
        self.direct_workers = direct_workers

        self.slice_slug = slice_part.replace("/", "_") if slice_part else "all"

        # Diretórios de saída
        self.json_cache_dir  = os.path.join(output_dir, "json_cache", self.slice_slug)
        self.zips_dir        = os.path.join(output_dir, "zips_json_bruto")
        self.checkpoints_dir = os.path.join(output_dir, "checkpoints")
        self.final_dir       = os.path.join(output_dir, "consolidado_final")
        for d in [self.json_cache_dir, self.zips_dir, self.checkpoints_dir, self.final_dir]:
            os.makedirs(d, exist_ok=True)

        # Lê .env uma única vez
        env_map = _read_env_file()
        github_token = env_map.get("GITHUB_TOKEN") or None
        if github_token:
            print(f"[ENV] GITHUB_TOKEN encontrado — sync ativo para {github_repo}")
        else:
            print("[ENV] GITHUB_TOKEN ausente — sync com GitHub desativado.")

        # Proxies
        self.proxy_slots = load_proxies_from_env(proxy_indices, env_map=env_map)

        # SliceLog
        self.slice_log = SliceLog(
            slice_slug=self.slice_slug,
            github_token=github_token,
            github_repo=github_repo,
        )
        self.slice_log.load()

    # ── JSON cache helpers ────────────────────────────────────────────────────

    def _save_json_match(self, mid: str, data: Dict[str, Any]):
        """Salva JSON individual de uma partida (escrita atômica)."""
        path = os.path.join(self.json_cache_dir, f"{mid}.json")
        tmp  = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    def _load_json_match(self, mid: str) -> Optional[Dict[str, Any]]:
        """Carrega JSON individual de uma partida se existir."""
        path = os.path.join(self.json_cache_dir, f"{mid}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    # ── run() ─────────────────────────────────────────────────────────────────

    def run(self):
        print("\n" + "=" * 80)
        print("ULTRA SCRAPER FLASH v3 — LOG JSON POR ENDPOINT + SYNC GITHUB")
        print("=" * 80)

        print(f"Carregando base mestre: {self.parquet_source} ...")
        df_master = pd.read_parquet(self.parquet_source)
        print(f"Total: {len(df_master):,} registros")

        id_col = (
            "Match_ID" if "Match_ID" in df_master.columns
            else ("Id" if "Id" in df_master.columns else df_master.columns[0])
        )
        df_master = df_master.drop_duplicates(subset=[id_col])

        # Slice
        if self.slice_part:
            try:
                part_idx, total_parts = map(int, self.slice_part.split("/"))
                chunk_len = len(df_master) // total_parts
                start_row = (part_idx - 1) * chunk_len
                end_row = len(df_master) if part_idx == total_parts else part_idx * chunk_len
                df_master = df_master.iloc[start_row:end_row].copy()
                print(f"Fatia [{self.slice_part}]: {len(df_master):,} partidas")
            except Exception as exc:
                print(f"Aviso: erro ao interpretar --slice: {exc}")

        # Filtra só as que ainda não estão completas no SliceLog
        pending_mask = ~df_master[id_col].astype(str).apply(self.slice_log.is_complete)
        df_pending = df_master[pending_mask].copy()
        total_pending = len(df_pending)
        print(
            f"Pendentes: {total_pending:,} | "
            f"Completas no log: {self.slice_log.count_complete():,}"
        )

        if total_pending == 0:
            print("Tudo ja processado! Consolidando saida final...")
            self._consolidate_final_output()
            return

        pending_records = df_pending.to_dict(orient="records")
        num_batches = (total_pending + self.batch_size - 1) // self.batch_size
        print(
            f"{total_pending:,} partidas em {num_batches} lote(s) de {self.batch_size:,}.\n"
            f"Workers={self.workers} | Direct={self.direct_workers} | "
            f"Slots={[lbl for _, lbl in self.proxy_slots]} | "
            f"save_every={self.save_every} completas | "
            f"Delays: sui={self.delay_sumario}s st={self.delay_stats}s oce={self.delay_odds}s"
        )

        for batch_idx in range(num_batches):
            start_i = batch_idx * self.batch_size
            end_i   = min(start_i + self.batch_size, total_pending)
            asyncio.run(
                self._process_batch_async(
                    batch_idx + 1, num_batches, pending_records[start_i:end_i], id_col
                )
            )

        self._consolidate_final_output()

    # ── Passo 1: main pass ────────────────────────────────────────────────────

    async def _process_batch_async(
        self,
        batch_num: int,
        total_batches: int,
        records: List[Dict[str, Any]],
        id_col: str,
    ):
        print("\n" + "=" * 80)
        print(f"LOTE [{batch_num}/{total_batches}] — {len(records):,} jogos")
        print("=" * 80)

        total_in_batch = len(records)
        t_start = time.time()

        completed = 0
        errors = 0
        complete_since_save = 0  # dispara save_every
        save_idx = [0]
        save_lock = asyncio.Lock()

        num_slots = len(self.proxy_slots)
        dw = self.direct_workers
        semaphore = asyncio.Semaphore(self.workers)

        def _proxy_for_slot(slot_id: int) -> Tuple[Optional[str], str]:
            if dw > 0:
                if slot_id < dw:
                    return self.proxy_slots[0]  # IP_DIRETO
                proxy_only = self.proxy_slots[1:]
                return proxy_only[(slot_id - dw) % len(proxy_only)] if proxy_only else self.proxy_slots[0]
            return self.proxy_slots[slot_id % num_slots]

        async def process_one(slot_id: int, meta: Dict[str, Any]):
            nonlocal completed, errors, complete_since_save

            mid = str(meta.get(id_col, "")).strip()
            if not mid:
                return

            proxy_url, proxy_label = _proxy_for_slot(slot_id % self.workers)

            async with semaphore:
                t0 = time.time()
                try:
                    need_sui, need_st, need_oce = self.slice_log.get_missing(mid)

                    # Base info: metadados do parquet + dados já coletados do JSON
                    existing = self._load_json_match(mid) or {}
                    base_info: Dict[str, Any] = {
                        "Id": mid, "Match_ID": mid,
                        "Date":        str(meta.get("Date", "")),
                        "Time":        str(meta.get("Time", "")),
                        "Round":       str(meta.get("Round", "")),
                        "Home":        str(meta.get("Home", "")),
                        "Home_ID":     str(meta.get("Home_ID", "")),
                        "Away":        str(meta.get("Away", "")),
                        "Away_ID":     str(meta.get("Away_ID", "")),
                        "Home_Score":  meta.get("Home_Score"),
                        "Away_Score":  meta.get("Away_Score"),
                        "Country":     str(meta.get("Country", "")),
                        "League":      str(meta.get("League", "")),
                        "Season":      str(meta.get("Season", "")),
                        "Sub_League":  str(meta.get("Sub_League", meta.get("League", ""))),
                        "Tournament_ID": str(meta.get("Tournament_ID", "")),
                        "Neutral_Location": meta.get("Neutral_Location", False),
                        **existing,  # sobrescreve com dados já coletados
                    }

                    session_kw: Dict[str, Any] = {}
                    if CURL_CFFI_ASYNC:
                        session_kw["impersonate"] = "chrome120"
                    if proxy_url:
                        session_kw["proxies"] = {"http": proxy_url, "https": proxy_url}

                    async with AsyncSession(**session_kw) as session:
                        full_match = await scrape_match_async(
                            session, mid, base_info, proxy_label,
                            delay_sumario=self.delay_sumario,
                            delay_stats=self.delay_stats,
                            delay_odds=self.delay_odds,
                            need_sui=need_sui,
                            need_st=need_st,
                            need_oce=need_oce,
                        )

                    elapsed = time.time() - t0

                    # Atualiza SliceLog + salva JSON individual
                    self.slice_log.update(
                        mid,
                        full_match.get("_scraped_sui", False),
                        full_match.get("_scraped_st",  False),
                        full_match.get("_scraped_oce", False),
                    )
                    self._save_json_match(mid, full_match)

                    is_complete = self.slice_log.is_complete(mid)
                    sui_i = "+" if full_match.get("_scraped_sui") else "-"
                    st_i  = "+" if full_match.get("_scraped_st")  else "-"
                    oce_i = "+" if full_match.get("_scraped_oce") else "-"

                    async with save_lock:
                        completed += 1
                        if is_complete:
                            complete_since_save += 1
                        curr = completed

                        if curr % 25 == 0 or curr == total_in_batch:
                            speed = curr / (time.time() - t_start + 0.001)
                            print(
                                f"  [{curr:6d}/{total_in_batch:6d}] ({speed:5.1f} j/s) | "
                                f"S{sui_i} ST{st_i} O{oce_i} | {proxy_label} | "
                                f"{base_info['Home']} vs {base_info['Away']} ({elapsed:.2f}s)"
                            )

                        # Save periódico do SliceLog
                        if complete_since_save >= self.save_every:
                            save_idx[0] += 1
                            self.slice_log.save()
                            self.slice_log.push_to_github()
                            complete_since_save = 0
                            print(
                                f"\n  [LOG #{save_idx[0]}] {self.slice_log.stats_str()}"
                            )

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    async with save_lock:
                        errors += 1
                    print(f"  ERRO [slot {slot_id}] {mid} ({proxy_label}): {exc}")

        # ── Dispara todas as tasks do main pass ───────────────────────────────
        tasks = [
            asyncio.create_task(process_one(i % self.workers, rec))
            for i, rec in enumerate(records)
        ]
        await asyncio.gather(*tasks)

        # ── Passo 2: Retry dos endpoints incompletos ──────────────────────────
        incomplete = [
            (str(rec.get(id_col, "")), rec)
            for rec in records
            if not self.slice_log.is_complete(str(rec.get(id_col, "")))
        ]

        if incomplete:
            print(
                f"\nRETRY: {len(incomplete)} partidas incompletas "
                f"({self.MAX_RETRY_ROUNDS} rounds, pausa {self.RETRY_PAUSE_SEC}s)"
            )
            print(f"Status atual: {self.slice_log.stats_str()}")
            await self._retry_incomplete(incomplete)

        # ── Passo 3: Parquet APENAS das completas ─────────────────────────────
        complete_mids = {
            str(rec.get(id_col, ""))
            for rec in records
            if self.slice_log.is_complete(str(rec.get(id_col, "")))
        }
        still_incomplete = len(records) - len(complete_mids)

        elapsed_batch = time.time() - t_start
        print(
            f"\nLote {batch_num}: "
            f"{len(complete_mids):,} completas | "
            f"{still_incomplete:,} incompletas | "
            f"{errors:,} erros | {elapsed_batch:.0f}s"
        )
        print(f"SliceLog: {self.slice_log.stats_str()}")

        if complete_mids:
            self._save_batch_parquet(batch_num, complete_mids)

        # ── Passo 4: ZIP de todos os JSONs do lote ────────────────────────────
        self._zip_batch_jsons(batch_num, [str(rec.get(id_col, "")) for rec in records])

        # ── Passo 5: Save final + push ────────────────────────────────────────
        self.slice_log.save()
        self.slice_log.push_to_github()

    # ── Passo 2 detalhe: retry de incompletos ─────────────────────────────────

    async def _retry_incomplete(self, incomplete: List[Tuple[str, Dict]]):
        """
        Retenta endpoints faltantes com concorrência reduzida e pausa entre rounds.
        Em cada round, só tenta as ainda incompletas.
        """
        sem = asyncio.Semaphore(self.RETRY_CONCURRENCY)
        num_slots = len(self.proxy_slots)

        async def retry_one(mid: str, meta: Dict, slot_id: int):
            need_sui, need_st, need_oce = self.slice_log.get_missing(mid)
            if not any([need_sui, need_st, need_oce]):
                return

            proxy_url, proxy_label = self.proxy_slots[slot_id % num_slots]

            async with sem:
                try:
                    session_kw: Dict[str, Any] = {}
                    if CURL_CFFI_ASYNC:
                        session_kw["impersonate"] = "chrome120"
                    if proxy_url:
                        session_kw["proxies"] = {"http": proxy_url, "https": proxy_url}

                    # Carrega JSON existente como base (preserva o que já foi coletado)
                    existing = self._load_json_match(mid) or {}
                    base_info: Dict[str, Any] = {"Id": mid, "Match_ID": mid, **existing}
                    # Complementa com metadados do Parquet se ausentes no JSON
                    for k in ["Home","Away","League","Country","Season",
                               "Sub_League","Tournament_ID","Home_Score","Away_Score"]:
                        base_info.setdefault(k, str(meta.get(k, "")) if k != "Home_Score" and k != "Away_Score" else meta.get(k))

                    async with AsyncSession(**session_kw) as session:
                        updated = await scrape_match_async(
                            session, mid, base_info, proxy_label,
                            delay_sumario=self.delay_sumario,
                            delay_stats=self.delay_stats,
                            delay_odds=self.delay_odds,
                            need_sui=need_sui,
                            need_st=need_st,
                            need_oce=need_oce,
                        )

                    # Salva JSON atualizado + atualiza SliceLog
                    self._save_json_match(mid, updated)
                    self.slice_log.update(
                        mid,
                        updated.get("_scraped_sui", False),
                        updated.get("_scraped_st",  False),
                        updated.get("_scraped_oce", False),
                    )

                    ok = "OK" if self.slice_log.is_complete(mid) else "~~"
                    sui_i = "+" if updated.get("_scraped_sui") else "-"
                    st_i  = "+" if updated.get("_scraped_st")  else "-"
                    oce_i = "+" if updated.get("_scraped_oce") else "-"
                    print(
                        f"    [{ok}] {mid} | S{sui_i} ST{st_i} O{oce_i} | {proxy_label}"
                    )
                except Exception as exc:
                    print(f"    RETRY ERRO: {mid} — {exc}")

        for round_num in range(1, self.MAX_RETRY_ROUNDS + 1):
            to_retry = [
                (mid, meta) for mid, meta in incomplete
                if not self.slice_log.is_complete(mid)
            ]
            if not to_retry:
                print(f"  Todos completos apos round {round_num - 1}!")
                break

            print(
                f"\n  [RETRY round {round_num}/{self.MAX_RETRY_ROUNDS}] "
                f"{len(to_retry)} partidas | pausa {self.RETRY_PAUSE_SEC}s..."
            )
            await asyncio.sleep(self.RETRY_PAUSE_SEC)

            retry_tasks = [
                asyncio.create_task(retry_one(mid, meta, i))
                for i, (mid, meta) in enumerate(to_retry)
            ]
            await asyncio.gather(*retry_tasks)

        final_incomplete = sum(1 for mid, _ in incomplete if not self.slice_log.is_complete(mid))
        if final_incomplete:
            print(f"\n  Aviso: {final_incomplete} partidas permanecem incompletas.")
        else:
            print(f"\n  Todos os {len(incomplete)} retries concluidos com sucesso!")

    # ── Salvar Parquet das completas ──────────────────────────────────────────

    def _save_batch_parquet(self, batch_num: int, complete_mids: set):
        """Salva Parquet parcial apenas com partidas onde sui+st+oce=True."""
        rows = []
        for mid in complete_mids:
            match_data = self._load_json_match(mid)
            if not match_data:
                continue
            try:
                row = process_match_to_row(
                    match_data=match_data,
                    league_name=match_data.get("League", ""),
                    country=match_data.get("Country", ""),
                    season=match_data.get("Season", ""),
                    sub_league=match_data.get("Sub_League"),
                    tournament_id=match_data.get("Tournament_ID"),
                )
                rows.append(row)
            except Exception as exc:
                print(f"  Aviso: erro ao converter {mid} para linha do Parquet: {exc}")

        if rows:
            fname = f"part_{self.slice_slug}_{batch_num:03d}.parquet"
            path  = os.path.join(self.checkpoints_dir, fname)
            pd.DataFrame(rows).to_parquet(path, index=False)
            print(f"\n  [PARQUET] {len(rows):,} partidas completas -> {path}")
        else:
            print(f"\n  Aviso: nenhuma partida completa no lote {batch_num}.")

    # ── ZIP de todos os JSONs do lote (completos + incompletos) ──────────────

    def _zip_batch_jsons(self, batch_num: int, mids: List[str]):
        """Compacta todos os JSONs do lote para referência e backup."""
        zip_path = os.path.join(
            self.zips_dir,
            f"lote_{self.slice_slug}_{batch_num:03d}.zip",
        )
        count = 0
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for mid in mids:
                json_path = os.path.join(self.json_cache_dir, f"{mid}.json")
                if os.path.exists(json_path):
                    zf.write(json_path, arcname=f"{mid}.json")
                    count += 1
        print(f"  [ZIP] {count} JSONs -> {zip_path}")

    # ── Consolidação final ────────────────────────────────────────────────────

    def _consolidate_final_output(self):
        print("\n" + "=" * 80)
        print("CONSOLIDANDO ARQUIVOS FINAIS")
        print("=" * 80)

        parts = sorted([
            os.path.join(self.checkpoints_dir, f)
            for f in os.listdir(self.checkpoints_dir)
            if f.startswith("part_") and f.endswith(".parquet")
        ])
        if not parts:
            print("Aviso: nenhum parquet parcial encontrado.")
            return

        print(f"Combinando {len(parts)} partes...")
        df_final = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
        id_col = "Match_ID" if "Match_ID" in df_final.columns else "Id"
        df_final = df_final.drop_duplicates(subset=[id_col])

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        pq_path  = os.path.join(self.final_dir, f"jogos_{self.slice_slug}_{ts}.parquet")
        csv_path = os.path.join(self.final_dir, f"jogos_{self.slice_slug}_{ts}.csv")

        df_final.to_parquet(pq_path,  index=False)
        df_final.to_csv(csv_path,     index=False, encoding="utf-8")

        print(
            f"{len(df_final):,} partidas finais.\n"
            f"Parquet: {pq_path}\nCSV: {csv_path}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ultra Scraper Flash v3 — Log JSON por Endpoint + Sync GitHub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:

  # Notebook 1/4, proxies 1,2, prioridade no IP direto
  !python ultra_updater_massivo.py --slice 1/4 --proxies 1,2 \\
      --workers 12 --direct-workers 8 --delay-odds 0.05

  # Notebook 2/4, so IP direto
  !python ultra_updater_massivo.py --slice 2/4 --workers 10

  # Salvar log mais frequentemente (a cada 200 completas)
  !python ultra_updater_massivo.py --slice 1/4 --save-every 200
""",
    )

    parser.add_argument(
        "--parquet", type=str,
        default="https://github.com/gatodegravata/flashscore/raw/main/db/jogos_consolidados.parquet",
        help="Caminho local ou URL do parquet mestre",
    )
    parser.add_argument("--workers",     type=int, default=8,      help="Coroutines simultaneas")
    parser.add_argument("--batch-size",  type=int, default=10_000, help="Tamanho do lote")
    parser.add_argument("--output-dir",  type=str, default="dataset_completo")
    parser.add_argument(
        "--proxies", type=str, default=None,
        help="Indices de proxy do .env separados por virgula (ex: '1,3')",
    )
    parser.add_argument(
        "--slice", type=str, default=None,
        help="Fatia da base (ex: '1/4', '2/4')",
    )
    parser.add_argument("--delay-sumario", type=float, default=0.0)
    parser.add_argument("--delay-stats",   type=float, default=0.0)
    parser.add_argument("--delay-odds",    type=float, default=0.0)
    parser.add_argument(
        "--save-every", type=int, default=500,
        help="Salva SliceLog e sincroniza GitHub a cada N partidas COMPLETAS (default: 500)",
    )
    parser.add_argument(
        "--direct-workers", type=int, default=0,
        help="Workers exclusivos no IP direto do Colab (0 = distribuicao uniforme)",
    )
    parser.add_argument(
        "--github-repo", type=str, default="gatodegravata/flashscore",
        help="Repositorio GitHub para sync do log (formato: owner/repo)",
    )

    args = parser.parse_args()

    proxy_indices: Optional[List[int]] = None
    if args.proxies:
        try:
            proxy_indices = [int(x.strip()) for x in args.proxies.split(",") if x.strip()]
        except ValueError:
            print(f"Aviso: --proxies invalido '{args.proxies}'. Usando so IP direto.")

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
        github_repo=args.github_repo,
    )
    updater.run()
