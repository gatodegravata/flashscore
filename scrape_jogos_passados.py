#!/usr/bin/env python3
"""
Script COMPLETO para scraping de TODAS as ligas do FlashScore
Temporadas: 2021, 2021-2022, 2022, 2022-2023, 2023, 2023-2024, 2024, 2024-2025, 2025, 2025-2026, 2026
Total: ~780 ligas (10 temporadas × 78 ligas)
Duração estimada: Várias semanas
"""

import json
import os
import time
import subprocess
from datetime import datetime
import pandas as pd
from flashscore_scraper import FlashScoreScraper

# ==================== LIGAS 2021 (24 ligas) ====================
LINKS_2021 = [
'https://www.flashscore.com/football/argentina/torneo-betano-2021/results/',
'https://www.flashscore.com/football/bolivia/division-profesional-2021/results/',
'https://www.flashscore.com/football/brazil/serie-a-betano-2021/results/',
'https://www.flashscore.com/football/brazil/serie-b-2021/results/',
'https://www.flashscore.com/football/brazil/copa-betano-do-brasil-2021/results/',
'https://www.flashscore.com/football/chile/liga-de-primera-2021/results/',
'https://www.flashscore.com/football/china/super-league-2021/results/',
'https://www.flashscore.com/football/colombia/primera-a-2021/results/',
'https://www.flashscore.com/football/ecuador/liga-pro-2021/results/',
'https://www.flashscore.com/football/estonia/meistriliiga-2021/results/',
'https://www.flashscore.com/football/finland/veikkausliiga-2021/results/',
'https://www.flashscore.com/football/iceland/besta-deild-karla-2021/results/',
'https://www.flashscore.com/football/ireland/premier-division-2021/results/',
'https://www.flashscore.com/football/japan/j1-league-2021/results/',
'https://www.flashscore.com/football/norway/eliteserien-2021/results/',
'https://www.flashscore.com/football/paraguay/copa-de-primera-2021/results/',
'https://www.flashscore.com/football/peru/liga-1-2021/results/',
'https://www.flashscore.com/football/south-america/copa-libertadores-2021/results/',
'https://www.flashscore.com/football/south-america/copa-sudamericana-2021/results/',
'https://www.flashscore.com/football/south-korea/k-league-1-2021/results/',
'https://www.flashscore.com/football/sweden/allsvenskan-2021/results/',
'https://www.flashscore.com/football/uruguay/liga-auf-uruguaya-2021/results/',
'https://www.flashscore.com/football/usa/mls-2021/results/',
'https://www.flashscore.com/football/venezuela/liga-futve-2021/results/',
]

# ==================== LIGAS 2021-2022 (54 ligas) ====================
LINKS_2021_2022 = [
'https://www.flashscore.com/football/australia/a-league-2021-2022/results/',
'https://www.flashscore.com/football/austria/bundesliga-2021-2022/results/',
'https://www.flashscore.com/football/belgium/jupiler-pro-league-2021-2022/results/',
'https://www.flashscore.com/football/bosnia-and-herzegovina/wwin-liga-bih-2021-2022/results/',
'https://www.flashscore.com/football/bulgaria/efbet-league-2021-2022/results/',
'https://www.flashscore.com/football/croatia/hnl-2021-2022/results/',
'https://www.flashscore.com/football/cyprus/cyprus-league-2021-2022/results/',
'https://www.flashscore.com/football/czech-republic/chance-liga-2021-2022/results/',
'https://www.flashscore.com/football/denmark/superliga-2021-2022/results/',
'https://www.flashscore.com/football/egypt/premier-league-2021-2022/results/',
'https://www.flashscore.com/football/england/championship-2021-2022/results/',
'https://www.flashscore.com/football/england/league-one-2021-2022/results/',
'https://www.flashscore.com/football/england/league-two-2021-2022/results/',
'https://www.flashscore.com/football/england/premier-league-2021-2022/results/',
'https://www.flashscore.com/football/europe/champions-league-2021-2022/results/',
'https://www.flashscore.com/football/europe/europa-conference-league-2021-2022/results/',
'https://www.flashscore.com/football/europe/europa-league-2021-2022/results/',
'https://www.flashscore.com/football/france/ligue-1-2021-2022/results/',
'https://www.flashscore.com/football/france/ligue-2-2021-2022/results/',
'https://www.flashscore.com/football/france/national-2021-2022/results/',
'https://www.flashscore.com/football/germany/2-bundesliga-2021-2022/results/',
'https://www.flashscore.com/football/germany/bundesliga-2021-2022/results/',
'https://www.flashscore.com/football/germany/3-liga-2021-2022/results/',
'https://www.flashscore.com/football/greece/super-league-2021-2022/results/',
'https://www.flashscore.com/football/israel/ligat-ha-al-2021-2022/results/',
'https://www.flashscore.com/football/italy/serie-a-2021-2022/results/',
'https://www.flashscore.com/football/italy/serie-b-2021-2022/results/',
'https://www.flashscore.com/football/italy/serie-c-group-a-2021-2022/results/',
'https://www.flashscore.com/football/italy/serie-c-group-b-2021-2022/results/',
'https://www.flashscore.com/football/italy/serie-c-group-c-2021-2022/results/',
'https://www.flashscore.com/football/mexico/liga-mx-2021-2022/results/',
'https://www.flashscore.com/football/netherlands/eredivisie-2021-2022/results/',
'https://www.flashscore.com/football/netherlands/eerste-divisie-2021-2022/results/',
'https://www.flashscore.com/football/northern-ireland/nifl-premiership-2021-2022/results/',
'https://www.flashscore.com/football/poland/ekstraklasa-2021-2022/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2-2021-2022/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2021-2022/results/',
'https://www.flashscore.com/football/romania/superliga-2021-2022/results/',
'https://www.flashscore.com/football/saudi-arabia/saudi-professional-league-2021-2022/results/',
'https://www.flashscore.com/football/scotland/championship-2021-2022/results/',
'https://www.flashscore.com/football/scotland/premiership-2021-2022/results/',
'https://www.flashscore.com/football/scotland/league-one-2021-2022/results/',
'https://www.flashscore.com/football/scotland/league-two-2021-2022/results/',
'https://www.flashscore.com/football/serbia/mozzart-bet-super-liga-2021-2022/results/',
'https://www.flashscore.com/football/slovakia/nike-liga-2021-2022/results/',
'https://www.flashscore.com/football/slovenia/prva-liga-2021-2022/results/',
'https://www.flashscore.com/football/south-africa/betway-premiership-2021-2022/results/',
'https://www.flashscore.com/football/spain/laliga-2021-2022/results/',
'https://www.flashscore.com/football/spain/laliga2-2021-2022/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-1-2021-2022/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-2-2021-2022/results/',
'https://www.flashscore.com/football/switzerland/super-league-2021-2022/results/',
'https://www.flashscore.com/football/turkey/super-lig-2021-2022/results/',
'https://www.flashscore.com/football/ukraine/premier-league-2021-2022/results/',
'https://www.flashscore.com/football/wales/cymru-premier-2021-2022/results/'
]

# ==================== LIGAS 2022 (24 ligas) ====================
LINKS_2022 = [
'https://www.flashscore.com/football/argentina/torneo-betano-2022/results/',
'https://www.flashscore.com/football/bolivia/division-profesional-2022/results/',
'https://www.flashscore.com/football/brazil/serie-a-betano-2022/results/',
'https://www.flashscore.com/football/brazil/serie-b-2022/results/',
'https://www.flashscore.com/football/brazil/copa-betano-do-brasil-2022/results/',
'https://www.flashscore.com/football/chile/liga-de-primera-2022/results/',
'https://www.flashscore.com/football/china/super-league-2022/results/',
'https://www.flashscore.com/football/colombia/primera-a-2022/results/',
'https://www.flashscore.com/football/ecuador/liga-pro-2022/results/',
'https://www.flashscore.com/football/estonia/meistriliiga-2022/results/',
'https://www.flashscore.com/football/finland/veikkausliiga-2022/results/',
'https://www.flashscore.com/football/iceland/besta-deild-karla-2022/results/',
'https://www.flashscore.com/football/ireland/premier-division-2022/results/',
'https://www.flashscore.com/football/japan/j1-league-2022/results/',
'https://www.flashscore.com/football/norway/eliteserien-2022/results/',
'https://www.flashscore.com/football/paraguay/copa-de-primera-2022/results/',
'https://www.flashscore.com/football/peru/liga-1-2022/results/',
'https://www.flashscore.com/football/south-america/copa-libertadores-2022/results/',
'https://www.flashscore.com/football/south-america/copa-sudamericana-2022/results/',
'https://www.flashscore.com/football/south-korea/k-league-1-2022/results/',
'https://www.flashscore.com/football/sweden/allsvenskan-2022/results/',
'https://www.flashscore.com/football/uruguay/liga-auf-uruguaya-2022/results/',
'https://www.flashscore.com/football/usa/mls-2022/results/',
'https://www.flashscore.com/football/venezuela/liga-futve-2022/results/',
]

