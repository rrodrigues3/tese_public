#!/bin/bash

# Ativar modo estrito para melhor depuração
set -e

# 1. Git pull na pasta /data/rafael/vm_isa
echo ">>> Atualizando repositório vm_isa..."
cd /data/rafael/vm_isa
git pull

# Remover o ficheiro results.xlsx
echo ">>> Removendo results.xlsx de vm_isa..."
rm -f results.xlsx

# Adicionar, commitar e fazer push
git add .
git commit -m "Atualização automática: remoção de results.xlsx"
git push

# 2. Git pull na pasta /data/rafael/tese_public
echo ">>> Atualizando repositório tese_public..."
cd /data/rafael/tese_public
git pull

# Remover detections_output e results.csv
echo ">>> Removendo detections_output e results.csv de tese_public..."
rm -rf detections_output
rm -f results.csv

# Adicionar, commitar e fazer push
git add .
git commit -m "Atualização automática: remoção de detections_output e results.csv"
git push

echo ">>> Script concluído com sucesso!"
