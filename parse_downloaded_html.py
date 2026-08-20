from bs4 import BeautifulSoup

def count_matches_in_html(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Busca por div[id^='g_1_']
    g1_elements = soup.select("div[id^='g_1_']")
    g1_ids = [el.get('id').replace('g_1_', '') for el in g1_elements if el.get('id')]
    
    # 2. Busca por div.event__match
    event_matches = soup.select("div.event__match")
    
    # 3. Listagem dos confrontos
    matches_list = []
    for el in g1_elements:
        home_el = el.select_one("div.event__participant--home") or el.select_one("div.event__participant")
        away_el = el.select_one("div.event__participant--away")
        score_home = el.select_one("div.event__score--home")
        score_away = el.select_one("div.event__score--away")
        
        home = home_el.text.strip() if home_el else "?"
        away = away_el.text.strip() if away_el else "?"
        sh = score_home.text.strip() if score_home else "?"
        sa = score_away.text.strip() if score_away else "?"
        
        matches_list.append((el.get('id'), home, away, f"{sh}-{sa}"))
        
    print("=" * 70)
    print(f"ARQUIVO: {file_path}")
    print("=" * 70)
    print(f"Total de div[id^='g_1_']: {len(g1_elements)}")
    print(f"Total de div.event__match: {len(event_matches)}")
    print(f"Total de IDs unicos: {len(set(g1_ids))}")
    print("=" * 70)
    print("Primeiros 5 jogos do arquivo:")
    for m in matches_list[:5]:
        print(f"  {m[0]} | {m[1]} vs {m[2]} ({m[3]})")
    print("...")
    print("Ultimos 5 jogos do arquivo:")
    for m in matches_list[-5:]:
        print(f"  {m[0]} | {m[1]} vs {m[2]} ({m[3]})")
    print("=" * 70)

if __name__ == "__main__":
    count_matches_in_html(r"C:\proj\apostas\futpython-flashscore\TESTE-CANADA\lista2025.html")
