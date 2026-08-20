# 🖥️ Guia de Instalação e Execução na VPS (Linux Ubuntu 24/7)

Este guia contém todos os comandos necessários para rodar o **FlashScore Scraper** de forma contínua em segundo plano na sua VPS Linux, com suporte a proxies Webshare e proteção do IP do servidor.

---

## 1. Instalar Dependências do Sistema

Conecte-se na sua VPS via SSH e execute:

```bash
sudo apt update -y
sudo apt install -y chromium-browser chromium-chromedriver python3-venv python3-pip git
```

---

## 2. Clonar o Repositório

```bash
git clone https://github.com/gatodegravata/flashscore.git
cd flashscore
```

---

## 3. Configurar o Ambiente Virtual Python

```bash
# Cria o ambiente virtual
python3 -m venv .venv

# Ativa o ambiente virtual
source .venv/bin/activate

# Instala as bibliotecas necessárias
pip install -r requirements.txt
# Ou manualmente se preferir:
pip install selenium beautifulsoup4 pandas tqdm requests webdriver-manager tinydb
```

---

## 4. Configurar as Ligas para Download

Edite o arquivo de configuração de ligas:

```bash
nano ligas_config.csv
```

- Marque com **`S`** na coluna `baixar` das ligas que deseja extrair.
- Para salvar: pressione `Ctrl + O` e depois `Enter`.
- Para sair: pressione `Ctrl + X`.

---

## 5. Executar em Segundo Plano (24/7 com `nohup`)

O comando `nohup` permite que o script continue rodando mesmo após você fechar o terminal SSH do seu computador.

### 🛡️ Opção A: Executar Versão 1.0 Oficial (Selenium Multi-Workers)
```bash
nohup python3 -u scrape_jogos_passados.py --proxy --workers 3 > scraper.log 2>&1 &
```

### 🚀 Opção B: Executar Versão 2.0 Ultra-Rápida (API Direta via `curl_cffi` - 30x mais rápida)
```bash
nohup python3 -u scrape_jogos_passados_fast.py --proxy --workers 10 > scraper.log 2>&1 &
```

### ⚡ Opção C: Executar Sequencial Simples (1 jogo por vez)
```bash
nohup python3 -u scrape_jogos_passados.py --proxy > scraper.log 2>&1 &
```

---

## 6. Comandos Úteis de Monitoramento e Controle

### 📡 Acompanhar os logs e extração em tempo real:
```bash
tail -f scraper.log
```
*(Pressione `Ctrl + C` para sair da visualização do log sem parar o scraper).*

### 📊 Verificar se o scraper está em execução:
```bash
ps aux | grep scrape_jogos_passados
pgrep -a chrome
pgrep -c chrome
pgrep -c chromium

```

### 🛑 Pausar / Parar a execução (Mata o Scraper e Processos Fantasmas):
```bash
# Opção 1: Mata tudo de uma vez
killall -9 chrome chromium chromium-browser chromedriver python3


# 1. Mata o script Python
pkill -9 -f scrape_jogos_passados.py
# 2. Mata todos os processos do Chrome / Chromium e ChromeDriver
pkill -9 -f chrome
pkill -9 -f chromium
pkill -9 -f chromedriver

```

### 🔍 Verificar se a memória/processos estão 100% limpos:
```bash
ps aux | grep -E 'python3|chrome|chromedriver'
```

### 🔄 Atualizar o código a partir do GitHub:
```bash
git pull origin main
```

---

## 7. Gerar Tabelas Finais (CSV) Manualmente

Quando quiser converter os dados baixados (JSON) em planilhas CSV consolidadas a qualquer momento:

### 📊 7.1 Gerar CSV de Jogos Passados / Históricos:
```bash
python3 generate_df_jogos_passados.py
```
*(Lê os arquivos de `jogos_passados/` e salva os CSVs consolidados em `data_jogos_passados/`).*

### 📅 7.2 Gerar CSV de Jogos Futuros / Agenda:
```bash
python3 generate_df_jogos_futuros.py
```
*(Lê os arquivos de `jogos_futuros/` e salva os CSVs consolidados em `data_jogos_futuros/`).*

---

## 8. Gerenciamento do Cache de Disco (`raw_html`)

> **Nota:** O cache de HTMLs foi desativado por padrão no código para manter o uso de SSD em 0MB constantes.

### 🧹 Limpeza Rápida de Cache Antigo:
```bash
rm -rf raw_html/*
```

### 📈 Verificar Espaço em Disco da VPS:
```bash
df -h
```
