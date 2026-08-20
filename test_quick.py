#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Teste Rápido - FlashScore Scraper
Testa a inicialização do WebDriver e extração de 1 partida de teste.
"""
import sys
import os
import io
import json

# Garante suporte a UTF-8 no Windows Console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flashscore_scraper import FlashScoreScraper

def test_quick():
    print("=" * 60)
    print("🧪 INICIANDO TESTE DO FLASHSCORE SCRAPER (MODO VISUAL)")
    print("=" * 60)
    
    # headless=False para você ver o Chrome abrindo na tela
    scraper = FlashScoreScraper(headless=False)
    try:
        # Testando extração dos IDs de uma liga (Premier League 2023-2024)
        league_url = 'https://www.flashscore.com/football/england/premier-league-2023-2024/results/'
        print(f"\n1. Acessando página da liga: {league_url}")
        scraper.driver.get(league_url)
        scraper.accept_cookies()
        
        import time
        from bs4 import BeautifulSoup
        time.sleep(4)
        
        soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')
        match_divs = soup.select("div.event__match")
        match_ids = []
        for div in match_divs:
            m_id = div.get('id')
            if m_id and m_id.startswith('g_1_'):
                match_ids.append(m_id.replace('g_1_', ''))
                
        print(f"✓ Total de jogos identificados na primeira página: {len(match_ids)}")
        
        if not match_ids:
            print("⚠ Nenhum match ID encontrado na página principal.")
            return
            
        test_id = match_ids[0]
        print(f"\n2. Testando extração completa de 1 partida (ID: {test_id})...")
        match_data = scraper.scrape_match(test_id)
        
        if match_data:
            print("\n" + "=" * 60)
            print("🎉 SUCESSO! Dados extraídos:")
            print("=" * 60)
            print(f"• Jogo: {match_data.get('Home')} vs {match_data.get('Away')}")
            print(f"• Data/Hora: {match_data.get('Date')} {match_data.get('Time')}")
            print(f"• Placar: {match_data.get('Home_Score')} x {match_data.get('Away_Score')}")
            print(f"• Rodada: {match_data.get('Round')}")
            print(f"• Best Odd 1: {match_data.get('Best_Odd_1_FT')} | X: {match_data.get('Best_Odd_X_FT')} | 2: {match_data.get('Best_Odd_2_FT')}")
            
            # Salva resultado do teste
            os.makedirs("data_teste", exist_ok=True)
            with open("data_teste/sample_match.json", "w", encoding="utf-8") as f:
                json.dump(match_data, f, ensure_ascii=False, indent=2)
            print("• Arquivo salvo com sucesso em: data_teste/sample_match.json")
        else:
            print("❌ Falha ao extrair dados da partida.")
            
    except Exception as e:
        print(f"❌ Erro durante o teste: {e}")
        import traceback
        traceback.print_exc()
    finally:
        scraper.close()
        print("\n✓ WebDriver finalizado com sucesso.")

if __name__ == "__main__":
    test_quick()
