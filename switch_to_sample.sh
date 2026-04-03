#!/bin/bash
# サンプルデータに切り替えるスクリプト
# 使い方: ./switch_to_sample.sh
# 戻す時: ./switch_to_real.sh

APP_DIR="/Volumes/tkg SSD/household-budget-app"
DATA_DIR="$APP_DIR/data"
BACKUP_DIR="$APP_DIR/data/real_backup"
SAMPLE_DIR="$APP_DIR/data/sample"

echo "=== 実データをバックアップして、サンプルデータに切り替えます ==="

mkdir -p "$BACKUP_DIR"

for f in saved_expenses.csv transactions.csv accounts.csv sample_assets.csv \
         sample_budget.csv year_end_adjustment.yaml user_profile.json \
         user_settings.json chat_history.json history_summary.json .salt; do
    if [ -f "$DATA_DIR/$f" ]; then
        cp "$DATA_DIR/$f" "$BACKUP_DIR/$f"
        echo "  バックアップ: $f"
    fi
done

for f in "$SAMPLE_DIR"/*; do
    fname=$(basename "$f")
    cp "$f" "$DATA_DIR/$fname"
    echo "  サンプル適用: $fname"
done
# .salt もコピー
if [ -f "$SAMPLE_DIR/.salt" ]; then
    cp "$SAMPLE_DIR/.salt" "$DATA_DIR/.salt"
    echo "  サンプル適用: .salt"
fi

echo ""
echo "=== 切り替え完了！Streamlitを再起動してください ==="
