#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper de Jogos Futuros - FlashScore
Coleta jogos de hoje, amanhã e depois de amanhã
Extrai todas as odds mas NÃO extrai estatísticas (jogos não aconteceram)
Tenta filtrar por países das ligas, se não conseguir pega tudo
"""

import os
import json
import time
import subprocess
from datetime import datetime, timedelta
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm
from flashscore_scraper import FlashScoreScraper

# ==================== EXTRAI LIGAS/PAÍSES DO CSV CONFIG ====================
def extract_allowed_leagues_from_config(config_file="ligas_config.csv"):
    """
    Carrega pares (PAÍS, SLUG_LIGA) cadastrados no ligas_config.csv
    Garante que só aceita a liga se o PAÍS bater exatamente com a URL/configuração
    """
    allowed_countries = set()
    allowed_league_slugs = set()
    
    if os.path.exists(config_file):
        try:
            try:
                df = pd.read_csv(config_file, sep=';', encoding='utf-8-sig', dtype=str)
            except Exception:
                df = pd.read_csv(config_file, sep=',', encoding='utf-8', dtype=str)
            
            # 1. Países autorizados
            if 'pais' in df.columns:
                for p in df['pais'].dropna().unique():
                    p_clean = str(p).strip().upper()
                    if p_clean:
                        allowed_countries.add(p_clean)

            # 2. Slugs das URLs (ex: 'canada/championship', 'hungary/nb-i')
            if 'url' in df.columns:
                for u in df['url'].dropna().unique():
                    u_str = str(u).strip().lower()
                    if '/football/' in u_str:
                        parts = u_str.split('/football/')[1].split('/')
                        if len(parts) >= 1:
                            allowed_countries.add(parts[0].upper())
                        if len(parts) >= 2:
                            country = parts[0].upper()
                            slug_liga = parts[1].replace('-2021', '').replace('-2022', '').replace('-2023', '').replace('-2024', '').replace('-2025', '').replace('-2026', '').replace('-', ' ').upper()
                            allowed_league_slugs.add((country, slug_liga))

            print(f"✓ Config carregada: {len(allowed_countries)} países autorizados ({', '.join(sorted(list(allowed_countries)))})")
        except Exception as e:
            print(f"⚠️ Erro ao ler {config_file}: {e}")
            
    return allowed_countries, allowed_league_slugs

# Carrega ligas permitidas do arquivo de configuração
ALLOWED_COUNTRIES, ALLOWED_LEAGUE_SLUGS = extract_allowed_leagues_from_config()


def git_commit(message, file_path=None):
    """
    Faz commit automático no git e push para o GitHub
    Args:
        message: Mensagem do commit
        file_path: Arquivo específico para adicionar (opcional, se None adiciona tudo)
    """
    try:
        if file_path:
            subprocess.run(['git', 'add', file_path], check=True, capture_output=True)
        else:
            subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        
        result = subprocess.run(['git', 'commit', '-m', message], 
                              check=True, capture_output=True, text=True)
        print(f"  ✓ Git commit: {message}")
        
        # Push automático para o GitHub
        push_result = subprocess.run(['git', 'push'], 
                                    check=True, capture_output=True, text=True)
        print(f"  ✓ Git push: Enviado para GitHub")
        return True
    except subprocess.CalledProcessError:
        # Ignora erro (pode ser que não tenha mudanças para commitar)
        return False
    except Exception as e:
        print(f"  ⚠️ Erro no git commit/push: {e}")
        return False


def accept_cookies_if_present(driver):
    """Aceita cookies se aparecerem"""
    try:
        cookie_button = WebDriverWait(driver, 4).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'button#onetrust-accept-btn-handler'))
        )
        if cookie_button.is_displayed():
            driver.execute_script("arguments[0].click();", cookie_button)
            time.sleep(1)
            print("  ✓ Cookies aceitos")
    except Exception:
        pass


def go_to_future_day(driver, days_ahead: int):
    """
    Navega para dia futuro clicando no botão 'next'
    days_ahead: 0 = hoje, 1 = amanhã, 2 = depois de amanhã
    """
    if days_ahead <= 0:
        return
    
    try:
        # Espera o seletor de data aparecer
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="wcl-dayPicker"]'))
        )
        
        for i in range(days_ahead):
            # Encontra botão next
            next_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-day-picker-arrow="next"]'))
            )
            
            # Guarda referência de um elemento para detectar mudança
            try:
                ref = driver.find_element(By.CSS_SELECTOR, 'div.event__match--twoLine, div.event__match')
            except Exception:
                ref = None
            
            # Scroll e clique
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(1.5)
            
            # Espera a página atualizar
            if ref is not None:
                try:
                    WebDriverWait(driver, 8).until(EC.staleness_of(ref))
                except Exception:
                    pass
            
            print(f"  ✓ Navegou para +{i+1} dia(s)")
            
    except Exception as e:
        print(f"  ⚠️ Erro ao navegar para dia futuro: {e}")


def select_scheduled_tab(driver):
    """
    Clica na aba SCHEDULED (Programados) para filtrar apenas jogos que ainda NÃO começaram
    Elimina jogos encerrados e jogos ao vivo sem cotação pré-jogo.
    """
    try:
        # Tenta por XPath buscando texto SCHEDULED ou PROGRAMADOS
        scheduled_tab = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//div[contains(@class, 'filters__tab') and (contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'SCHEDULED') or contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'PROGRAMADOS'))]"
            ))
        )
        
        # Guarda referência de um elemento para detectar atualização do DOM
        try:
            ref = driver.find_element(By.CSS_SELECTOR, 'div.event__match--twoLine, div.event__match')
        except Exception:
            ref = None

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", scheduled_tab)
        driver.execute_script("arguments[0].click();", scheduled_tab)
        time.sleep(1.5)

        if ref is not None:
            try:
                WebDriverWait(driver, 6).until(EC.staleness_of(ref))
            except Exception:
                pass

        print("  ✓ Aba 'SCHEDULED' selecionada com sucesso (Apenas jogos que não começaram)")
        time.sleep(1.0)
    except Exception as e:
        print(f"  ℹ️  Aba SCHEDULED não encontrada ou já selecionada: {e}")


def expand_sections(driver):
    """
    Expande seções colapsadas (Display matches)
    Clica em todas as ligas que vêm recolhidas pelo Flashscore
    """
    try:
        time.sleep(1.5)
        
        # Múltiplos seletores para pegar 'display matches' em inglês, português ou por classe CSS moderna
        xpath_query = """
        //div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'display matches')]
        | //span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'display matches')]
        | //div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'mostrar jogos')]
        | //span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'mostrar jogos')]
        | //*[contains(@class, 'wcl-scores-simpleText') or contains(@class, 'wcl-simpleText')]
        """
        
        elements = driver.find_elements(By.XPATH, xpath_query)
        expanded = 0
        
        for elem in elements:
            try:
                txt = elem.text.strip().lower()
                if ('display matches' in txt or 'mostrar jogos' in txt) and elem.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", elem)
                    expanded += 1
                    time.sleep(0.3)
            except Exception:
                continue
        
        if expanded > 0:
            print(f"  ✓ Expandiu {expanded} ligas/seções que estavam recolhidas")
            time.sleep(2.0)  # Aguarda renderização dos jogos extras
        else:
            print("  ✓ Todas as ligas já estavam expandidas")
            
    except Exception as e:
        print(f"  ℹ️  Erro ao expandir seções: {e}")


def collect_match_ids(driver):
    """
    Coleta todos os IDs de jogos visíveis na página
    """
    cards = driver.find_elements(By.CSS_SELECTOR, 'div.event__match--twoLine, div.event__match')
    all_ids = []
    
    for card in cards:
        try:
            id_full = card.get_attribute('id')
            if id_full and id_full.startswith('g_1_'):
                match_id = id_full.split('_')[-1]
                all_ids.append(match_id)
        except Exception:
            continue
    
    print(f"✓ Total de jogos agendados no dia: {len(all_ids)}")
    return all_ids


def filter_matches_by_country(driver, match_ids):
    """
    Tenta filtrar jogos por país verificando a URL da liga de cada jogo
    Retorna lista filtrada ou vazia se falhar
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        filtered_ids = []
        
        for match_id in match_ids:
            try:
                # Busca o elemento do jogo
                match_elem = soup.find('div', id=f'g_1_{match_id}')
                if not match_elem:
                    continue
                
                # Busca o header da liga (anterior ao jogo)
                header = None
                for prev in match_elem.find_all_previous():
                    if prev.name == 'div' and 'event__header' in prev.get('class', []):
                        header = prev
                        break
                
                if not header:
                    continue
                
                # Pega o link da liga
                league_link = header.find('a', class_='eventHeaderLink')
                if league_link and 'href' in league_link.attrs:
                    href = league_link['href']
                    # href formato: /football/PAÍS/liga-nome/
                    if '/football/' in href:
                        country = href.split('/football/')[1].split('/')[0].lower()
                        
                        if country in ALLOWED_COUNTRIES:
                            filtered_ids.append(match_id)
            except Exception:
                continue
        
        return filtered_ids
    except Exception as e:
        print(f"  ⚠️ Erro ao filtrar: {e}")
        return []


