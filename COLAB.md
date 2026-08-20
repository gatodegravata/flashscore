# FlashScore Scraper - Guia de Execução no Google Colab

Este notebook/guia permite rodar o scraper na nuvem do Google Colab sem gastar recursos da sua máquina.

---

### 1. Clonar o Repositório e Instalar Dependências

Abra um novo notebook no [Google Colab](https://colab.research.google.com/) e execute a seguinte célula:

```python
%%capture
# 1. Instalar Google Chrome Oficial no Colab (Silencioso)
!wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
!echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list > /dev/null
!apt-get update -qq
!apt-get install -y -qq google-chrome-stable > /dev/null

# 2. Clonar o repositório
!git clone -q https://github.com/gatodegravata/flashscore.git
%cd flashscore

# 3. Instalar bibliotecas Python (Silencioso)
!pip install -q -r requirements.txt
```

---

### 2. (Opcional) Conectar ao Google Drive para Salvar os Dados Permanentemente

Como as sessões do Colab são temporárias, conecte seu Google Drive para que os JSONs fiquem salvos na sua conta:

```python
from google.colab import drive
import os
import shutil

# Monta o Drive
drive.mount('/content/drive')

# Cria pasta no seu Google Drive (se não existir)
drive_folder = '/content/drive/MyDrive/Flashscore_Data/'
os.makedirs(drive_folder, exist_ok=True)
print(f"Pasta do Drive pronta: {drive_folder}")
```

---

### 3. Configurar para Teste Rápido (Apenas Canadá 2026)

Execute esta célula no Colab para configurar o teste com apenas 1 liga:

```python
conteudo_teste = """baixar;pais;liga_temporada;temporada;url
S;CANADA;CANADA 1;2026;https://www.flashscore.com/football/canada/canadian-premier-league/results/
"""

with open('ligas_config.csv', 'w', encoding='utf-8') as f:
    f.write(conteudo_teste)

print("✓ ligas_config.csv configurado com sucesso para testar apenas o Canadá 2026!")
```

---

### 4. Executar o Scraping

#### 🚀 Opção A: Versão 2.0 Ultra-Rápida via API (`curl_cffi` - Recomendada)
```python
# Roda com 10 ou 15 workers simultâneos sem proxy
!python scrape_jogos_passados_fast.py --workers 10
```

#### 🛡️ Opção B: Versão 1.0 Clássica (Selenium Multi-Workers)
```python
# Modo Paralelo Selenium (ex: 3 a 5 workers)
!python scrape_jogos_passados.py --workers 5
```

---

### 5. Baixar os Resultados para o seu Computador (Automático)

Execute esta célula para disparar o download imediato do `.zip` completo (com todos os JSONs e CSVs gerados):

```python
from google.colab import files
import os

# Baixa o pacote completo compactado
if os.path.exists('flashscore_dados_completos.zip'):
    files.download('flashscore_dados_completos.zip')
elif os.path.exists('data_jogos_passados'):
    # Compacta e baixa caso queira baixar avulso
    !zip -r flashscore_dados.zip data_jogos_passados jogos_passados
    files.download('flashscore_dados.zip')
```

---

### 6. (Opcional) Copiar os Resultados para o Google Drive

```python
# Copia os arquivos gerados para a pasta do seu Google Drive
!cp -r jogos_passados/* /content/drive/MyDrive/Flashscore_Data/ 2>/dev/null || true
!cp -r data_jogos_passados/* /content/drive/MyDrive/Flashscore_Data/ 2>/dev/null || true
print("✓ Dados copiados com sucesso para o seu Google Drive!")
```
