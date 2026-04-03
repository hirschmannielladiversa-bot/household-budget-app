"""資産・税金可視化モジュール"""

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Optional, List
from datetime import datetime


class AssetVisualizer:
    """資産と税金のグラフを生成するクラス"""

    COLORS = px.colors.qualitative.Set3

    def __init__(self, asset_manager=None, tax_calculator=None):
        self.asset_manager = asset_manager
        self.tax_calculator = tax_calculator

    # === 資産グラフ ===

    def asset_composition_pie(self, title: str = "資産構成") -> go.Figure:
        """資産構成円グラフ（ドーナツチャート）"""
        if self.asset_manager is None or self.asset_manager.df is None:
            return self._empty_figure("資産データがありません")

        composition = self.asset_manager.asset_composition()
        if len(composition) == 0:
            return self._empty_figure("資産データがありません")

        # 日本語名に変換
        labels = [self.asset_manager.get_asset_type_name(t) for t in composition.index]
        icons = [self.asset_manager.get_asset_type_icon(t) for t in composition.index]
        labels_with_icons = [f"{icon} {label}" for icon, label in zip(icons, labels)]

        fig = px.pie(
            values=composition.values,
            names=labels_with_icons,
            title=title,
            color_discrete_sequence=self.COLORS,
            hole=0.4
        )

        fig.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='%{label}<br>¥%{value:,.0f}<br>%{percent}<extra></extra>'
        )

        fig.update_layout(
            font=dict(size=12),
            legend=dict(orientation='h', yanchor='bottom', y=-0.2)
        )

        return fig

    def asset_type_bar(self, title: str = "資産種別") -> go.Figure:
        """資産種別棒グラフ（水平）"""
        if self.asset_manager is None or self.asset_manager.df is None:
            return self._empty_figure("資産データがありません")

        composition = self.asset_manager.asset_composition()
        if len(composition) == 0:
            return self._empty_figure("資産データがありません")

        # 日本語名とアイコンを取得
        labels = [self.asset_manager.get_asset_type_name(t) for t in composition.index]
        icons = [self.asset_manager.get_asset_type_icon(t) for t in composition.index]
        labels_with_icons = [f"{icon} {label}" for icon, label in zip(icons, labels)]

        fig = go.Figure(go.Bar(
            x=composition.values,
            y=labels_with_icons,
            orientation='h',
            marker_color=[self.COLORS[i % len(self.COLORS)] for i in range(len(composition))],
            hovertemplate='%{y}<br>¥%{x:,.0f}<extra></extra>'
        ))

        fig.update_layout(
            title=title,
            xaxis_title='評価額（円）',
            xaxis_tickformat=',',
            yaxis_title='',
            bargap=0.3
        )

        return fig

    def asset_value_trend(self, history_df: Optional[pd.DataFrame] = None,
                          title: str = "資産価値推移") -> go.Figure:
        """資産価値推移グラフ（簿価 vs 時価）"""
        if self.asset_manager is None or self.asset_manager.df is None:
            return self._empty_figure("資産データがありません")

        # 履歴データがない場合は現在の値のみ表示
        if history_df is None:
            df = self.asset_manager.df
            if len(df) == 0:
                return self._empty_figure("資産データがありません")

            # 現在の簿価と時価を計算
            today = datetime.now()
            book_values = []
            market_values = []

            for _, asset in df.iterrows():
                book_value = self.asset_manager.calculate_current_book_value(asset)
                market_value = asset.get('current_value', 0)
                book_values.append(book_value)
                market_values.append(market_value)

            total_book = sum(book_values)
            total_market = sum(market_values)

            fig = go.Figure()

            fig.add_trace(go.Bar(
                name='簿価',
                x=['現在'],
                y=[total_book],
                marker_color='#4ECDC4',
                hovertemplate='簿価<br>¥%{y:,.0f}<extra></extra>'
            ))

            fig.add_trace(go.Bar(
                name='時価',
                x=['現在'],
                y=[total_market],
                marker_color='#FF6B6B',
                hovertemplate='時価<br>¥%{y:,.0f}<extra></extra>'
            ))

            fig.update_layout(
                title=title,
                xaxis_title='',
                yaxis_title='評価額（円）',
                yaxis_tickformat=',',
                barmode='group',
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
            )

            return fig

        # 履歴データがある場合は折れ線グラフ
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=history_df['date'],
            y=history_df['book_value'],
            mode='lines+markers',
            name='簿価',
            line=dict(color='#4ECDC4'),
            hovertemplate='%{x}<br>簿価: ¥%{y:,.0f}<extra></extra>'
        ))

        fig.add_trace(go.Scatter(
            x=history_df['date'],
            y=history_df['market_value'],
            mode='lines+markers',
            name='時価',
            line=dict(color='#FF6B6B'),
            hovertemplate='%{x}<br>時価: ¥%{y:,.0f}<extra></extra>'
        ))

        fig.update_layout(
            title=title,
            xaxis_title='日付',
            yaxis_title='評価額（円）',
            yaxis_tickformat=',',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            hovermode='x unified'
        )

        return fig

    def depreciation_chart(self, asset_id: Optional[str] = None,
                           title: str = "減価償却推移") -> go.Figure:
        """減価償却グラフ（エリアチャート）"""
        if self.asset_manager is None or self.asset_manager.df is None:
            return self._empty_figure("資産データがありません")

        df = self.asset_manager.df

        # 特定の資産または減価償却対象資産を選択
        if asset_id:
            asset_df = df[df['asset_id'] == asset_id]
            if len(asset_df) == 0:
                return self._empty_figure(f"資産ID '{asset_id}' が見つかりません")
            asset = asset_df.iloc[0]
        else:
            # 減価償却対象資産（車両または不動産）を選択
            depreciable = df[df['asset_type'].isin(['vehicle', 'real_estate'])]
            if len(depreciable) == 0:
                return self._empty_figure("減価償却対象資産がありません")
            asset = depreciable.iloc[0]

        # 減価償却計算
        purchase_price = asset.get('purchase_price', 0)
        purchase_date = asset.get('purchase_date')
        asset_type = asset.get('asset_type', '')
        asset_name = asset.get('name', '資産')

        if pd.isna(purchase_date) or purchase_price == 0:
            return self._empty_figure("購入情報が不足しています")

        # 耐用年数を取得
        type_config = self.asset_manager.config.get('asset_types', {}).get(asset_type, {})
        if asset_type == 'real_estate':
            details = asset.get('details_parsed', {})
            structure = details.get('type', 'RC')
            years_config = type_config.get('depreciation_years', {})
            useful_life = years_config.get(structure, 47)
        else:
            useful_life = type_config.get('depreciation_years', 6)

        # 残存価格
        residual_value = purchase_price * 0.1
        annual_depreciation = (purchase_price - residual_value) / useful_life

        # 年度ごとの簿価を計算
        years = list(range(useful_life + 1))
        book_values = []
        for year in years:
            value = max(purchase_price - annual_depreciation * year, residual_value)
            book_values.append(value)

        # 累計減価償却額
        accumulated_depreciation = [purchase_price - bv for bv in book_values]

        fig = go.Figure()

        # 簿価エリア
        fig.add_trace(go.Scatter(
            x=years,
            y=book_values,
            fill='tozeroy',
            name='簿価',
            line=dict(color='#4ECDC4'),
            hovertemplate='%{x}年目<br>簿価: ¥%{y:,.0f}<extra></extra>'
        ))

        # 累計減価償却額（線のみ）
        fig.add_trace(go.Scatter(
            x=years,
            y=accumulated_depreciation,
            mode='lines',
            name='累計減価償却額',
            line=dict(color='#FF6B6B', dash='dash'),
            hovertemplate='%{x}年目<br>累計償却: ¥%{y:,.0f}<extra></extra>'
        ))

        # 購入価格と残存価格の参照線
        fig.add_hline(y=purchase_price, line_dash="dot", line_color="gray",
                      annotation_text=f"取得価格: ¥{purchase_price:,.0f}")
        fig.add_hline(y=residual_value, line_dash="dot", line_color="orange",
                      annotation_text=f"残存価格: ¥{residual_value:,.0f}")

        fig.update_layout(
            title=f"{title}（{asset_name}）",
            xaxis_title='経過年数',
            yaxis_title='金額（円）',
            yaxis_tickformat=',',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        return fig

    # === 税金グラフ ===

    def tax_breakdown_pie(self, tax_result: dict, title: str = "税金内訳") -> go.Figure:
        """税金内訳円グラフ"""
        if not tax_result:
            return self._empty_figure("税金データがありません")

        # 表示する項目を抽出
        display_items = {
            '所得税': tax_result.get('所得税', 0),
            '復興特別所得税': tax_result.get('復興特別所得税', 0),
            '住民税': tax_result.get('住民税', 0),
        }

        # オプション項目
        if '自動車税' in tax_result and tax_result['自動車税'] > 0:
            display_items['自動車税'] = tax_result['自動車税']
        if '固定資産税' in tax_result and tax_result['固定資産税'] > 0:
            display_items['固定資産税'] = tax_result['固定資産税']
        if '重量税' in tax_result and tax_result['重量税'] > 0:
            display_items['重量税'] = tax_result['重量税']

        # ゼロの項目を除外
        display_items = {k: v for k, v in display_items.items() if v > 0}

        if not display_items:
            return self._empty_figure("税金データがありません")

        fig = px.pie(
            values=list(display_items.values()),
            names=list(display_items.keys()),
            title=title,
            color_discrete_sequence=self.COLORS,
            hole=0.4
        )

        fig.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='%{label}<br>¥%{value:,.0f}<br>%{percent}<extra></extra>'
        )

        fig.update_layout(
            font=dict(size=12),
            legend=dict(orientation='h', yanchor='bottom', y=-0.2)
        )

        return fig

    def income_vs_tax_waterfall(self, annual_income: int, tax_result: dict,
                                 title: str = "収入から手取りまで") -> go.Figure:
        """収入 -> 控除 -> 税金 -> 手取りウォーターフォールチャート"""
        if annual_income <= 0:
            return self._empty_figure("年収を入力してください")

        # 給与所得控除を計算
        if annual_income <= 1625000:
            employment_deduction = 550000
        elif annual_income <= 1800000:
            employment_deduction = int(annual_income * 0.4 - 100000)
        elif annual_income <= 3600000:
            employment_deduction = int(annual_income * 0.3 + 80000)
        elif annual_income <= 6600000:
            employment_deduction = int(annual_income * 0.2 + 440000)
        elif annual_income <= 8500000:
            employment_deduction = int(annual_income * 0.1 + 1100000)
        else:
            employment_deduction = 1950000

        basic_deduction = 480000

        income_tax = tax_result.get('所得税', 0)
        reconstruction_tax = tax_result.get('復興特別所得税', 0)
        resident_tax = tax_result.get('住民税', 0)
        take_home = tax_result.get('手取り', annual_income - income_tax - reconstruction_tax - resident_tax)

        fig = go.Figure(go.Waterfall(
            name="収支",
            orientation="v",
            measure=["absolute", "relative", "relative", "relative", "relative", "relative", "total"],
            x=["年収", "給与所得控除", "基礎控除", "所得税", "復興税", "住民税", "手取り"],
            y=[annual_income, -employment_deduction, -basic_deduction,
               -income_tax, -reconstruction_tax, -resident_tax, take_home],
            textposition="outside",
            text=[f"¥{annual_income:,.0f}",
                  f"-¥{employment_deduction:,.0f}",
                  f"-¥{basic_deduction:,.0f}",
                  f"-¥{income_tax:,.0f}",
                  f"-¥{reconstruction_tax:,.0f}",
                  f"-¥{resident_tax:,.0f}",
                  f"¥{take_home:,.0f}"],
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            increasing={"marker": {"color": "#4ECDC4"}},
            decreasing={"marker": {"color": "#FF6B6B"}},
            totals={"marker": {"color": "#45B7D1"}}
        ))

        fig.update_layout(
            title=title,
            yaxis_title='金額（円）',
            yaxis_tickformat=',',
            showlegend=False
        )

        return fig

    def tax_calendar_chart(self, calendar_df: pd.DataFrame,
                           title: str = "年間税金カレンダー") -> go.Figure:
        """年間税金カレンダー（月別積み上げ棒グラフ）"""
        if calendar_df is None or len(calendar_df) == 0:
            return self._empty_figure("税金スケジュールがありません")

        # 月別・税目別に集計
        pivot = calendar_df.pivot_table(
            index='月', columns='税目', values='金額',
            aggfunc='sum', fill_value=0
        )

        # 全ての月を含める（1-12月）
        all_months = list(range(1, 13))
        pivot = pivot.reindex(all_months, fill_value=0)

        fig = go.Figure()

        for i, tax_type in enumerate(pivot.columns):
            fig.add_trace(go.Bar(
                name=tax_type,
                x=[f'{m}月' for m in pivot.index],
                y=pivot[tax_type],
                marker_color=self.COLORS[i % len(self.COLORS)],
                hovertemplate=f'{tax_type}<br>%{{x}}<br>¥%{{y:,.0f}}<extra></extra>'
            ))

        fig.update_layout(
            title=title,
            xaxis_title='月',
            yaxis_title='金額（円）',
            yaxis_tickformat=',',
            barmode='stack',
            legend=dict(orientation='h', yanchor='bottom', y=-0.3)
        )

        return fig

    def tax_rate_comparison(self, incomes: Optional[List[int]] = None,
                            title: str = "年収別実効税率") -> go.Figure:
        """年収別税率比較折れ線グラフ"""
        if self.tax_calculator is None:
            return self._empty_figure("税金計算機が設定されていません")

        if incomes is None:
            incomes = [3000000, 4000000, 5000000, 6000000, 7000000,
                      8000000, 10000000, 12000000, 15000000]

        effective_rates = []
        income_taxes = []
        resident_taxes = []

        for income in incomes:
            result = self.tax_calculator.calculate_total_tax(income)
            effective_rates.append(result['実効税率'])
            income_taxes.append(result['所得税'] + result['復興特別所得税'])
            resident_taxes.append(result['住民税'])

        income_labels = [f'{inc//10000}万' for inc in incomes]

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # 税額（棒グラフ）
        fig.add_trace(go.Bar(
            name='所得税+復興税',
            x=income_labels,
            y=income_taxes,
            marker_color='#FF6B6B',
            hovertemplate='%{x}<br>所得税: ¥%{y:,.0f}<extra></extra>'
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            name='住民税',
            x=income_labels,
            y=resident_taxes,
            marker_color='#4ECDC4',
            hovertemplate='%{x}<br>住民税: ¥%{y:,.0f}<extra></extra>'
        ), secondary_y=False)

        # 実効税率（折れ線グラフ）
        fig.add_trace(go.Scatter(
            name='実効税率',
            x=income_labels,
            y=effective_rates,
            mode='lines+markers',
            line=dict(color='#45B7D1', width=3),
            marker=dict(size=10),
            hovertemplate='%{x}<br>実効税率: %{y:.1f}%<extra></extra>'
        ), secondary_y=True)

        fig.update_layout(
            title=title,
            barmode='stack',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        fig.update_xaxes(title_text='年収')
        fig.update_yaxes(title_text='税額（円）', tickformat=',', secondary_y=False)
        fig.update_yaxes(title_text='実効税率（%）', secondary_y=True)

        return fig

    # === ダッシュボード ===

    def asset_dashboard(self, title: str = "資産ダッシュボード") -> go.Figure:
        """資産ダッシュボード（4パネル）"""
        fig = make_subplots(
            rows=2, cols=2,
            specs=[[{"type": "pie"}, {"type": "bar"}],
                   [{"type": "bar"}, {"type": "scatter"}]],
            subplot_titles=("資産構成", "資産種別", "個別資産", "簿価 vs 時価")
        )

        if self.asset_manager is None or self.asset_manager.df is None or len(self.asset_manager.df) == 0:
            fig.update_layout(title=title, height=800)
            fig.add_annotation(
                text="資産データがありません",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=20)
            )
            return fig

        df = self.asset_manager.df
        composition = self.asset_manager.asset_composition()

        # 1. 資産構成円グラフ
        labels = [self.asset_manager.get_asset_type_name(t) for t in composition.index]
        fig.add_trace(
            go.Pie(labels=labels, values=composition.values,
                   hole=0.4, showlegend=False),
            row=1, col=1
        )

        # 2. 資産種別棒グラフ
        icons = [self.asset_manager.get_asset_type_icon(t) for t in composition.index]
        labels_with_icons = [f"{icon} {label}" for icon, label in zip(icons, labels)]
        fig.add_trace(
            go.Bar(x=composition.values, y=labels_with_icons,
                   orientation='h', marker_color='#4ECDC4', showlegend=False),
            row=1, col=2
        )

        # 3. 個別資産棒グラフ
        fig.add_trace(
            go.Bar(x=df['name'], y=df['current_value'],
                   marker_color=[self.COLORS[i % len(self.COLORS)] for i in range(len(df))],
                   showlegend=False),
            row=2, col=1
        )

        # 4. 簿価 vs 時価散布図
        book_values = [self.asset_manager.calculate_current_book_value(row) for _, row in df.iterrows()]
        market_values = df['current_value'].tolist()

        fig.add_trace(
            go.Scatter(x=book_values, y=market_values,
                      mode='markers+text', text=df['name'],
                      textposition='top center',
                      marker=dict(size=12, color=self.COLORS[0]),
                      showlegend=False),
            row=2, col=2
        )

        # 対角線（簿価=時価）
        max_val = max(max(book_values), max(market_values)) * 1.1
        fig.add_trace(
            go.Scatter(x=[0, max_val], y=[0, max_val],
                      mode='lines', line=dict(dash='dash', color='gray'),
                      showlegend=False),
            row=2, col=2
        )

        fig.update_layout(
            title=title,
            height=800,
            showlegend=False
        )

        # 軸ラベル
        fig.update_xaxes(tickformat=',', row=1, col=2)
        fig.update_yaxes(tickformat=',', row=2, col=1)
        fig.update_xaxes(title_text='簿価（円）', tickformat=',', row=2, col=2)
        fig.update_yaxes(title_text='時価（円）', tickformat=',', row=2, col=2)

        return fig

    def tax_dashboard(self, annual_income: int, title: str = "税金ダッシュボード") -> go.Figure:
        """税金ダッシュボード（4パネル）"""
        fig = make_subplots(
            rows=2, cols=2,
            specs=[[{"type": "pie"}, {"type": "bar"}],
                   [{"type": "waterfall"}, {"type": "scatter"}]],
            subplot_titles=("税金内訳", "月別支払い", "収入→手取り", "年収別税率")
        )

        if self.tax_calculator is None:
            fig.update_layout(title=title, height=800)
            fig.add_annotation(
                text="税金計算機が設定されていません",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=20)
            )
            return fig

        tax_result = self.tax_calculator.calculate_total_tax(annual_income)

        # 1. 税金内訳円グラフ
        tax_items = {
            '所得税': tax_result.get('所得税', 0),
            '復興税': tax_result.get('復興特別所得税', 0),
            '住民税': tax_result.get('住民税', 0),
        }
        tax_items = {k: v for k, v in tax_items.items() if v > 0}

        if tax_items:
            fig.add_trace(
                go.Pie(labels=list(tax_items.keys()), values=list(tax_items.values()),
                       hole=0.4, showlegend=False),
                row=1, col=1
            )

        # 2. 月別支払い棒グラフ
        calendar_df = self.tax_calculator.generate_tax_calendar(annual_income=annual_income)
        if len(calendar_df) > 0:
            monthly_totals = calendar_df.groupby('月')['金額'].sum()
            all_months = list(range(1, 13))
            monthly_totals = monthly_totals.reindex(all_months, fill_value=0)

            fig.add_trace(
                go.Bar(x=[f'{m}月' for m in monthly_totals.index],
                       y=monthly_totals.values,
                       marker_color='#4ECDC4', showlegend=False),
                row=1, col=2
            )

        # 3. ウォーターフォール（簡易版）
        take_home = tax_result.get('手取り', 0)
        total_tax = tax_result.get('税金合計', 0)

        fig.add_trace(
            go.Bar(x=['年収', '税金', '手取り'],
                   y=[annual_income, -total_tax, take_home],
                   marker_color=['#4ECDC4', '#FF6B6B', '#45B7D1'],
                   showlegend=False),
            row=2, col=1
        )

        # 4. 年収別税率折れ線
        incomes = [3000000, 5000000, 7000000, 10000000, 15000000]
        rates = []
        for inc in incomes:
            result = self.tax_calculator.calculate_total_tax(inc)
            rates.append(result['実効税率'])

        fig.add_trace(
            go.Scatter(x=[f'{inc//10000}万' for inc in incomes],
                      y=rates, mode='lines+markers',
                      line=dict(color='#45B7D1', width=2),
                      marker=dict(size=8),
                      showlegend=False),
            row=2, col=2
        )

        # 現在の年収をマーク
        current_rate = tax_result['実効税率']
        fig.add_trace(
            go.Scatter(x=[f'{annual_income//10000}万'],
                      y=[current_rate], mode='markers',
                      marker=dict(size=15, color='#FF6B6B', symbol='star'),
                      showlegend=False),
            row=2, col=2
        )

        fig.update_layout(
            title=title,
            height=800,
            showlegend=False
        )

        # 軸ラベル
        fig.update_yaxes(tickformat=',', row=1, col=2)
        fig.update_yaxes(tickformat=',', row=2, col=1)
        fig.update_yaxes(title_text='実効税率（%）', row=2, col=2)

        return fig

    # === ユーティリティ ===

    def _empty_figure(self, message: str = "データがありません") -> go.Figure:
        """空のFigureを生成（メッセージ付き）"""
        fig = go.Figure()
        fig.add_annotation(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(
            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False)
        )
        return fig
