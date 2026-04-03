# サンプルデータで分析テスト

サンプルデータを使って家計分析の動作確認を行います。

## 実行内容

以下のPythonコードを実行して、分析結果を表示します：

```python
import sys
sys.path.insert(0, '/Volumes/tkg SSD/household-budget-app')

from modules import DataLoader, BudgetAnalyzer, BudgetVisualizer

# データ読み込み
loader = DataLoader()
df = loader.load_csv('/Volumes/tkg SSD/household-budget-app/data/sample_budget.csv')

# 分析
analyzer = BudgetAnalyzer(df, loader.get_ideal_ratios())
stats = analyzer.statistics_summary()

# 結果表示
print(f"=== 家計分析結果 ===")
print(f"データ件数: {len(df)} 件")
print(f"期間: {df['日付'].min().strftime('%Y-%m-%d')} 〜 {df['日付'].max().strftime('%Y-%m-%d')}")
print(f"総支出: ¥{stats['total']:,.0f}")
print(f"月平均: ¥{stats['average_monthly']:,.0f}")
print(f"トレンド: {stats['trend']['trend']}")
print()
print("=== カテゴリ別支出 ===")
for cat, amount in analyzer.spending_by_category().items():
    ratio = amount / stats['total'] * 100
    print(f"  {cat}: ¥{amount:,.0f} ({ratio:.1f}%)")
```

## 出力例

```
=== 家計分析結果 ===
データ件数: 44 件
期間: 2024-01-05 〜 2024-03-30
総支出: ¥284,950
月平均: ¥94,983
トレンド: 減少傾向

=== カテゴリ別支出 ===
  住居費: ¥85,000 (29.8%)
  光熱費: ¥62,900 (22.1%)
  食費: ¥57,550 (20.2%)
  ...
```
