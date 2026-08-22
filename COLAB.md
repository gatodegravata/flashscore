# COLAB.md — Guia de Execução no Google Colab

Cole as células abaixo em sequência no seu notebook Google Colab.
O `.env` **não está no repositório** por segurança — você vai criá-lo direto na célula 3,
e ele só existe durante a sessão (some quando o runtime reiniciar).

---

## Célula 1 — Clonar o repositório

```python
# ── CÉLULA 1: Clone do repositório ───────────────────────────────────────────
import os

REPO_URL = "https://github.com/gatodegravata/flashscore.git"  # ajuste se necessário
REPO_DIR = "/content/flashscore"

if not os.path.exists(REPO_DIR):
    !git clone {REPO_URL} {REPO_DIR}
else:
    # Se já existe, garante que está atualizado
    !git -C {REPO_DIR} pull --rebase

%cd {REPO_DIR}
print("Diretório atual:", os.getcwd())
```

---

## Célula 2 — Instalar dependências

```python
# ── CÉLULA 2: Instalação de dependências ─────────────────────────────────────
!pip install -q -r requirements.txt

# curl_cffi precisa de versão recente com suporte a AsyncSession
!pip install -q "curl_cffi>=0.7.0"

print("Dependências instaladas!")
```

---

## Célula 3 — Criar o arquivo `.env` com os proxies (SOMENTE NESTA SESSÃO)

> ⚠️ **Nunca faça commit deste conteúdo.** O `.env` criado aqui existe apenas
> na memória volátil do Colab e será apagado ao reiniciar o runtime.

```python
# ── CÉLULA 3: Criar .env com credenciais de proxy ────────────────────────────
# Cole aqui as suas credenciais. Elas NÃO serão gravadas no GitHub.

env_content = """API_KEY_WEBSHARE=COLE_SUA_API_KEY_AQUI
WEBSHARE_PROXY_1=http://usuario:senha@ip1:porta
WEBSHARE_PROXY_2=http://usuario:senha@ip2:porta
WEBSHARE_PROXY_3=http://usuario:senha@ip3:porta
WEBSHARE_PROXY_4=http://usuario:senha@ip4:porta
WEBSHARE_PROXY_5=http://usuario:senha@ip5:porta
WEBSHARE_PROXY_6=http://usuario:senha@ip6:porta
WEBSHARE_PROXY_7=http://usuario:senha@ip7:porta
WEBSHARE_PROXY_8=http://usuario:senha@ip8:porta
WEBSHARE_PROXY_9=http://usuario:senha@ip9:porta
WEBSHARE_PROXY_10=http://usuario:senha@ip10:porta
"""

with open(".env", "w") as f:
    f.write(env_content)

print(".env criado com sucesso (apenas nesta sessão).")
```

---

## Célula 4 — Verificar qual fatia este notebook vai processar

Antes de rodar, defina qual das 4 sessões paralelas este notebook é:

```python
# ── CÉLULA 4: Configurar este notebook ───────────────────────────────────────

# Altere conforme o notebook (1, 2, 3 ou 4):
ESTE_NOTEBOOK = 1       # <- EDITE AQUI (1, 2, 3 ou 4)
TOTAL_NOTEBOOKS = 4     # <- Total de Colabs rodando em paralelo

SLICE = f"{ESTE_NOTEBOOK}/{TOTAL_NOTEBOOKS}"

# Proxies que este notebook usará (distribua entre os notebooks):
# Notebook 1: proxies 1,2   |  Notebook 2: proxies 3,4
# Notebook 3: proxies 5,6   |  Notebook 4: proxies 7,8,9,10
PROXIES_POR_NOTEBOOK = {
    1: "1,2",
    2: "3,4",
    3: "5,6",
    4: "7,8,9,10",
}
PROXIES = PROXIES_POR_NOTEBOOK[ESTE_NOTEBOOK]

print(f"Este notebook processará a fatia: {SLICE}")
print(f"Proxies que serão usados: {PROXIES}")
print(f"IP direto do Colab sempre será o slot 0 (prioritário).")
```

---

## Célula 5 — Executar o scraper

