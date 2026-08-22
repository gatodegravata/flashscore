#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script rápido para consolidar todas as partes de Parquet geradas em um arquivo Parquet e CSV Final.
"""

import os
import sys
import pandas as pd

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

output_dir = sys.argv[1] if len(sys.argv) > 1 else "dataset_completo"
checkpoints_dir = os.path.join(output_dir, "checkpoints")
final_dir = os.path.join(output_dir, "consolidado_final")
os.makedirs(final_dir, exist_ok=True)

print("=" * 80)
print(f"🏆 CONSOLIDADOR FINAL DE PARTIDAS ({output_dir})")
print("=" * 80)

parquet_parts = [
    os.path.join(checkpoints_dir, f)
    for f in sorted(os.listdir(checkpoints_dir))
    if f.startswith("part_") and f.endswith(".parquet")
]

if not parquet_parts:
    print(f"⚠️ Nenhuma parte 'part_*.parquet' encontrada em {checkpoints_dir}")
    sys.exit(0)

print(f"📂 Combinando {len(parquet_parts)} partes parciais...")
dfs = []
for p in parquet_parts:
    print(f"  • Lendo {os.path.basename(p)}...")
    dfs.append(pd.read_parquet(p))

df_final = pd.concat(dfs, ignore_index=True)

id_col = 'Match_ID' if 'Match_ID' in df_final.columns else 'Id'
total_antes = len(df_final)
df_final = df_final.drop_duplicates(subset=[id_col])
total_depois = len(df_final)

if total_antes != total_depois:
    print(f"🧹 Desduplicação: {total_antes - total_depois} duplicatas removidas.")

final_parquet = os.path.join(final_dir, "jogos_consolidados_completo.parquet")
final_csv = os.path.join(final_dir, "jogos_consolidados_completo.csv")

print(f"\n💾 Gravando Parquet Final ({len(df_final):,} partidas)...")
df_final.to_parquet(final_parquet, index=False)
print(f"  ✓ Salvo: {final_parquet}")

print(f"\n💾 Gravando CSV Final ({len(df_final):,} partidas)...")
df_final.to_csv(final_csv, index=False, encoding='utf-8')
print(f"  ✓ Salvo: {final_csv}")

print("\n" + "=" * 80)
print(f"🎉 SUCESSO TOTAL! {len(df_final):,} PARTIDAS CONSOLIDADAS!")
print("=" * 80)
