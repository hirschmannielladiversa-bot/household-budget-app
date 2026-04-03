#!/bin/bash
# 実データに戻すスクリプト
# 使い方: ./switch_to_real.sh

APP_DIR="/Volumes/tkg SSD/household-budget-app"
DATA_DIR="$APP_DIR/data"
BACKUP_DIR="$APP_DIR/data/real_backup"

echo "=== 実データに戻します ==="

if [ ! -d "$BACKUP_DIR" ]; then
    echo "エラー: バックアップが見つかりません ($BACKUP_DIR)"
    exit 1
fi

for f in "$BACKUP_DIR"/*; do
    fname=$(basename "$f")
    cp "$f" "$DATA_DIR/$fname"
    echo "  復元: $fname"
done
# .salt も復元
if [ -f "$BACKUP_DIR/.salt" ]; then
    cp "$BACKUP_DIR/.salt" "$DATA_DIR/.salt"
    echo "  復元: .salt"
fi

echo ""
echo "=== 復元完了！Streamlitを再起動してください ==="
