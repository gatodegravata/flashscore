"""
Script de Teste Visual do Botão 'Show More Matches'
Abre a janela real do Chrome para você assistir na sua tela o robô encontrando
e clicando no botão até expandir 100% dos jogos da liga.
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

def test_visual_expansion(league_url):
    print("=" * 80)
    print("TESTE VISUAL: EXPANSAO DE JOGOS NO FLASHSCORE")
    print("=" * 80)
    
    options = Options()
    # MODO VISÍVEL (Janela real na sua tela)
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    print("🚀 Abrindo o Google Chrome na sua tela...")
    driver = webdriver.Chrome(options=options)
    
    try:
        print(f"\n🌐 Acessando a página de resultados da liga:")
        print(f"👉 {league_url}")
        driver.get(league_url)
        time.sleep(3)
        
        # 1. Tenta aceitar cookies e fechar modal de idade (+18)
        try:
            # Banner de Cookies
            cookie_btn = driver.find_element("css selector", "button#onetrust-accept-btn-handler")
            if cookie_btn.is_displayed():
                print("🍪 Aceitando banner de cookies...")
                cookie_btn.click()
                time.sleep(1)
        except Exception:
            pass
            
        try:
            # Modal "Help us verify your age" ("I'M 18 AND OLDER")
            age_btns = driver.find_elements("xpath", "//button[contains(., '18 AND OLDER') or contains(., '18 e mais') or contains(., '18')]")
            for abtn in age_btns:
                if abtn.is_displayed():
                    print("🔞 Fechando modal de verificação de idade (I'M 18 AND OLDER)...")
                    driver.execute_script("arguments[0].click();", abtn)
                    time.sleep(1)
                    break
        except Exception:
            pass

        # 2. Loop de cliques visíveis
        print("\n⏬ Procurando o botão 'Show more matches' / 'Mostrar mais jogos'...")
        clicks = 0
        consecutive_fails = 0
        
        while clicks < 100 and consecutive_fails < 4:
            clicked_this_round = False
            
            # Rola até o final da página para forçar a renderização do rodapé/botão
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.2)
            
            # Busca direta via XPath (funciona com <a>, <button>, <span>, etc.)
            xpath_expr = "//a[contains(., 'Show more') or contains(., 'Mostrar mais') or contains(., 'Mais jogos')] | //button[contains(., 'Show more') or contains(., 'Mostrar mais') or contains(., 'Mais jogos')] | //span[contains(., 'Show more') or contains(., 'Mostrar mais') or contains(., 'Mais jogos')]"
            
            try:
                elements = driver.find_elements("xpath", xpath_expr)
                for elem in elements:
                    try:
                        if elem.is_displayed():
                            # Rola a tela até o botão para você VER no centro
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", elem)
                            time.sleep(0.8)
                            
                            # Destaca o botão em amarelo e vermelho
                            driver.execute_script("arguments[0].style.border='4px solid red'; arguments[0].style.backgroundColor='yellow';", elem)
                            time.sleep(0.5)
                            
                            # Clica via JS
                            driver.execute_script("arguments[0].click();", elem)
                            
                            clicks += 1
                            print(f"  👉 [CLIQUE #{clicks}] Botão encontrado e clicado com sucesso! (Texto: '{elem.text.strip()}')")
                            
                            # Aguarda os novos jogos carregarem na tela
                            time.sleep(2.5)
                            consecutive_fails = 0
                            clicked_this_round = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass
            
            if not clicked_this_round:
                consecutive_fails += 1
                time.sleep(1)
        
        # 3. Contagem final dos jogos expandidos
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        match_divs = soup.select("div.event__match")
        
        valid_match_ids = []
        for div in match_divs:
            mid = div.get('id')
            if mid and mid.startswith('g_1_'):
                valid_match_ids.append(mid.replace('g_1_', ''))
        
        print("\n" + "=" * 80)
        print("📊 RESULTADO DA EXPANSÃO:")
        print(f"  • Total de cliques realizados: {clicks}")
        print(f"  • Total de divs event__match na página: {len(match_divs)}")
        print(f"  • Total de IDs válidos de jogos (g_1_...): {len(valid_match_ids)}")
        print("=" * 80)
        
        input("\n⌨️ Pressione ENTER aqui no terminal para fechar o navegador quando terminar de olhar...")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    # Teste com a Canadian Premier League 2025
    TEST_URL = "https://www.flashscore.com/football/canada/canadian-premier-league-2025/results/"
    test_visual_expansion(TEST_URL)