def scrape_upcoming_match(scraper, match_id):
    """
    Extrai dados de um jogo futuro
    Usa o método scrape_match do scraper V2, mas SEM estatísticas
    
    Retorna dict com:
    - Match_ID (renomeado de Id)
    - Country, League, Round
    - Home, Away
    - Date, Time
    - Todas as odds (1X2 HT/FT, O/U HT/FT, BTTS, DC, CS)
    """
    try:
        print(f"    🔄 Processando {match_id}...", end=" ", flush=True)
        
        # Usa o método scrape_match que já faz tudo
        # Mas intercepta antes de extrair estatísticas
        
        # 1. Informações básicas + slugs
        data = scraper.get_match_basic_info(match_id)
        
        if not data or not data.get('Home_Slug') or not data.get('Away_Slug'):
            return None
        
        # Filtro de Liga: O país do jogo DEVE ser um dos países cadastrados em ligas_config.csv
        league_str = (data.get('League') or '').upper()
        country_of_match = league_str.split(' - ')[0].strip() if ' - ' in league_str else league_str
        
        is_allowed = False
        if not ALLOWED_COUNTRIES:
            is_allowed = True  # Se não houver config, aceita tudo
        else:
            # 1. O país do jogo TEM que ser um dos países cadastrados
            if country_of_match in ALLOWED_COUNTRIES:
                is_allowed = True
        
        if not is_allowed:
            print(f"    ⏭️ Ignorado (País/Liga fora do config: '{data.get('League', '?')}')")
            return None

        # Renomeia Id para Match_ID
        data['Match_ID'] = data.pop('Id', match_id)
        
        # 2. Odds 1X2 FT
        data = scraper.extract_odds_1x2_ft(match_id, data)
        if not data.get('Odds_1X2_FT'):
            print(f"    ✗ Erro no jogo {match_id}: Sem odds 1X2 FT")
            return None
        
        # 3. Odds 1X2 HT
        data = scraper.extract_odds_1x2_ht(match_id, data)
        
        # 4. Odds Over/Under FT
        data = scraper.extract_odds_ou_ft(match_id, data)
        
        # 5. Odds Over/Under HT
        data = scraper.extract_odds_ou_ht(match_id, data)
        
        # 6. Odds BTTS FT
        data = scraper.extract_odds_btts_ft(match_id, data)
        
        # 7. Odds Double Chance FT
        data = scraper.extract_odds_dc_ft(match_id, data)
        
        # 8. Odds Correct Score FT - REMOVIDO para acelerar
        # data = scraper.extract_odds_cs_ft(match_id, data)
        
        # NÃO extrai estatísticas (jogo não aconteceu ainda)
        # Comentado: extract_statistics_ft, extract_statistics_ht, extract_statistics_2t
        
        return data
        
    except Exception as e:
        print(f"    ✗ Erro no jogo {match_id}: {str(e)[:50]}")
        return None