# ==================== LIGAS 2022-2023 (54 ligas) ====================
LINKS_2022_2023 = [
'https://www.flashscore.com/football/australia/a-league-2022-2023/results/',
'https://www.flashscore.com/football/austria/bundesliga-2022-2023/results/',
'https://www.flashscore.com/football/belgium/jupiler-pro-league-2022-2023/results/',
'https://www.flashscore.com/football/bosnia-and-herzegovina/wwin-liga-bih-2022-2023/results/',
'https://www.flashscore.com/football/bulgaria/efbet-league-2022-2023/results/',
'https://www.flashscore.com/football/croatia/hnl-2022-2023/results/',
'https://www.flashscore.com/football/cyprus/cyprus-league-2022-2023/results/',
'https://www.flashscore.com/football/czech-republic/chance-liga-2022-2023/results/',
'https://www.flashscore.com/football/denmark/superliga-2022-2023/results/',
'https://www.flashscore.com/football/egypt/premier-league-2022-2023/results/',
'https://www.flashscore.com/football/england/championship-2022-2023/results/',
'https://www.flashscore.com/football/england/league-one-2022-2023/results/',
'https://www.flashscore.com/football/england/league-two-2022-2023/results/',
'https://www.flashscore.com/football/england/premier-league-2022-2023/results/',
'https://www.flashscore.com/football/europe/champions-league-2022-2023/results/',
'https://www.flashscore.com/football/europe/europa-conference-league-2022-2023/results/',
'https://www.flashscore.com/football/europe/europa-league-2022-2023/results/',
'https://www.flashscore.com/football/france/ligue-1-2022-2023/results/',
'https://www.flashscore.com/football/france/ligue-2-2022-2023/results/',
'https://www.flashscore.com/football/france/national-2022-2023/results/',
'https://www.flashscore.com/football/germany/2-bundesliga-2022-2023/results/',
'https://www.flashscore.com/football/germany/bundesliga-2022-2023/results/',
'https://www.flashscore.com/football/germany/3-liga-2022-2023/results/',
'https://www.flashscore.com/football/greece/super-league-2022-2023/results/',
'https://www.flashscore.com/football/israel/ligat-ha-al-2022-2023/results/',
'https://www.flashscore.com/football/italy/serie-a-2022-2023/results/',
'https://www.flashscore.com/football/italy/serie-b-2022-2023/results/',
'https://www.flashscore.com/football/italy/serie-c-group-a-2022-2023/results/',
'https://www.flashscore.com/football/italy/serie-c-group-b-2022-2023/results/',
'https://www.flashscore.com/football/italy/serie-c-group-c-2022-2023/results/',
'https://www.flashscore.com/football/mexico/liga-mx-2022-2023/results/',
'https://www.flashscore.com/football/netherlands/eredivisie-2022-2023/results/',
'https://www.flashscore.com/football/netherlands/eerste-divisie-2022-2023/results/',
'https://www.flashscore.com/football/northern-ireland/nifl-premiership-2022-2023/results/',
'https://www.flashscore.com/football/poland/ekstraklasa-2022-2023/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2-2022-2023/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2022-2023/results/',
'https://www.flashscore.com/football/romania/superliga-2022-2023/results/',
'https://www.flashscore.com/football/saudi-arabia/saudi-professional-league-2022-2023/results/',
'https://www.flashscore.com/football/scotland/championship-2022-2023/results/',
'https://www.flashscore.com/football/scotland/premiership-2022-2023/results/',
'https://www.flashscore.com/football/scotland/league-one-2022-2023/results/',
'https://www.flashscore.com/football/scotland/league-two-2022-2023/results/',
'https://www.flashscore.com/football/serbia/mozzart-bet-super-liga-2022-2023/results/',
'https://www.flashscore.com/football/slovakia/nike-liga-2022-2023/results/',
'https://www.flashscore.com/football/slovenia/prva-liga-2022-2023/results/',
'https://www.flashscore.com/football/south-africa/betway-premiership-2022-2023/results/',
'https://www.flashscore.com/football/spain/laliga-2022-2023/results/',
'https://www.flashscore.com/football/spain/laliga2-2022-2023/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-1-2022-2023/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-2-2022-2023/results/',
'https://www.flashscore.com/football/switzerland/super-league-2022-2023/results/',
'https://www.flashscore.com/football/turkey/super-lig-2022-2023/results/',
'https://www.flashscore.com/football/ukraine/premier-league-2022-2023/results/',
'https://www.flashscore.com/football/wales/cymru-premier-2022-2023/results/'
]

# ==================== LIGAS 2023 (24 ligas) ====================
LINKS_2023 = [
'https://www.flashscore.com/football/argentina/torneo-betano-2023/results/',
'https://www.flashscore.com/football/bolivia/division-profesional-2023/results/',
'https://www.flashscore.com/football/brazil/serie-a-betano-2023/results/',
'https://www.flashscore.com/football/brazil/serie-b-2023/results/',
'https://www.flashscore.com/football/brazil/copa-betano-do-brasil-2023/results/',
'https://www.flashscore.com/football/chile/liga-de-primera-2023/results/',
'https://www.flashscore.com/football/china/super-league-2023/results/',
'https://www.flashscore.com/football/colombia/primera-a-2023/results/',
'https://www.flashscore.com/football/ecuador/liga-pro-2023/results/',
'https://www.flashscore.com/football/estonia/meistriliiga-2023/results/',
'https://www.flashscore.com/football/finland/veikkausliiga-2023/results/',
'https://www.flashscore.com/football/iceland/besta-deild-karla-2023/results/',
'https://www.flashscore.com/football/ireland/premier-division-2023/results/',
'https://www.flashscore.com/football/japan/j1-league-2023/results/',
'https://www.flashscore.com/football/norway/eliteserien-2023/results/',
'https://www.flashscore.com/football/paraguay/copa-de-primera-2023/results/',
'https://www.flashscore.com/football/peru/liga-1-2023/results/',
'https://www.flashscore.com/football/south-america/copa-libertadores-2023/results/',
'https://www.flashscore.com/football/south-america/copa-sudamericana-2023/results/',
'https://www.flashscore.com/football/south-korea/k-league-1-2023/results/',
'https://www.flashscore.com/football/sweden/allsvenskan-2023/results/',
'https://www.flashscore.com/football/uruguay/liga-auf-uruguaya-2023/results/',
'https://www.flashscore.com/football/usa/mls-2023/results/',
'https://www.flashscore.com/football/venezuela/liga-futve-2023/results/',
]

