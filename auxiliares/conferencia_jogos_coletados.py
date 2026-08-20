# @title 📊 Tabela Dinâmica de Conferência de Jogos Flashscore
import os
import sys
import csv
import re
import json
import pandas as pd
from google.colab import data_table
from IPython.display import display

# Ativa o formatador interativo do Google Colab
data_table.enable_dataframe_formatter()

CONFIG_FILE = "ligas_config.csv"
CSV_DIR = "dataframes_jogos_passados"
META_JSON = "auxiliares/temporadas_ligas.json"

# 1. Carrega metadados oficiais
url_map = {}
if os.path.exists(META_JSON):
    with open(META_JSON, 'r', encoding='utf-8') as f:
        data_meta = json.load(f)
    for l in data_meta.get('leagues', []):
        l_name = l.get('league_name')
        c_name = l.get('country_name')
        root_u = l.get('url', '').rstrip('/')
        if root_u:
            url_map[root_u] = {'name': l_name, 'country': c_name}
            url_map[root_u + '/results'] = {'name': l_name, 'country': c_name}
        for s in l.get('seasons', []):
            s_u = s.get('url', '').rstrip('/')
            if s_u:
                url_map[s_u] = {'name': l_name, 'country': c_name}
                url_map[s_u + '/results'] = {'name': l_name, 'country': c_name}
            if '/football/' in s_u:
                slug = s_u.split('/football/')[1].strip('/')
                url_map[slug] = {'name': l_name, 'country': c_name}
                url_map[slug + '/results'] = {'name': l_name, 'country': c_name}

def obter_nome_liga(url, liga_alias):
    u_norm = url.rstrip('/')
    info = url_map.get(u_norm) or url_map.get(u_norm + '/results')
    if not info and '/football/' in u_norm:
        slug = u_norm.split('/football/')[1].strip('/')
        info = url_map.get(slug)
    if info and info.get('name'):
        return info['name']
    if '/football/' in u_norm:
        parts = u_norm.split('/football/')[1].split('/')
        if len(parts) > 1 and parts[1]:
            slug_c = re.sub(r'[-_]20\d{2}(?:[-_]20\d{2})?', '', parts[1]).strip('-_')
            name = slug_c.replace('-', ' ').title()
            for k, v in [('Npl', 'NPL'), ('Nsw', 'NSW'), ('Act', 'ACT'), ('Rfef', 'RFEF')]:
                name = re.sub(rf'\b{k}\b', v, name, flags=re.IGNORECASE)
            return name
    return liga_alias

def padronizar_temp(t):
    m = re.match(r'^(20\d\d)[-_/](20\d\d)$', str(t).strip())
    return f"{m.group(1)}/{m.group(2)}" if m else str(t).strip()

# 2. Varre ligas_config.csv e checa os CSVs
registros = []
ligas_temps = {}

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    for row in csv.reader(f, delimiter=';'):
        if not row or len(row) < 5 or row[0].startswith('#') or row[0].strip().upper() != 'S':
            continue
        _, pais, liga_alias, temp, url = [x.strip() for x in row[:5]]
        
        temp_p = padronizar_temp(temp)
        nome_real = obter_nome_liga(url, liga_alias)
        
        c_clean = re.sub(r'[/\\:*?"<>| ]+', '-', pais.lower()).strip('-')
        l_clean = re.sub(r'[/\\:*?"<>| ]+', '-', liga_alias.lower()).strip('-')
        s_clean = re.sub(r'[/\\:*?"<>| ]+', '-', str(temp).lower()).strip('-')
        csv_file = f"{c_clean}_{l_clean}_{s_clean}.csv"
        csv_p = os.path.join(CSV_DIR, csv_file)
        
        total_j = 0
        if os.path.exists(csv_p):
            try:
                df_c = pd.read_csv(csv_p, low_memory=False)
                if 'Sub_League' in df_c.columns:
                    df_sub = df_c[df_c['Sub_League'].astype(str).str.lower() == nome_real.lower()]
                    total_j = len(df_sub) if len(df_sub) > 0 else len(df_c)
                else:
                    total_j = len(df_c)
            except Exception:
                total_j = 0
                
        url_c = re.sub(r'[-_]20\d{2}(?:[-_]20\d{2})?', '', url.rstrip('/')).replace('/results', '') + '/'
        chave = (pais.upper(), nome_real, url_c)
        ligas_temps.setdefault(chave, set()).add(temp_p)
        
        registros.append({
            'Country': pais.upper(),
            'Sub_League': nome_real,
            'Season': temp_p,
            'Matches': total_j,
            'League_URL': url_c
        })

# 3. Monta a Matriz Dinâmica
df_base = pd.DataFrame(registros)
pivot = df_base.pivot_table(index=['Country', 'Sub_League', 'League_URL'], columns='Season', values='Matches', aggfunc='sum', fill_value=0)

# Ordena colunas
pivot = pivot[sorted(list(pivot.columns), key=lambda s: int(re.search(r'\d{4}', str(s)).group(0)) if re.search(r'\d{4}', str(s)) else 0)]
pivot['TOTAL_JOGOS'] = pivot.sum(axis=1)

# Status por liga
status_l = []
for idx in pivot.index:
    c, l_n, u_n = idx
    temps_esp = ligas_temps.get((c, l_n, u_n), set())
    tot_esp = len(temps_esp)
    col = sum(1 for t in temps_esp if t in pivot.columns and pivot.loc[idx, t] > 0)
    if col == tot_esp and tot_esp > 0:
        status_l.append(f"✅ Completo ({col}/{tot_esp})")
    elif col > 0:
        status_l.append(f"⚠️ Parcial ({col}/{tot_esp})")
    else:
        status_l.append(f"❌ Pendente (0/{tot_esp})")

pivot['STATUS'] = status_l
df_resultado = pivot.reset_index()
df_resultado.columns.name = None

# Exibe a tabela interativa do Google Colab
display(data_table.DataTable(df_resultado, include_index=False, num_rows_per_page=25))