def process_day(scraper, days_ahead: int, output_dir='./jogos_futuros'):
    """
    Processa um dia específico (hoje, amanhã, depois)
    
    Args:
        scraper: FlashScoreScraper instance
        days_ahead: 0=hoje, 1=amanhã, 2=depois de amanhã
        output_dir: Diretório para salvar JSONs
    """
    # Calcula data
    target_date = datetime.today() + timedelta(days=days_ahead)
    date_str = target_date.strftime('%Y-%m-%d')
    day_name = ['Hoje', 'Amanhã', 'Depois de Amanhã'][days_ahead] if days_ahead < 3 else f'+{days_ahead} dias'
    
    print(f"\n{'='*80}")
    print(f"📅 {day_name.upper()} - {date_str}")
    print(f"{'='*80}")
    
    # Prepara arquivo de saída
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f'jogos_flashscore_{date_str}.json')
    
    # Carrega jogos já processados (se existir)
    existing_matches = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                existing_matches = {m['Match_ID']: m for m in data.get('matches', [])}
            print(f"📄 Arquivo existente: {len(existing_matches)} jogos já processados")
        except Exception as e:
            print(f"⚠️ Erro ao carregar arquivo existente: {e}")
    
    # Navega para página principal do futebol
    football_url = 'https://www.flashscore.com/football/'
    print(f"🔍 Acessando: {football_url}")
    scraper.driver.get(football_url)
    
    # Aceita cookies
    accept_cookies_if_present(scraper.driver)
    
    # Espera página carregar
    try:
        WebDriverWait(scraper.driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div#live-table'))
        )
    except Exception as e:
        print(f"❌ Erro ao carregar página: {e}")
        return
    
    # Navega para o dia desejado
    if days_ahead > 0:
        print(f"⏭️  Navegando para {day_name.lower()}...")
        go_to_future_day(scraper.driver, days_ahead)
    
    # Clica na aba SCHEDULED (Programados) para filtrar jogos que não começaram
    select_scheduled_tab(scraper.driver)
    
    # Expande seções colapsadas
    print("🔽 Expandindo seções...")
    expand_sections(scraper.driver)
    
    # Coleta IDs de todos os jogos
    print("📋 Coletando IDs dos jogos...")
    match_ids = collect_match_ids(scraper.driver)
    
    # Filtra IDs novos (não processados)
    new_match_ids = [mid for mid in match_ids if mid not in existing_matches]
    
    print(f"✓ Total de jogos encontrados: {len(match_ids)}")
    print(f"✓ Jogos já processados: {len(existing_matches)}")
    print(f"🔄 Jogos novos para processar: {len(new_match_ids)}")
    
    if len(new_match_ids) == 0:
        print("✅ Todos os jogos já foram processados!")
        return
    
    # Processa cada jogo novo
    print(f"\n🎯 Processando {len(new_match_ids)} jogos novos...")
    matches = list(existing_matches.values())  # Mantém os já processados
    
    for i, match_id in enumerate(tqdm(new_match_ids, desc=f"Jogos {date_str}")):
        try:
            match_data = scrape_upcoming_match(scraper, match_id)
            
            if match_data:
                matches.append(match_data)
                
                # Salva incrementalmente JOGO A JOGO
                output_data = {
                    'date': date_str,
                    'scrape_timestamp': datetime.now().isoformat(),
                    'total_matches': len(matches),
                    'matches': matches
                }
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)
                
                print(f"  [{i+1}/{len(new_match_ids)}] {match_data.get('Home', '?')} vs {match_data.get('Away', '?')} ✓💾")
            
            time.sleep(0.5)  # Pausa entre requisições
            
        except Exception as e:
            print(f"\n    ✗ Erro geral no jogo {match_id}: {e}")
            continue
    
    # Salva resultado final
    output_data = {
        'date': date_str,
        'scrape_timestamp': datetime.now().isoformat(),
        'total_matches': len(matches),
        'matches': matches
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ {day_name} completo: {len(matches)} jogos salvos em {output_file}")
    print(f"   📊 Novos: {len(new_match_ids)} | Existentes: {len(existing_matches)}")
    
    # Commit automático após completar o dia
    git_commit(f"Scraping jogos futuros: {day_name} ({date_str}) - {len(matches)} jogos", output_file)


def main():
    """
    Função principal - Coleta jogos futuros (Hoje e Amanhã)
    """
    import argparse
    parser = argparse.ArgumentParser(description="FlashScore Scraper de Jogos Futuros")
    parser.add_argument("--days", nargs="+", type=int, default=[0, 1],
                        help="Dias à frente para baixar (0=Hoje, 1=Amanhã, 2=Depois). Ex: --days 0 1")
    args = parser.parse_args()

    print("="*80)
    print("⚽ SCRAPER DE JOGOS FUTUROS - FLASHSCORE")
    print("="*80)
    print(f"Início: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📅 Dias selecionados: {args.days} (0=Hoje, 1=Amanhã)")
    
    # Inicializa scraper (headless para performance)
    scraper = FlashScoreScraper(headless=True)
    
    try:
        for days in args.days:
            process_day(scraper, days_ahead=days)
            
    finally:
        scraper.close()
        print(f"\n✅ Scraping de jogos futuros concluído!")
        print(f"Fim: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