# ==================== LIGAS 2023-2024 (54 ligas) ====================
LINKS_2023_2024 = [
'https://www.flashscore.com/football/australia/a-league-2023-2024/results/',
'https://www.flashscore.com/football/austria/bundesliga-2023-2024/results/',
'https://www.flashscore.com/football/belgium/jupiler-pro-league-2023-2024/results/',
'https://www.flashscore.com/football/bosnia-and-herzegovina/wwin-liga-bih-2023-2024/results/',
'https://www.flashscore.com/football/bulgaria/efbet-league-2023-2024/results/',
'https://www.flashscore.com/football/croatia/hnl-2023-2024/results/',
'https://www.flashscore.com/football/cyprus/cyprus-league-2023-2024/results/',
'https://www.flashscore.com/football/czech-republic/chance-liga-2023-2024/results/',
'https://www.flashscore.com/football/denmark/superliga-2023-2024/results/',
'https://www.flashscore.com/football/egypt/premier-league-2023-2024/results/',
'https://www.flashscore.com/football/england/championship-2023-2024/results/',
'https://www.flashscore.com/football/england/league-one-2023-2024/results/',
'https://www.flashscore.com/football/england/league-two-2023-2024/results/',
'https://www.flashscore.com/football/england/premier-league-2023-2024/results/',
'https://www.flashscore.com/football/europe/champions-league-2023-2024/results/',
'https://www.flashscore.com/football/europe/europa-conference-league-2023-2024/results/',
'https://www.flashscore.com/football/europe/europa-league-2023-2024/results/',
'https://www.flashscore.com/football/france/ligue-1-2023-2024/results/',
'https://www.flashscore.com/football/france/ligue-2-2023-2024/results/',
'https://www.flashscore.com/football/france/national-2023-2024/results/',
'https://www.flashscore.com/football/germany/2-bundesliga-2023-2024/results/',
'https://www.flashscore.com/football/germany/bundesliga-2023-2024/results/',
'https://www.flashscore.com/football/germany/3-liga-2023-2024/results/',
'https://www.flashscore.com/football/greece/super-league-2023-2024/results/',
'https://www.flashscore.com/football/israel/ligat-ha-al-2023-2024/results/',
'https://www.flashscore.com/football/italy/serie-a-2023-2024/results/',
'https://www.flashscore.com/football/italy/serie-b-2023-2024/results/',
'https://www.flashscore.com/football/italy/serie-c-group-a-2023-2024/results/',
'https://www.flashscore.com/football/italy/serie-c-group-b-2023-2024/results/',
'https://www.flashscore.com/football/italy/serie-c-group-c-2023-2024/results/',
'https://www.flashscore.com/football/mexico/liga-mx-2023-2024/results/',
'https://www.flashscore.com/football/netherlands/eredivisie-2023-2024/results/',
'https://www.flashscore.com/football/netherlands/eerste-divisie-2023-2024/results/',
'https://www.flashscore.com/football/northern-ireland/nifl-premiership-2023-2024/results/',
'https://www.flashscore.com/football/poland/ekstraklasa-2023-2024/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2-2023-2024/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2023-2024/results/',
'https://www.flashscore.com/football/romania/superliga-2023-2024/results/',
'https://www.flashscore.com/football/saudi-arabia/saudi-professional-league-2023-2024/results/',
'https://www.flashscore.com/football/scotland/championship-2023-2024/results/',
'https://www.flashscore.com/football/scotland/premiership-2023-2024/results/',
'https://www.flashscore.com/football/scotland/league-one-2023-2024/results/',
'https://www.flashscore.com/football/scotland/league-two-2023-2024/results/',
'https://www.flashscore.com/football/serbia/mozzart-bet-super-liga-2023-2024/results/',
'https://www.flashscore.com/football/slovakia/nike-liga-2023-2024/results/',
'https://www.flashscore.com/football/slovenia/prva-liga-2023-2024/results/',
'https://www.flashscore.com/football/south-africa/betway-premiership-2023-2024/results/',
'https://www.flashscore.com/football/spain/laliga-2023-2024/results/',
'https://www.flashscore.com/football/spain/laliga2-2023-2024/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-1-2023-2024/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-2-2023-2024/results/',
'https://www.flashscore.com/football/switzerland/super-league-2023-2024/results/',
'https://www.flashscore.com/football/turkey/super-lig-2023-2024/results/',
'https://www.flashscore.com/football/ukraine/premier-league-2023-2024/results/',
'https://www.flashscore.com/football/wales/cymru-premier-2023-2024/results/'
]

# ==================== LIGAS 2024 (24 ligas) ====================
LINKS_2024 = [
'https://www.flashscore.com/football/argentina/torneo-betano-2024/results/',
'https://www.flashscore.com/football/bolivia/division-profesional-2024/results/',
'https://www.flashscore.com/football/brazil/serie-a-betano-2024/results/',
'https://www.flashscore.com/football/brazil/serie-b-2024/results/',
'https://www.flashscore.com/football/brazil/copa-betano-do-brasil-2024/results/',
'https://www.flashscore.com/football/chile/liga-de-primera-2024/results/',
'https://www.flashscore.com/football/china/super-league-2024/results/',
'https://www.flashscore.com/football/colombia/primera-a-2024/results/',
'https://www.flashscore.com/football/ecuador/liga-pro-2024/results/',
'https://www.flashscore.com/football/estonia/meistriliiga-2024/results/',
'https://www.flashscore.com/football/finland/veikkausliiga-2024/results/',
'https://www.flashscore.com/football/iceland/besta-deild-karla-2024/results/',
'https://www.flashscore.com/football/ireland/premier-division-2024/results/',
'https://www.flashscore.com/football/japan/j1-league-2024/results/',
'https://www.flashscore.com/football/norway/eliteserien-2024/results/',
'https://www.flashscore.com/football/paraguay/copa-de-primera-2024/results/',
'https://www.flashscore.com/football/peru/liga-1-2024/results/',
'https://www.flashscore.com/football/south-america/copa-libertadores-2024/results/',
'https://www.flashscore.com/football/south-america/copa-sudamericana-2024/results/',
'https://www.flashscore.com/football/south-korea/k-league-1-2024/results/',
'https://www.flashscore.com/football/sweden/allsvenskan-2024/results/',
'https://www.flashscore.com/football/uruguay/liga-auf-uruguaya-2024/results/',
'https://www.flashscore.com/football/usa/mls-2024/results/',
'https://www.flashscore.com/football/venezuela/liga-futve-2024/results/',
]

# ==================== LIGAS 2024-2025 (54 ligas) ====================
LINKS_2024_2025 = [
'https://www.flashscore.com/football/australia/a-league-2024-2025/results/',
'https://www.flashscore.com/football/austria/bundesliga-2024-2025/results/',
'https://www.flashscore.com/football/belgium/jupiler-pro-league-2024-2025/results/',
'https://www.flashscore.com/football/bosnia-and-herzegovina/wwin-liga-bih-2024-2025/results/',
'https://www.flashscore.com/football/bulgaria/efbet-league-2024-2025/results/',
'https://www.flashscore.com/football/croatia/hnl-2024-2025/results/',
'https://www.flashscore.com/football/cyprus/cyprus-league-2024-2025/results/',
'https://www.flashscore.com/football/czech-republic/chance-liga-2024-2025/results/',
'https://www.flashscore.com/football/denmark/superliga-2024-2025/results/',
'https://www.flashscore.com/football/egypt/premier-league-2024-2025/results/',
'https://www.flashscore.com/football/england/championship-2024-2025/results/',
'https://www.flashscore.com/football/england/league-one-2024-2025/results/',
'https://www.flashscore.com/football/england/league-two-2024-2025/results/',
'https://www.flashscore.com/football/england/premier-league-2024-2025/results/',
'https://www.flashscore.com/football/europe/champions-league-2024-2025/results/',
'https://www.flashscore.com/football/europe/europa-conference-league-2024-2025/results/',
'https://www.flashscore.com/football/europe/europa-league-2024-2025/results/',
'https://www.flashscore.com/football/france/ligue-1-2024-2025/results/',
'https://www.flashscore.com/football/france/ligue-2-2024-2025/results/',
'https://www.flashscore.com/football/france/national-2024-2025/results/',
'https://www.flashscore.com/football/germany/2-bundesliga-2024-2025/results/',
'https://www.flashscore.com/football/germany/bundesliga-2024-2025/results/',
'https://www.flashscore.com/football/germany/3-liga-2024-2025/results/',
'https://www.flashscore.com/football/greece/super-league-2024-2025/results/',
'https://www.flashscore.com/football/israel/ligat-ha-al-2024-2025/results/',
'https://www.flashscore.com/football/italy/serie-a-2024-2025/results/',
'https://www.flashscore.com/football/italy/serie-b-2024-2025/results/',
'https://www.flashscore.com/football/italy/serie-c-group-a-2024-2025/results/',
'https://www.flashscore.com/football/italy/serie-c-group-b-2024-2025/results/',
'https://www.flashscore.com/football/italy/serie-c-group-c-2024-2025/results/',
'https://www.flashscore.com/football/mexico/liga-mx-2024-2025/results/',
'https://www.flashscore.com/football/netherlands/eredivisie-2024-2025/results/',
'https://www.flashscore.com/football/netherlands/eerste-divisie-2024-2025/results/',
'https://www.flashscore.com/football/northern-ireland/nifl-premiership-2024-2025/results/',
'https://www.flashscore.com/football/poland/ekstraklasa-2024-2025/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2-2024-2025/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2024-2025/results/',
'https://www.flashscore.com/football/romania/superliga-2024-2025/results/',
'https://www.flashscore.com/football/saudi-arabia/saudi-professional-league-2024-2025/results/',
'https://www.flashscore.com/football/scotland/championship-2024-2025/results/',
'https://www.flashscore.com/football/scotland/premiership-2024-2025/results/',
'https://www.flashscore.com/football/scotland/league-one-2024-2025/results/',
'https://www.flashscore.com/football/scotland/league-two-2024-2025/results/',
'https://www.flashscore.com/football/serbia/mozzart-bet-super-liga-2024-2025/results/',
'https://www.flashscore.com/football/slovakia/nike-liga-2024-2025/results/',
'https://www.flashscore.com/football/slovenia/prva-liga-2024-2025/results/',
'https://www.flashscore.com/football/south-africa/betway-premiership-2024-2025/results/',
'https://www.flashscore.com/football/spain/laliga-2024-2025/results/',
'https://www.flashscore.com/football/spain/laliga2-2024-2025/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-1-2024-2025/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-2-2024-2025/results/',
'https://www.flashscore.com/football/switzerland/super-league-2024-2025/results/',
'https://www.flashscore.com/football/turkey/super-lig-2024-2025/results/',
'https://www.flashscore.com/football/ukraine/premier-league-2024-2025/results/',
'https://www.flashscore.com/football/wales/cymru-premier-2024-2025/results/'
]