```python
# ── CÉLULA 5: Rodar o scraper ─────────────────────────────────────────────────
# --direct-workers = quantos workers ficam EXCLUSIVAMENTE no IP do Colab
# O restante dos workers é dividido entre os proxies selecionados.
# Exemplo: --workers 12 --direct-workers 8
#   → 8 workers no IP direto  (maioria do tráfego)
#   → 4 workers nos proxies   (complemento)

!python ultra_updater_massivo.py \
    --slice {SLICE} \
    --proxies {PROXIES} \
    --workers 12 \
    --direct-workers 8 \
    --save-every 5000 \
    --delay-odds 0.05
```

---

## Célula 6 — Verificar progresso e arquivos gerados

```python
# ── CÉLULA 6: Verificar artefatos gerados ────────────────────────────────────
import os, glob

SLICE_SLUG = SLICE.replace("/", "_")
OUTPUT_DIR = "dataset_completo"

# Checkpoint de IDs
cp_file = f"{OUTPUT_DIR}/checkpoints/processed_ids_{SLICE_SLUG}.txt"
if os.path.exists(cp_file):
    with open(cp_file) as f:
        ids = [l.strip() for l in f if l.strip()]
    print(f"IDs processados neste slice: {len(ids):,}")
else:
    print("Nenhum checkpoint encontrado ainda.")

# Parquets parciais
parts = sorted(glob.glob(f"{OUTPUT_DIR}/checkpoints/part_{SLICE_SLUG}_*.parquet"))
print(f"\nParquets parciais salvos: {len(parts)}")
for p in parts:
    size_mb = os.path.getsize(p) / 1_048_576
    print(f"  {os.path.basename(p)} — {size_mb:.1f} MB")

# ZIPs de JSON bruto
zips = sorted(glob.glob(f"{OUTPUT_DIR}/zips_json_bruto/lote_{SLICE_SLUG}_*.zip"))
print(f"\nZIPs de JSON bruto: {len(zips)}")
for z in zips:
    size_mb = os.path.getsize(z) / 1_048_576
    print(f"  {os.path.basename(z)} — {size_mb:.1f} MB")
```

---

## Célula 7 — (Opcional) Baixar os artefatos para o Google Drive

```python
# ── CÉLULA 7: Montar Drive e copiar artefatos ─────────────────────────────────
from google.colab import drive
import shutil, os

drive.mount("/content/drive")

DRIVE_DEST = f"/content/drive/MyDrive/flashscore_scraping/slice_{SLICE_SLUG}"
os.makedirs(DRIVE_DEST, exist_ok=True)

shutil.copytree(
    f"dataset_completo/checkpoints",
    f"{DRIVE_DEST}/checkpoints",
    dirs_exist_ok=True,
)
shutil.copytree(
    f"dataset_completo/zips_json_bruto",
    f"{DRIVE_DEST}/zips_json_bruto",
    dirs_exist_ok=True,
)

print(f"Artefatos copiados para: {DRIVE_DEST}")
```

---

## Resumo dos Parâmetros do Script

| Parâmetro | Default | Descrição |
|---|---|---|
| `--slice` | `None` | Fatia deste Colab (ex: `1/4`) |
| `--proxies` | `None` | Índices de proxy do `.env` (ex: `1,3`) |
| `--workers` | `8` | Total de coroutines assíncronas simultâneas |
| `--direct-workers` | `0` | Quantos workers ficam FIXOS no IP direto (0 = uniforme) |
| `--batch-size` | `10000` | Tamanho do lote para o ZIP bruto |
| `--save-every` | `10000` | Intervalo de save do parquet parcial |
| `--delay-sumario` | `0.0` | Delay (s) após cada request `df_sui` |
| `--delay-stats` | `0.0` | Delay (s) após cada request `df_st` |
| `--delay-odds` | `0.0` | Delay (s) após cada request GraphQL |

> **Dica:** Se você estiver recebendo muitos 429 no GraphQL, comece com `--delay-odds 0.1`.
> Se continuar, suba para `0.2` ou reduza `--workers`.

---

## Distribuição de Proxies entre 4 Notebooks

```
Notebook 1  →  --slice 1/4  --proxies 1,2
Notebook 2  →  --slice 2/4  --proxies 3,4
Notebook 3  →  --slice 3/4  --proxies 5,6
Notebook 4  →  --slice 4/4  --proxies 7,8,9,10
```

O **IP direto do Colab** é sempre o slot 0 e tem prioridade — os proxies
pagos são usados como complemento para distribuir a carga.
