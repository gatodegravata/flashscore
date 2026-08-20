from bs4 import BeautifulSoup

with open(r"C:\proj\apostas\futpython-flashscore\TESTE-CANADA\lista2025.html", "r", encoding="utf-8", errors="ignore") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

stages = soup.select("div.event__header, div.event__title, div.wcl-leagueHeader_8L1A0")
print("Headers de fases encontrados:")
for st in stages:
    print(" ->", st.text.strip())

# Vamos agrupar as seções
all_divs = soup.select("div[id^='g_1_'], div.event__header, div.event__title")
current_stage = "Principal"
counts = {}

for d in all_divs:
    if not d.get("id") or not d.get("id").startswith("g_1_"):
        current_stage = d.text.strip()
        if current_stage not in counts:
            counts[current_stage] = 0
    else:
        counts[current_stage] = counts.get(current_stage, 0) + 1

print("\nDivisão exata dos 117 jogos no HTML que você baixou:")
for stage, count in counts.items():
    print(f" • {stage}: {count} jogos")
