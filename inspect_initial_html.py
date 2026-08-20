from bs4 import BeautifulSoup
import os

html_path = r"C:\proj\apostas\futpython-flashscore\teste-canada\lista.html"

if not os.path.exists(html_path):
    print(f"Arquivo nao encontrado em: {html_path}")
    exit(1)

with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

g1_matches = soup.select("div[id^='g_1_']")
print("=" * 70)
print(f"ANÁLISE DE: {html_path}")
print("=" * 70)
print(f"Total de partidas na carga inicial (sem clicar em nada): {len(g1_matches)}")
print("=" * 70)

# Procurando elementos de botões e links de rodapé
buttons = soup.select("button, a, span")
show_more_candidates = []
for b in buttons:
    txt = b.text.strip()
    if any(w in txt.lower() for w in ['show more', 'mostrar mais', 'mais jogos', 'more matches']):
        show_more_candidates.append((b.name, b.attrs, txt))

print(f"\nBotões / Links de 'Show More' encontrados no HTML:")
for tag, attrs, txt in show_more_candidates:
    print(f" Tag: <{tag}> | Texto: '{txt}' | Atributos: {attrs}")
print("=" * 70)

# Procurando rodadas/meses
rounds = soup.select("div.event__round, div.event__header, span.event__title--name")
print(f"\nRodadas/Headers visíveis:")
for r in rounds[:10]:
    print(" ->", r.text.strip())
print("=" * 70)
