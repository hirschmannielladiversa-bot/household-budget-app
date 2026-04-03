"""家計分析モジュール"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime


class BudgetAnalyzer:
    """家計データの分析"""

    def __init__(self, df: pd.DataFrame, ideal_ratios: Optional[Dict[str, float]] = None):
        self.df = df.copy()
        if not self.df.empty and '日付' in self.df.columns:
            if '年月' not in self.df.columns:
                self.df['年月'] = pd.to_datetime(self.df['日付']).dt.to_period('M')
            if '曜日' not in self.df.columns:
                self.df['曜日'] = pd.to_datetime(self.df['日付']).dt.day_name()
        self.ideal_ratios = ideal_ratios or {}

    def total_spending(self) -> float:
        """総支出を計算"""
        return self.df['金額'].sum()

    def spending_by_category(self) -> pd.Series:
        """カテゴリ別支出"""
        return self.df.groupby('カテゴリ')['金額'].sum().sort_values(ascending=False)

    def spending_ratio_by_category(self) -> pd.Series:
        """カテゴリ別支出比率"""
        total = self.total_spending()
        if total == 0:
            return pd.Series(dtype=float)
        return self.spending_by_category() / total

    def monthly_spending(self) -> pd.Series:
        """月別支出"""
        return self.df.groupby('年月')['金額'].sum()

    def monthly_spending_by_category(self) -> pd.DataFrame:
        """月別・カテゴリ別支出"""
        pivot = self.df.pivot_table(
            values='金額',
            index='年月',
            columns='カテゴリ',
            aggfunc='sum',
            fill_value=0
        )
        return pivot

    def daily_spending(self) -> pd.Series:
        """日別支出"""
        return self.df.groupby(self.df['日付'].dt.date)['金額'].sum()

    def weekday_spending(self) -> pd.Series:
        """曜日別支出"""
        weekday_order = ['Monday', 'Tuesday', 'Wednesday',
                         'Thursday', 'Friday', 'Saturday', 'Sunday']

        # 曜日カラムがない場合は日付から生成
        if '曜日' not in self.df.columns:
            if '日付' in self.df.columns:
                weekday = self.df['日付'].dt.day_name()
                spending = self.df.groupby(weekday)['金額'].sum()
            else:
                return pd.Series(index=weekday_order, data=0)
        else:
            spending = self.df.groupby('曜日')['金額'].sum()

        return spending.reindex(weekday_order).fillna(0)

    def weekday_category_heatmap(self) -> pd.DataFrame:
        """曜日×カテゴリのヒートマップデータ"""
        weekday_order = ['Monday', 'Tuesday', 'Wednesday',
                         'Thursday', 'Friday', 'Saturday', 'Sunday']

        # 曜日カラムがない場合は日付から生成
        df_copy = self.df.copy()
        if '曜日' not in df_copy.columns:
            if '日付' in df_copy.columns:
                df_copy['曜日'] = df_copy['日付'].dt.day_name()
            else:
                # 空のDataFrameを返す
                return pd.DataFrame(index=weekday_order)

        pivot = df_copy.pivot_table(
            values='金額',
            index='曜日',
            columns='カテゴリ',
            aggfunc='sum',
            fill_value=0
        )
        return pivot.reindex(weekday_order).fillna(0)

    def average_monthly_spending(self) -> float:
        """月平均支出"""
        monthly = self.monthly_spending()
        if len(monthly) == 0:
            return 0.0
        return monthly.mean()

    def average_monthly_by_category(self) -> pd.Series:
        """カテゴリ別月平均支出"""
        monthly_cat = self.monthly_spending_by_category()
        if len(monthly_cat) == 0:
            return pd.Series(dtype=float)
        return monthly_cat.mean()

    def spending_trend(self) -> Dict[str, Any]:
        """支出トレンド分析"""
        monthly = self.monthly_spending()
        if len(monthly) < 2:
            return {'trend': 'データ不足', 'change': 0.0}

        first_month = monthly.iloc[0]
        last_month = monthly.iloc[-1]

        if first_month == 0:
            change_rate = 0.0
        else:
            change_rate = (last_month - first_month) / first_month * 100

        if change_rate > 5:
            trend = '増加傾向'
        elif change_rate < -5:
            trend = '減少傾向'
        else:
            trend = '横ばい'

        return {
            'trend': trend,
            'change': change_rate,
            'first_month': first_month,
            'last_month': last_month
        }

    def category_trend(self, category: str) -> Dict[str, Any]:
        """特定カテゴリのトレンド分析"""
        cat_df = self.df[self.df['カテゴリ'] == category]
        if len(cat_df) == 0:
            return {'trend': 'データなし', 'change': 0.0}

        monthly = cat_df.groupby('年月')['金額'].sum()
        if len(monthly) < 2:
            return {'trend': 'データ不足', 'change': 0.0}

        first_month = monthly.iloc[0]
        last_month = monthly.iloc[-1]

        if first_month == 0:
            change_rate = 0.0
        else:
            change_rate = (last_month - first_month) / first_month * 100

        if change_rate > 10:
            trend = '増加'
        elif change_rate < -10:
            trend = '減少'
        else:
            trend = '安定'

        return {
            'trend': trend,
            'change': change_rate,
            'monthly_data': monthly
        }

    def compare_with_ideal(self) -> pd.DataFrame:
        """理想比率との比較"""
        actual = self.spending_ratio_by_category()
        comparison = pd.DataFrame({
            '実際': actual,
            '理想': pd.Series(self.ideal_ratios)
        }).fillna(0)

        comparison['差分'] = comparison['実際'] - comparison['理想']
        comparison['評価'] = comparison['差分'].apply(
            lambda x: '超過' if x > 0.02 else ('節約' if x < -0.02 else '適正')
        )

        return comparison.sort_values('差分', ascending=False)

    def top_expenses(self, n: int = 5) -> pd.DataFrame:
        """高額支出TOP N"""
        return self.df.nlargest(n, '金額')[['日付', 'カテゴリ', '金額', 'メモ']]

    def statistics_summary(self) -> Dict[str, Any]:
        """統計サマリー"""
        return {
            'total': self.total_spending(),
            'average_monthly': self.average_monthly_spending(),
            'num_transactions': len(self.df),
            'date_range': {
                'start': self.df['日付'].min(),
                'end': self.df['日付'].max()
            },
            'top_category': self.spending_by_category().idxmax() if len(self.df) > 0 else None,
            'trend': self.spending_trend()
        }

    def monthly_summary(self, year_month) -> Dict[str, Any]:
        """特定月のサマリー"""
        month_df = self.df[self.df['年月'] == year_month]
        if len(month_df) == 0:
            return {'error': '該当するデータがありません'}

        return {
            'total': month_df['金額'].sum(),
            'by_category': month_df.groupby('カテゴリ')['金額'].sum().to_dict(),
            'num_transactions': len(month_df),
            'average_per_day': month_df['金額'].sum() / month_df['日付'].dt.day.max(),
            'top_expense': month_df.nlargest(1, '金額').to_dict('records')[0] if len(month_df) > 0 else None
        }

    def anomaly_detection(self, threshold: float = 2.0) -> pd.DataFrame:
        """異常支出の検出（標準偏差の threshold 倍を超える支出）"""
        by_category = self.df.groupby('カテゴリ')['金額']
        mean = by_category.transform('mean')
        std = by_category.transform('std').fillna(0)

        # 標準偏差が0の場合は異常なし
        z_score = np.where(std > 0, (self.df['金額'] - mean) / std, 0)
        self.df['z_score'] = z_score

        anomalies = self.df[self.df['z_score'] > threshold].copy()
        return anomalies[['日付', 'カテゴリ', '金額', 'メモ', 'z_score']].sort_values('z_score', ascending=False)

    def savings_potential(self, income: float) -> Dict[str, Any]:
        """貯蓄ポテンシャル分析"""
        monthly_avg = self.average_monthly_spending()
        monthly_savings = income - monthly_avg
        savings_rate = monthly_savings / income if income > 0 else 0

        # カテゴリ別の節約余地
        comparison = self.compare_with_ideal()
        overspending = comparison[comparison['評価'] == '超過']

        potential_savings = 0
        reduction_targets = []
        for cat, row in overspending.iterrows():
            excess = row['差分'] * self.total_spending()
            potential_savings += excess
            reduction_targets.append({
                'category': cat,
                'excess_ratio': row['差分'],
                'excess_amount': excess
            })

        return {
            'current_monthly_spending': monthly_avg,
            'current_monthly_savings': monthly_savings,
            'current_savings_rate': savings_rate,
            'potential_additional_savings': potential_savings,
            'reduction_targets': reduction_targets
        }
