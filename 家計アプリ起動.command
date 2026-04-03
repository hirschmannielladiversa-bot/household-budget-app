#!/bin/bash
# 家計管理ダッシュボード 起動スクリプト
# このファイルをダブルクリックするとアプリが起動します

cd "$(dirname "$0")"

echo "🏠 家計管理ダッシュボードを起動しています..."
echo ""

# Python確認
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3が見つかりません。"
    echo "   https://www.python.org/downloads/ からインストールしてください。"
    echo ""
    echo "何かキーを押すと閉じます..."
    read -n 1
    exit 1
fi

# 依存関係チェック（streamlitがなければインストール）
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "📦 必要なパッケージをインストールしています（初回のみ）..."
    pip3 install -r requirements.txt
    echo ""
fi

echo "✅ ブラウザで自動的に開きます。"
echo "   開かない場合は http://localhost:8501 にアクセスしてください。"
echo ""
echo "⏹  終了するにはこのウィンドウを閉じるか、Ctrl+C を押してください。"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 -m streamlit run app.py
