import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

def inspect_canada():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=options)
    url = "https://www.flashscore.com/football/canada/canadian-premier-league-2025/results/"
    print(f"Acessando {url}...")
    driver.get(url)
    time.sleep(3)
    
    # Fecha modais
    try:
        driver.find_element("css selector", "button#onetrust-accept-btn-handler").click()
    except:
        pass
    try:
        driver.find_element("xpath", "//button[contains(., '18')]").click()
    except:
        pass
        
    # Clica ate o fim
    for i in range(10):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        btn = driver.find_elements("xpath", "//a[contains(., 'Show more')] | //button[contains(., 'Show more')] | //span[contains(., 'Show more')]")
        if btn:
            try:
                driver.execute_script("arguments[0].click();", btn[0])
                print(f"Clicou {i+1}")
                time.sleep(2)
            except:
                break
        else:
            break
            
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    # Coleta todos os IDs e tags de jogos
    all_g1 = soup.select("div[id^='g_1_']")
    all_events = soup.select("div.event__match")
    
    print("=" * 60)
    print(f"Total de div[id^='g_1_']: {len(all_g1)}")
    print(f"Total de div.event__match: {len(all_events)}")
    
    # Imprime primeiros e ultimos jogos
    print("\n--- Primeiros 3 jogos ---")
    for d in all_g1[:3]:
        home = d.select_one("div.event__participant--home")
        away = d.select_one("div.event__participant--away")
        print(f"ID: {d.get('id')} | {home.text if home else '?'} vs {away.text if away else '?'}")
        
    print("\n--- Ultimos 3 jogos ---")
    for d in all_g1[-3:]:
        home = d.select_one("div.event__participant--home")
        away = d.select_one("div.event__participant--away")
        print(f"ID: {d.get('id')} | {home.text if home else '?'} vs {away.text if away else '?'}")
    print("=" * 60)
    
    driver.quit()

if __name__ == "__main__":
    inspect_canada()