LINKS_2025 = [
'https://www.flashscore.com/football/argentina/torneo-betano-2025/results/',
'https://www.flashscore.com/football/bolivia/division-profesional-2025/results/',
'https://www.flashscore.com/football/brazil/serie-a-betano-2025/results/',
'https://www.flashscore.com/football/brazil/serie-b-2025/results/',
'https://www.flashscore.com/football/brazil/copa-betano-do-brasil-2025/results/',
'https://www.flashscore.com/football/chile/liga-de-primera-2025/results/',
'https://www.flashscore.com/football/china/super-league-2025/results/',
'https://www.flashscore.com/football/colombia/primera-a-2025/results/',
'https://www.flashscore.com/football/ecuador/liga-pro-2025/results/',
'https://www.flashscore.com/football/estonia/meistriliiga-2025/results/',
'https://www.flashscore.com/football/finland/veikkausliiga-2025/results/',
'https://www.flashscore.com/football/iceland/besta-deild-karla-2025/results/',
'https://www.flashscore.com/football/ireland/premier-division-2025/results/',
'https://www.flashscore.com/football/japan/j1-league-2025/results/',
'https://www.flashscore.com/football/norway/eliteserien-2025/results/',
'https://www.flashscore.com/football/paraguay/copa-de-primera-2025/results/',
'https://www.flashscore.com/football/peru/liga-1-2025/results/',
'https://www.flashscore.com/football/south-america/copa-libertadores-2025/results/',
'https://www.flashscore.com/football/south-america/copa-sudamericana-2025/results/',
'https://www.flashscore.com/football/south-korea/k-league-1-2025/results/',
'https://www.flashscore.com/football/sweden/allsvenskan-2025/results/',
'https://www.flashscore.com/football/uruguay/liga-auf-uruguaya-2025/results/',
'https://www.flashscore.com/football/usa/mls-2025/results/',
'https://www.flashscore.com/football/venezuela/liga-futve-2025/results/',
]

LINKS_2026 = [
'https://www.flashscore.com/football/argentina/torneo-betano-2026/results/',
'https://www.flashscore.com/football/bolivia/division-profesional-2026/results/',
'https://www.flashscore.com/football/brazil/serie-a-betano-2026/results/',
'https://www.flashscore.com/football/brazil/serie-b-2026/results/',
'https://www.flashscore.com/football/brazil/copa-betano-do-brasil-2026/results/',
'https://www.flashscore.com/football/chile/liga-de-primera-2026/results/',
'https://www.flashscore.com/football/china/super-league-2026/results/',
'https://www.flashscore.com/football/colombia/primera-a-2026/results/',
'https://www.flashscore.com/football/ecuador/liga-pro-2026/results/',
'https://www.flashscore.com/football/estonia/meistriliiga-2026/results/',
'https://www.flashscore.com/football/finland/veikkausliiga-2026/results/',
'https://www.flashscore.com/football/iceland/besta-deild-karla-2026/results/',
'https://www.flashscore.com/football/ireland/premier-division-2026/results/',
'https://www.flashscore.com/football/japan/j1-league-2026/results/',
'https://www.flashscore.com/football/norway/eliteserien-2026/results/',
'https://www.flashscore.com/football/paraguay/copa-de-primera-2026/results/',
'https://www.flashscore.com/football/peru/liga-1-2026/results/',
'https://www.flashscore.com/football/south-america/copa-libertadores-2026/results/',
'https://www.flashscore.com/football/south-america/copa-sudamericana-2026/results/',
'https://www.flashscore.com/football/south-korea/k-league-1-2026/results/',
'https://www.flashscore.com/football/sweden/allsvenskan-2026/results/',
'https://www.flashscore.com/football/uruguay/liga-auf-uruguaya-2026/results/',
'https://www.flashscore.com/football/usa/mls-2026/results/',
'https://www.flashscore.com/football/venezuela/liga-futve-2026/results/',
]
# ==================== LIGAS 2025-2026 (54 ligas) ====================
LINKS_2025_2026 = [
'https://www.flashscore.com/football/australia/a-league-2025-2026/results/',
'https://www.flashscore.com/football/austria/bundesliga-2025-2026/results/',
'https://www.flashscore.com/football/belgium/jupiler-pro-league-2025-2026/results/',
'https://www.flashscore.com/football/bosnia-and-herzegovina/wwin-liga-bih-2025-2026/results/',
'https://www.flashscore.com/football/bulgaria/efbet-league-2025-2026/results/',
'https://www.flashscore.com/football/croatia/hnl-2025-2026/results/',
'https://www.flashscore.com/football/cyprus/cyprus-league-2025-2026/results/',
'https://www.flashscore.com/football/czech-republic/chance-liga-2025-2026/results/',
'https://www.flashscore.com/football/denmark/superliga-2025-2026/results/',
'https://www.flashscore.com/football/egypt/premier-league-2025-2026/results/',
'https://www.flashscore.com/football/england/championship-2025-2026/results/',
'https://www.flashscore.com/football/england/league-one-2025-2026/results/',
'https://www.flashscore.com/football/england/league-two-2025-2026/results/',
'https://www.flashscore.com/football/england/premier-league-2025-2026/results/',
'https://www.flashscore.com/football/europe/champions-league-2025-2026/results/',
'https://www.flashscore.com/football/europe/europa-conference-league-2025-2026/results/',
'https://www.flashscore.com/football/europe/europa-league-2025-2026/results/',
'https://www.flashscore.com/football/france/ligue-1-2025-2026/results/',
'https://www.flashscore.com/football/france/ligue-2-2025-2026/results/',
'https://www.flashscore.com/football/france/national-2025-2026/results/',
'https://www.flashscore.com/football/germany/2-bundesliga-2025-2026/results/',
'https://www.flashscore.com/football/germany/bundesliga-2025-2026/results/',
'https://www.flashscore.com/football/germany/3-liga-2025-2026/results/',
'https://www.flashscore.com/football/greece/super-league-2025-2026/results/',
'https://www.flashscore.com/football/israel/ligat-ha-al-2025-2026/results/',
'https://www.flashscore.com/football/italy/serie-a-2025-2026/results/',
'https://www.flashscore.com/football/italy/serie-b-2025-2026/results/',
'https://www.flashscore.com/football/italy/serie-c-group-a-2025-2026/results/',
'https://www.flashscore.com/football/italy/serie-c-group-b-2025-2026/results/',
'https://www.flashscore.com/football/italy/serie-c-group-c-2025-2026/results/',
'https://www.flashscore.com/football/mexico/liga-mx-2025-2026/results/',
'https://www.flashscore.com/football/netherlands/eredivisie-2025-2026/results/',
'https://www.flashscore.com/football/netherlands/eerste-divisie-2025-2026/results/',
'https://www.flashscore.com/football/northern-ireland/nifl-premiership-2025-2026/results/',
'https://www.flashscore.com/football/poland/ekstraklasa-2025-2026/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2-2025-2026/results/',
'https://www.flashscore.com/football/portugal/liga-portugal-2025-2026/results/',
'https://www.flashscore.com/football/romania/superliga-2025-2026/results/',
'https://www.flashscore.com/football/saudi-arabia/saudi-professional-league-2025-2026/results/',
'https://www.flashscore.com/football/scotland/championship-2025-2026/results/',
'https://www.flashscore.com/football/scotland/premiership-2025-2026/results/',
'https://www.flashscore.com/football/scotland/league-one-2025-2026/results/',
'https://www.flashscore.com/football/scotland/league-two-2025-2026/results/',
'https://www.flashscore.com/football/serbia/mozzart-bet-super-liga-2025-2026/results/',
'https://www.flashscore.com/football/slovakia/nike-liga-2025-2026/results/',
'https://www.flashscore.com/football/slovenia/prva-liga-2025-2026/results/',
'https://www.flashscore.com/football/south-africa/betway-premiership-2025-2026/results/',
'https://www.flashscore.com/football/spain/laliga-2025-2026/results/',
'https://www.flashscore.com/football/spain/laliga2-2025-2026/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-1-2025-2026/results/',
'https://www.flashscore.com/football/spain/primera-rfef-group-2-2025-2026/results/',
'https://www.flashscore.com/football/switzerland/super-league-2025-2026/results/',
'https://www.flashscore.com/football/turkey/super-lig-2025-2026/results/',
'https://www.flashscore.com/football/ukraine/premier-league-2025-2026/results/',
'https://www.flashscore.com/football/wales/cymru-premier-2025-2026/results/'
]

def git_commit(message, file_path=None):
    """
    Faz commit automático no git e push para o GitHub
    Args:
        message: Mensagem do commit
        file_path: Arquivo específico para adicionar (opcional, se None adiciona tudo)
    """
    try:
        if file_path:
            subprocess.run(['git', 'add', file_path], check=True, capture_output=True)
        else:
            subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        
        result = subprocess.run(['git', 'commit', '-m', message], 
                              check=True, capture_output=True, text=True)
        print(f"  ✓ Git commit: {message}")
        
        # Push automático para o GitHub
        push_result = subprocess.run(['git', 'push'], 
                                    check=True, capture_output=True, text=True)
        print(f"  ✓ Git push: Enviado para GitHub")
        return True
    except subprocess.CalledProcessError:
        # Ignora erro (pode ser que não tenha mudanças para commitar)
        return False
    except Exception as e:
        print(f"  ⚠️ Erro no git commit/push: {e}")
        return False


def extract_country_from_url(url):
    """Extrai o país da URL"""
    for marker in ['/football/', '/futebol/']:
        if marker in url:
            parts = url.split(marker)
            if len(parts) > 1:
                return parts[1].split('/')[0]
    return 'unknown'


def extract_league_name_from_url(url):
    """Extrai o nome da liga da URL"""
    for marker in ['/football/', '/futebol/']:
        if marker in url:
            parts = url.split(marker)
            if len(parts) > 1:
                subparts = parts[1].split('/')
                if len(subparts) > 1:
                    return subparts[1].replace('-', ' ').title()
    return 'Unknown League'


def extract_season_from_url(url):
    """Extrai a temporada da URL"""
    import re
    match = re.search(r'(\d{4}(?:-\d{4})?)', url)
    if match:
        return match.group(1)
    return 'unknown'


_STAGES_CACHE = None

def get_stages_mapping():
    """
    Carrega e armazena em cache o mapeamento de estágios direto de auxiliares/temporadas_ligas.json.
    Retorna um dicionário { url_normalizada: [stage_type_ids] }
    """
    global _STAGES_CACHE
    if _STAGES_CACHE is not None:
        return _STAGES_CACHE
    
    _STAGES_CACHE = {}
    json_path = "auxiliares/temporadas_ligas.json"
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for l in data.get('leagues', []):
                for s in l.get('seasons', []):
                    u = s.get('url', '').rstrip('/') + '/'
                    st_types = s.get('stage_types', [])
                    if not st_types and s.get('stage_type_id'):
                        st_types = [s.get('stage_type_id')]
                    if u:
                        _STAGES_CACHE[u] = [str(st) for st in st_types]
                        _STAGES_CACHE[u.rstrip('/') + '/results/'] = [str(st) for st in st_types]
        except Exception:
            pass
            
    return _STAGES_CACHE


def get_match_ids_from_league(scraper, league_url):
    """Extrai todos os IDs de partidas de uma página de liga"""
    # Garante que navega sempre para a aba /results/ da temporada
    target_results_url = league_url.strip().rstrip('/')
    if not target_results_url.endswith('/results'):
        target_results_url = target_results_url + '/results/'
    else:
        target_results_url = target_results_url + '/'
        
    display_name = target_results_url
    for marker in ['/football/', '/futebol/']:
        if marker in target_results_url:
            display_name = target_results_url.split(marker)[1]
            break
    print(f"\n🔍 Carregando: {display_name}")
    
    # Verifica e recria driver se necessário
    recreate_driver_if_needed(scraper)
    
    scraper.driver.get(target_results_url)
    
    try:
        import re
        import datetime
        from curl_cffi import requests
        from bs4 import BeautifulSoup
        
        time.sleep(3)
        
        # PRIMEIRO: Aceitar cookies e fechar modal de verificação de idade (+18)
        try:
            cookie_button = scraper.driver.find_element("css selector", "button#onetrust-accept-btn-handler")
            if cookie_button.is_displayed():
                cookie_button.click()
                print(f"  ✓ Cookies aceitos")
                time.sleep(1)
        except:
            pass
            
        try:
            age_btns = scraper.driver.find_elements("xpath", "//button[contains(., '18 AND OLDER') or contains(., '18 e mais') or contains(., '18')]")
            for abtn in age_btns:
                if abtn.is_displayed():
                    scraper.driver.execute_script("arguments[0].click();", abtn)
                    print(f"  ✓ Modal de idade fechado")
                    time.sleep(1)
                    break
        except:
            pass

        try:
            # Aciona todos os botões de expansão via DOM e JS do Flashscore
            for _ in range(30):
                scraper.driver.execute_script("""
                    window.scrollTo(0, document.body.scrollHeight);
                    var btns = document.querySelectorAll('.event__more, a.event__more, [class*="event__more"], a.link-more-games, [class*="showMore"]');
                    btns.forEach(function(b) {
                        try { b.click(); } catch(e) {}
                    });
                """)
                time.sleep(1.5)
                
                # Se não houver mais botões visíveis de 'Show more', para
                remaining = scraper.driver.execute_script("""
                    var btns = Array.from(document.querySelectorAll('.event__more, a.event__more, [class*="event__more"], a.link-more-games, [class*="showMore"]'));
                    return btns.filter(b => b.offsetParent !== null).length;
                """)
                if remaining == 0:
                    break
        except Exception:
            pass
            
        match_ids = []
        seen_ids = set()
        match_metadata = {}
        
        # 1. Coleta os dados renderizados no DOM completo da página
        soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')
        for elem in soup.select("div[id^='g_1_'], div.event__match"):
            mid = elem.get('id', '').replace('g_1_', '')
            if mid and len(mid) == 8 and mid not in seen_ids:
                seen_ids.add(mid)
                match_ids.append(mid)
                
                # Extrai informações do card HTML com suporte ao novo layout Flashscore
                h_elem = elem.select_one(".event__homeParticipant [class*='name_'], .event__participant--home, .event__homeParticipant")
                a_elem = elem.select_one(".event__awayParticipant [class*='name_'], .event__participant--away, .event__awayParticipant")
                s_h_elem = elem.select_one(".event__score--home")
                s_a_elem = elem.select_one(".event__score--away")
                t_elem = elem.select_one("[class*='dateContent_'], .event__time")
                r_elem = elem.find_previous("div", class_=lambda c: c and ("event__round" in c or "event__header" in c or "event__title" in c))
                
                # Extrai Home_ID e Away_ID do link do jogo (ex: /atletico-ottawa-xdCBerfb/cavalry-EHhWJdNd/)
                link_elem = elem.select_one("a.eventRowLink")
                home_id = None
                away_id = None
                if link_elem and link_elem.get('href'):
                    href = link_elem.get('href')
                    m_teams = re.search(r'/match/football/([^/]+)-([a-zA-Z0-9]{8})/([^/]+)-([a-zA-Z0-9]{8})', href)
                    if m_teams:
                        home_id = m_teams.group(2)
                        away_id = m_teams.group(4)
                
                h_name = h_elem.get_text(strip=True) if h_elem else None
                a_name = a_elem.get_text(strip=True) if a_elem else None
                h_score = int(s_h_elem.get_text(strip=True)) if s_h_elem and s_h_elem.get_text(strip=True).isdigit() else None
                a_score = int(s_a_elem.get_text(strip=True)) if s_a_elem and s_a_elem.get_text(strip=True).isdigit() else None
                
                raw_time = t_elem.get_text(strip=True) if t_elem else ""
                match_date = None
                match_time = None
                if raw_time and "." in raw_time:
                    parts = raw_time.split()
                    if len(parts) >= 2:
                        match_date = parts[0]
                        match_time = parts[1]
                    else:
                        match_date = parts[0]
                elif raw_time:
                    match_date = raw_time
                        
                round_name = r_elem.get_text(strip=True) if r_elem else None
                is_neutral = bool(
                    elem.select_one('[title*="Neutral location"], [data-tooltip*="Neutral location"], [aria-label*="Neutral location"]') 
                    or 'Neutral location' in elem.get_text()
                    or elem.select_one('.event__stage--info, .event__info, [class*="neutral"]')
                )
                
                match_metadata[mid] = {
                    'Match_ID': mid,
                    'Id': mid,
                    'Date': match_date,
                    'Time': match_time,
                    'Round': round_name,
                    'Home': h_name,
                    'Home_ID': home_id,
                    'Away': a_name,
                    'Away_ID': away_id,
                    'Home_Score': h_score,
                    'Away_Score': a_score,
                    'Neutral_Location': is_neutral,
                    'Tournament_ID': None,
                }
                
        # 2. Constrói e consulta os feeds de resultados diretamente para garantir fases e playoffs
        import re
        import datetime
        from curl_cffi import requests
        
        s_feed = requests.Session(impersonate="chrome120")
        feed_headers = {
            "x-fsign": "SW9D1eZo",
            "Referer": "https://www.flashscore.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Pega todas as chaves de torneio/stage da página atual
        page_tournament = scraper.driver.execute_script("""
            var t_id = null;
            if (window.dataLayer && Array.isArray(window.dataLayer)) {
                for (var i = 0; i < window.dataLayer.length; i++) {
                    if (window.dataLayer[i] && window.dataLayer[i].tournament) {
                        t_id = window.dataLayer[i].tournament;
                        break;
                    }
                }
            }
            var res = performance.getEntriesByType('resource').map(r => r.name);
            var tr = res.filter(u => u.includes('/feed/tr_1_'));
            
            // Pega IDs adicionais de torneios presentes nos atributos HTML
            var stage_keys = [];
            document.querySelectorAll('[data-label-key], [class*="pinMyLeague"]').forEach(el => {
                var k = el.getAttribute('data-label-key') || el.className;
                var m = k.match(/1_\\d+_([a-zA-Z0-9]{8})/);
                if (m && !stage_keys.includes(m[1])) stage_keys.push(m[1]);
            });
            
            return { tournament: t_id, tr: tr, stage_keys: stage_keys };
        """)
        
        feed_templates = []
        if page_tournament and page_tournament.get('tr') and len(page_tournament['tr']) > 0:
            for tr_url in page_tournament['tr']:
                feed_templates.append(tr_url)
            
        t_id = page_tournament.get('tournament') if page_tournament else None
        if not t_id:
            m_dl = re.search(r'\"tournament\":\"([a-zA-Z0-9]{8})\"', scraper.driver.page_source)
            if m_dl:
                t_id = m_dl.group(1)

        # Extrai ano da liga a partir da URL (ex: canadian-premier-league-2024/ -> 2024; canadian-premier-league/ -> 2026)
        m_single = re.search(r'-(20\d\d)(?:/|$)', league_url)
        m_double = re.search(r'-(20\d\d)-(20\d\d)(?:/|$)', league_url)
        if m_double:
            league_target_year = int(m_double.group(2))
            is_cross_year = True
        elif m_single:
            league_target_year = int(m_single.group(1))
            is_cross_year = False
        else:
            league_target_year = datetime.datetime.now().year
            is_cross_year = False

        all_t_ids = set()
        if t_id:
            all_t_ids.add(t_id)
        if page_tournament and page_tournament.get('stage_keys'):
            for sk in page_tournament['stage_keys']:
                all_t_ids.add(sk)
                
        # Adiciona chaves extras de feed capturadas
        if page_tournament and page_tournament.get('tr') and len(page_tournament['tr']) > 0:
            for tr_url in page_tournament['tr']:
                feed_templates.append(tr_url)
                
        # Normaliza a URL da liga para busca no mapeamento oficial
        norm_league_url = league_url.strip().rstrip('/') + '/'
        stages_map = get_stages_mapping()
        mapped_stages = stages_map.get(norm_league_url, None)
        
        if mapped_stages is not None and len(mapped_stages) > 0:
            print(f"  🎯 Stage Type(s) mapeados no GraphQL: {mapped_stages}")
            flags_to_check = [int(s) for s in mapped_stages if str(s).isdigit()] + [156, 12, 11, 0, 1, 2, 3]
            flags_to_check = list(dict.fromkeys(flags_to_check))
        else:
            flags_to_check = [156, 12, 11, 0, 1, 2, 3] + list(range(170, 207))
            flags_to_check = list(dict.fromkeys(flags_to_check))
        
        # Recupera as chaves principais
        main_ck = page_tournament.get('ck', '47') if page_tournament else '47'
        
        # E TAMBÉM inclui todas as chaves de estágios e torneios descobertas na página
        for tid_candidate in all_t_ids:
            if not tid_candidate: continue
            for flag in flags_to_check:
                feed_templates.append(f"https://global.flashscore.ninja/2/x/feed/tr_1_{main_ck}_{tid_candidate}_{flag}_0_-3_en_1")
                
        # Remove templates duplicados
        feed_templates = list(dict.fromkeys(feed_templates))
        print(f"  ⚡ Consultando feeds oficiais da liga ({len(feed_templates)} templates)...")
        for ft in feed_templates:
            # Varre até 25 páginas para suportar temporadas completas e divisões longas
            consecutive_empty = 0
            for page in range(0, 25):
                p_url = re.sub(r'(_\d+_)(-?\d+_en_\d+)', rf'_{page}_\2', ft)
                try:
                    r_feed = s_feed.get(p_url, headers=feed_headers, timeout=6)
                    if r_feed.status_code == 200 and r_feed.text and '~AA' in r_feed.text:
                        consecutive_empty = 0
                        items = r_feed.text.split('~AA')
                        for item in items[1:]:
                            tokens = re.split(r'[\xac\xf7]', item)
                            if not tokens:
                                continue
                            mid = tokens[1] if len(tokens) > 1 and tokens[0] == '' else tokens[0]
                            if not mid or len(mid) != 8:
                                continue
                                
                            d = {}
                            for i in range(0, len(tokens)-1):
                                k = tokens[i]
                                v = tokens[i+1]
                                if k.isupper() and len(k) <= 4:
                                    d[k] = v
                                
                            # Converte timestamp em Date e Time
                            ts = int(d.get('AD', 0)) if d.get('AD') and d.get('AD').isdigit() else 0
                            dt = datetime.datetime.fromtimestamp(ts) if ts else None
                            
                            # Filtro estrito do ano correspondente da temporada
                            if dt and league_target_year:
                                if is_cross_year:
                                    if dt.year != league_target_year and dt.year != (league_target_year - 1):
                                        continue
                                else:
                                    if dt.year != league_target_year:
                                        continue
                            
                            is_neutral = 'Neutral location' in d.get('AM', '') or 'neutral' in d.get('AM', '').lower()
                            
                            meta = {
                                'Match_ID': mid,
                                'Id': mid,
                                'Date': dt.strftime('%Y-%m-%d') if dt else None,
                                'Time': dt.strftime('%H:%M') if dt else None,
                                'Round': d.get('ER'),
                                'Home': d.get('AE'),
                                'Home_ID': d.get('PX'),
                                'Away': d.get('AF'),
                                'Away_ID': d.get('PY'),
                                'Home_Score': int(d.get('AG')) if d.get('AG') is not None and d.get('AG').isdigit() else None,
                                'Away_Score': int(d.get('AH')) if d.get('AH') is not None and d.get('AH').isdigit() else None,
                                'Neutral_Location': is_neutral,
                                'Tournament_ID': t_id,
                            }
                            match_metadata[mid] = meta
                            
                            if mid not in seen_ids:
                                seen_ids.add(mid)
                                match_ids.append(mid)
                    else:
                        consecutive_empty += 1
                        if page == 0:
                            break # OTIMIZAÇÃO: Se a página 0 da flag não tem jogos, a flag/fase inteira não existe!
                        if consecutive_empty >= 2:
                            break
                except Exception:
                    consecutive_empty += 1
                    if page == 0:
                        break
                    if consecutive_empty >= 2:
                        break
        
        print(f"  ✓ {len(match_ids)} jogos encontrados na liga!")
        return match_ids, match_metadata
    
    except Exception as e:
        print(f"  ✗ Erro: {e}")
        return []


def recreate_driver_if_needed(scraper):
    """
    Verifica se o driver está ativo e recria se necessário
    Retorna True se teve que recriar, False caso contrário
    """
    try:
        # Tenta uma operação simples para verificar se o driver está vivo
        _ = scraper.driver.current_url
        return False
    except Exception as e:
        print(f"\n  ⚠️ Sessão perdida: {str(e)[:50]}...")
        print(f"  🔄 Recriando driver...")
        try:
            scraper.driver.quit()
        except:
            pass
        
        # Recria o driver
        scraper.driver = scraper.setup_driver(headless=True)
        print(f"  ✓ Driver recriado")
        return True


def load_existing_data(filename):
    """Carrega dados existentes de um arquivo JSON se ele existir"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None


def get_processed_match_ids(country_data):
    """Extrai todos os IDs de jogos já processados de um país"""
    processed_ids = set()
    if country_data and 'leagues' in country_data:
        for league in country_data['leagues']:
            if 'matches' in league:
                for match in league['matches']:
                    # Tenta extrair ID de diferentes campos possíveis
                    match_id = match.get('Match_ID') or match.get('match_id')
                    if match_id:
                        processed_ids.add(match_id)
    return processed_ids


def save_country_data(filename, country_data):
    """Salva dados do país em arquivo JSON de forma atômica, rápida e segura"""
    try:
        temp_filename = f"{filename}.tmp"
        with open(temp_filename, 'w', encoding='utf-8') as f:
            json.dump(country_data, f, ensure_ascii=False, separators=(',', ':'))
        os.replace(temp_filename, filename)
        return True
    except Exception as e:
        print(f"  ⚠️ Erro ao salvar {filename}: {e}")
        return False


def process_season(scraper, league_urls, season_name, output_dir):
    """Processa todas as ligas de uma temporada específica"""
    print(f"\n{'=' * 100}")
    print(f"📅 TEMPORADA {season_name}")
    print(f"{'=' * 100}")
    print(f"Total de ligas: {len(league_urls)}")
    
    # Agrupa por país
    leagues_by_country = {}
    for url in league_urls:
        country = extract_country_from_url(url)
        league_name = extract_league_name_from_url(url)
        
        if country not in leagues_by_country:
            leagues_by_country[country] = []
        
        leagues_by_country[country].append({'url': url, 'name': league_name})
    
    print(f"\n📂 {len(leagues_by_country)} país(es) para processar:")
    for country, leagues in leagues_by_country.items():
        print(f"  • {country.upper()}: {len(leagues)} liga(s)")
    
    # Processa cada país
    for idx, (country, leagues) in enumerate(leagues_by_country.items(), 1):
        print(f"\n{'=' * 100}")
        print(f"🌎 [{idx}/{len(leagues_by_country)}] {country.upper()} - {season_name}")
        print(f"{'=' * 100}")
        
        filename = f"{output_dir}/{country}_{season_name.replace('/', '-')}.json"
        
        # Tenta carregar dados existentes
        existing_data = load_existing_data(filename)
        processed_ids = set()
        
        if existing_data:
            processed_ids = get_processed_match_ids(existing_data)
            print(f"📄 Arquivo existente encontrado: {len(processed_ids)} jogos já processados")
            print(f"   Continuando de onde parou...")
            country_data = existing_data
        else:
            print(f"📄 Iniciando novo arquivo...")
            country_data = {
                'country': country.upper(),
                'season': season_name,
                'scrape_date': datetime.now().isoformat(),
                'total_leagues': len(leagues),
                'leagues': []
            }
        
        # Processa cada liga do país
        for league in leagues:
            league_url = league['url']
            league_name = league['name']
            
            print(f"\n📂 {league_name}")
            
            # Busca se a liga já existe nos dados
            existing_league = None
            for lg in country_data['leagues']:
                if lg['name'] == league_name:
                    existing_league = lg
                    break
            
            # Se não existe, cria nova entrada
            if not existing_league:
                existing_league = {
                    'name': league_name,
                    'url': league_url,
                    'total_matches': 0,
                    'scraped_matches': 0,
                    'matches': []
                }
                country_data['leagues'].append(existing_league)
            
            # Extrai IDs já processados DESTA LIGA específica com sucesso (que já possuem odds)
            league_processed_ids = set()
            valid_matches = []
            for match in existing_league['matches']:
                match_id = match.get('Match_ID') or match.get('match_id') or match.get('Id')
                if match_id:
                    has_odds = bool(match.get('Odds_1X2_FT') or match.get('Odds_OU_FT'))
                    if has_odds:
                        league_processed_ids.add(match_id)
                        valid_matches.append(match)
                        
            existing_league['matches'] = valid_matches
            existing_league['scraped_matches'] = len(valid_matches)
            
            if league_processed_ids:
                print(f"  📄 {len(league_processed_ids)} jogos válidos com odds já salvos nesta liga")
            
            match_ids = get_match_ids_from_league(scraper, league_url)
            
            if not match_ids:
                print(f"  ⚠️  Nenhum jogo encontrado, pulando...")
                continue
            
            # Atualiza total de jogos da liga
            existing_league['total_matches'] = len(match_ids)
            
            # Filtra apenas IDs que ainda não foram processados NESTA LIGA
            new_match_ids = [mid for mid in match_ids if mid not in league_processed_ids]
            
            if not new_match_ids:
                print(f"  ✅ Liga já completa ({len(match_ids)} jogos)")
                continue
            
            print(f"  🔄 {len(new_match_ids)} novos jogos para processar (de {len(match_ids)} totais)")
            
            # Processa jogos (Suporte a Paralelismo com Pool Fixo ou Sequencial)
            workers_count = getattr(scraper, 'workers', 1)
            
            if workers_count > 1 and len(new_match_ids) > 1:
                print(f"  ⚡ Inicializando pool persistente de {workers_count} navegadores...")
                import queue
                import threading
                
                work_queue = queue.Queue()
                for mid in new_match_ids:
                    work_queue.put(mid)
                
                global_processed_counter = [0]
                save_lock = threading.Lock()
                proxy_list = []
                if scraper.proxy:
                    if os.path.exists("proxies.txt"):
                        with open("proxies.txt", "r", encoding="utf-8") as f:
                            proxy_list = [l.strip() for l in f if l.strip() and not l.startswith("#")]
                
                def cleanup_raw_html_cache(max_keep=0):
                    """Limpa arquivos HTML temporários da pasta raw_html para economizar disco"""
                    try:
                        raw_dir = "raw_html"
                        if os.path.exists(raw_dir):
                            deleted_count = 0
                            for f in os.listdir(raw_dir):
                                f_path = os.path.join(raw_dir, f)
                                if os.path.isfile(f_path):
                                    os.remove(f_path)
                                    deleted_count += 1
                            if deleted_count > 0:
                                print(f"\n  🧹 [Auto-Limpeza] {deleted_count} arquivos HTML temporários apagados de {raw_dir}/ para liberar disco.")
                    except Exception as e_clean:
                        pass

                def persistent_worker(worker_idx):
                    worker_proxy = proxy_list[worker_idx % len(proxy_list)] if proxy_list else None
                    worker_scraper = None
                    try:
                        worker_scraper = FlashScoreScraper(headless=True, use_cache=scraper.use_cache, proxy=worker_proxy)
                        # Aceita cookies uma única vez na inicialização
                        try:
                            worker_scraper.driver.get(scraper.base_url)
                            time.sleep(1)
                            worker_scraper.accept_cookies()
                        except:
                            pass
                        
                        league_ctx = f"{league_name} ({season_name})"
                        while not work_queue.empty():
                            try:
                                m_id = work_queue.get_nowait()
                            except queue.Empty:
                                break
                            
                            try:
                                match_data = worker_scraper.scrape_match(m_id, league_context=f"W{worker_idx+1} | {league_ctx}")
                                if match_data and match_data.get('Home') and match_data.get('Away'):
                                    match_data['Match_ID'] = m_id
                                    with save_lock:
                                        existing_league['matches'].append(match_data)
                                        existing_league['scraped_matches'] = len(existing_league['matches'])
                                        save_country_data(filename, country_data)
                                        processed_ids.add(m_id)
                                        global_processed_counter[0] += 1
                                        curr = len(existing_league['matches'])
                                        print(f"  [{curr:3d}/{len(match_ids)}] ✓ [W{worker_idx+1}] [{league_ctx}] {match_data.get('Home')} vs {match_data.get('Away')} [OK💾]")
                                        
                                        # Auto-limpeza a cada 500 jogos
                                        if global_processed_counter[0] % 500 == 0:
                                            cleanup_raw_html_cache()
                                else:
                                    print(f"  ✗ [W{worker_idx+1}] [{league_ctx}] Erro no jogo {m_id}")
                            except Exception as e:
                                print(f"  ✗ [W{worker_idx+1}] [{league_ctx}] Erro no jogo {m_id}: {e}")
                            finally:
                                work_queue.task_done()
                                time.sleep(0.5)
                    finally:
                        if worker_scraper:
                            try:
                                worker_scraper.close()
                            except:
                                pass

                threads = []
                for w_i in range(min(workers_count, len(new_match_ids))):
                    t = threading.Thread(target=persistent_worker, args=(w_i,))
                    t.daemon = True
                    t.start()
                    threads.append(t)
                    time.sleep(0.5)  # Pequeno espaçamento na inicialização dos navegadores
                
                # Aguarda todas as tarefas terminarem
                for t in threads:
                    t.join()
            else:
                # Modo Sequencial Tradicional (1 worker)
                league_ctx = f"{league_name} ({season_name})"
                for i, match_id in enumerate(new_match_ids, 1):
                    try:
                        recreate_driver_if_needed(scraper)
                        current_position = len(existing_league['matches']) + 1
                        print(f"  [{current_position:3d}/{len(match_ids)}] [{league_ctx}] {match_id}...", end=" ", flush=True)
                        
                        match_data = scraper.scrape_match(match_id, league_context=league_ctx)
                        
                        if match_data:
                            if not match_data.get('Home') or not match_data.get('Away'):
                                print(f"✗ Erro no jogo {match_id}")
                                continue
                            
                            match_data['Match_ID'] = match_id
                            existing_league['matches'].append(match_data)
                            existing_league['scraped_matches'] = len(existing_league['matches'])
                            
                            if save_country_data(filename, country_data):
                                print("✓💾")
                            else:
                                print("✓⚠️")
                            
                            processed_ids.add(match_id)
                        else:
                            print(f"✗ Erro no jogo {match_id}")
                            
                    except KeyboardInterrupt:
                        print("\n\n⚠️  Interrompido pelo usuário!")
                        print(f"   Progresso salvo: {len(existing_league['matches'])} jogos de {league_name}")
                        raise
                    except Exception as e:
                        print(f"✗ Erro no jogo {match_id}")
                    
                    time.sleep(1)  # Pausa entre jogos
            
            total_scraped = len(existing_league['matches'])
            print(f"  ✅ {total_scraped}/{len(match_ids)} jogos extraídos nesta liga")
        
        # Salva final do país
        save_country_data(filename, country_data)
        
        total_matches = sum(lg['scraped_matches'] for lg in country_data['leagues'])
        size_mb = os.path.getsize(filename) / (1024 * 1024)
        print(f"\n✅ {country.upper()} ({season_name}) completo: {total_matches} jogos → {filename} ({size_mb:.1f} MB)")


def scrape_from_config(config_file="ligas_config.csv", headless=True, proxy=None, workers=1):
    """
    Executa o scraping baseado nas ligas marcadas com 'S' no arquivo CSV de configuração.
    """
    if not os.path.exists(config_file):
        print(f"❌ Arquivo de configuração '{config_file}' não encontrado!")
        return
    
    # Lê o CSV com pandas (tudo como string para evitar erros de tipo)
    try:
        df = pd.read_csv(config_file, sep=';', encoding='utf-8-sig', dtype=str)
    except:
        df = pd.read_csv(config_file, sep=',', encoding='utf-8', dtype=str)
    
    # Filtra apenas onde a coluna 'baixar' está marcada como 'S' ou 'SIM' ou 'TRUE'
    df['baixar_clean'] = df['baixar'].fillna('').astype(str).str.strip().str.upper()
    df_selecionadas = df[df['baixar_clean'].isin(['S', 'SIM', 'TRUE', '1', 'Y', 'YES'])].copy()
    
    # Converte todas as colunas para string
    for col in ['pais', 'liga_temporada', 'temporada', 'url']:
        if col in df_selecionadas.columns:
            df_selecionadas[col] = df_selecionadas[col].astype(object)
    
    print("=" * 100)
    print("🚀 FLASHSCORE SCRAPER - MODO CSV CONFIG")
    print("=" * 100)
    print(f"📄 Arquivo de configuração: {config_file}")
    print(f"📊 Total de ligas no arquivo: {len(df)}")
    print(f"🎯 Ligas selecionadas para baixar ('S'): {len(df_selecionadas)}")
    if workers > 1:
        print(f"⚡ MODO PARALELO ATIVADO: {workers} workers simultâneos")
    if proxy:
        print(f"🛡️ Modo Proxy ATIVADO: {proxy}")
    else:
        print(f"🌐 Conexão Direta (IP Original)")
    
    if len(df_selecionadas) == 0:
        print("\n⚠️  Nenhuma liga marcada com 'S' na coluna 'baixar'!")
        print("   Abra o arquivo 'ligas_config.csv' no Excel/Bloco de Notas e marque 'S' nas ligas que deseja baixar.")
        print("=" * 100)
        return
    
    # Garante que colunas faltantes ou em branco sejam preenchidas automaticamente pela URL
    for idx, row in df_selecionadas.iterrows():
        url = str(row['url']).strip()
        if pd.isna(row.get('pais')) or str(row.get('pais')).strip() == '' or str(row.get('pais')) == 'nan':
            df_selecionadas.at[idx, 'pais'] = extract_country_from_url(url)
        if pd.isna(row.get('liga_temporada')) or str(row.get('liga_temporada')).strip() == '' or str(row.get('liga_temporada')) == 'nan':
            df_selecionadas.at[idx, 'liga_temporada'] = extract_league_name_from_url(url)
        if pd.isna(row.get('temporada')) or str(row.get('temporada')).strip() == '' or str(row.get('temporada')) == 'nan':
            df_selecionadas.at[idx, 'temporada'] = extract_season_from_url(url)

    print("\n📋 Ligas que serão processadas:")
    for idx, row in df_selecionadas.iterrows():
        print(f"  • [{str(row['pais']).upper()}] {row['liga_temporada']} ({row['temporada']})")
    
    output_dir = "jogos_passados"
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n" + "=" * 100)
    print("Iniciando em 3 segundos...")
    time.sleep(3)
    
    scraper = FlashScoreScraper(headless=headless, proxy=proxy)
    scraper.workers = workers
    
    try:
        start_time = datetime.now()
        
        # Agrupa por temporada e executa
        for season_name, group in df_selecionadas.groupby('temporada', sort=False):
            links = group['url'].tolist()
            print("\n\n" + "🟢" * 50)
            print(f"PROCESSANDO TEMPORADA: {season_name} ({len(links)} liga(s))")
            print("🟢" * 50)
            process_season(scraper, links, str(season_name), output_dir)
            
        end_time = datetime.now()
        duration = end_time - start_time
        
        print("\n\n" + "=" * 100)
        print("🎉 SCRAPING FINALIZADO COM SUCESSO!")
        print(f"⏱️  Duração total: {duration}")
        print("=" * 100)
        
        # 1. Converte automaticamente os JSONs em CSVs finais
        print("\n📊 Gerando CSVs estruturados...")
        try:
            from generate_df_jogos_passados import process_all_historical_games
            process_all_historical_games(input_dir=output_dir, output_dir="data_jogos_passados")
        except Exception as e:
            print(f"⚠️ Erro ao gerar CSV: {e}")

        # 2. Compacta e dispara download automático se estiver no Google Colab
        try:
            import google.colab
            from google.colab import files
            import shutil
            
            print("\n📥 Criando arquivo compactado para download automático...")
            shutil.make_archive("flashscore_dados_completos", "zip", ".", "jogos_passados")
            # Adiciona os CSVs no zip se existirem
            if os.path.exists("data_jogos_passados"):
                import zipfile
                with zipfile.ZipFile("flashscore_dados_completos.zip", "a") as zipf:
                    for root, _, filenames in os.walk("data_jogos_passados"):
                        for f in filenames:
                            zipf.write(os.path.join(root, f), arcname=os.path.join("data_jogos_passados", f))
            
            print("🚀 Disparando download automático para o seu computador...")
            files.download("flashscore_dados_completos.zip")
            print("✓ Download iniciado no seu navegador!")
        except ImportError:
            pass  # Não está no Colab (ambiente local Windows)
        except Exception as e:
            print(f"⚠️ Falha no download automático do Colab: {e}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  INTERROMPIDO PELO USUÁRIO (Ctrl+C)")
        print("✅ Todo o progresso já foi salvo no diretório jogos_passados/")
    finally:
        scraper.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FlashScore Scraper")
    parser.add_argument("--visual", action="store_true", help="Abrir Chrome visível na tela")
    parser.add_argument("--proxy", nargs="?", const="proxies.txt", default=None,
                        help="Ativar proxy (ex: --proxy ou --proxy proxies.txt ou --proxy ip:porta:user:pass)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Número de workers/jogos simultâneos (ex: --workers 5)")
    args = parser.parse_args()
    
    # Executa usando o ligas_config.csv (com ou sem proxy e suporte a workers)
    scrape_from_config(config_file="ligas_config.csv", headless=not args.visual, proxy=args.proxy, workers=args.workers)
