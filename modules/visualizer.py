"""グラフ生成モジュール"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional, Dict, List

# 日本語曜日マッピング
WEEKDAY_JA = {
    'Monday': '月曜日',
    'Tuesday': '火曜日',
    'Wednesday': '水曜日',
    'Thursday': '木曜日',
    'Friday': '金曜日',
    'Saturday': '土曜日',
    'Sunday': '日曜日'
}


class BudgetVisualizer:
    """家計データの可視化"""

    # カラーパレット
    COLORS = px.colors.qualitative.Set3

    def __init__(self, analyzer):
        self.analyzer = analyzer

    def category_pie_chart(self, title: str = "カテゴリ別支出割合") -> go.Figure:
        """カテゴリ別円グラフ"""
        spending = self.analyzer.spending_by_category()

        fig = px.pie(
            values=spending.values,
            names=spending.index,
            title=title,
            color_discrete_sequence=self.COLORS,
            hole=0.4
        )

        fig.update_traces(
            textposition='outside',
            textinfo='label+percent',
            hovertemplate='%{label}<br>¥%{value:,.0f}<br>%{percent}<extra></extra>',
            textfont_size=11,
            pull=[0.02] * len(spending),
        )

        fig.update_layout(
            font=dict(size=11),
            height=500,
            margin=dict(t=40, b=20, l=20, r=20),
            legend=dict(
                orientation='v',
                yanchor='middle',
                y=0.5,
                xanchor='left',
                x=1.05,
                font=dict(size=10),
            ),
            uniformtext_minsize=9,
            uniformtext_mode='hide',
        )

        return fig

    def monthly_bar_chart(self, title: str = "月別支出推移") -> go.Figure:
        """月別棒グラフ"""
        monthly = self.analyzer.monthly_spending()

        fig = px.bar(
            x=[str(m) for m in monthly.index],
            y=monthly.values,
            title=title,
            labels={'x': '月', 'y': '支出額（円）'},
            color_discrete_sequence=['#4ECDC4']
        )

        fig.update_traces(
            hovertemplate='%{x}<br>¥%{y:,.0f}<extra></extra>'
        )

        fig.update_layout(
            xaxis_title='月',
            yaxis_title='支出額（円）',
            yaxis_tickformat=',',
            bargap=0.3
        )

        return fig

    def category_trend_line(self, categories: Optional[List[str]] = None,
                            title: str = "カテゴリ別月次トレンド") -> go.Figure:
        """カテゴリ別折れ線グラフ"""
        monthly_cat = self.analyzer.monthly_spending_by_category()

        if categories:
            monthly_cat = monthly_cat[[c for c in categories if c in monthly_cat.columns]]

        fig = go.Figure()

        for i, category in enumerate(monthly_cat.columns):
            fig.add_trace(go.Scatter(
                x=[str(m) for m in monthly_cat.index],
                y=monthly_cat[category],
                mode='lines+markers',
                name=category,
                line=dict(color=self.COLORS[i % len(self.COLORS)]),
                hovertemplate=f'{category}<br>%{{x}}<br>¥%{{y:,.0f}}<extra></extra>'
            ))

        fig.update_layout(
            title=title,
            xaxis_title='月',
            yaxis_title='支出額（円）',
            yaxis_tickformat=',',
            legend=dict(orientation='h', yanchor='bottom', y=-0.3),
            hovermode='x unified'
        )

        return fig

    def weekday_category_heatmap(self, title: str = "曜日×カテゴリ 支出パターン") -> go.Figure:
        """曜日×カテゴリのヒートマップ"""
        heatmap_data = self.analyzer.weekday_category_heatmap()

        # 日本語曜日に変換
        heatmap_data.index = [WEEKDAY_JA.get(d, d) for d in heatmap_data.index]

        fig = px.imshow(
            heatmap_data.values,
            x=heatmap_data.columns,
            y=heatmap_data.index,
            title=title,
            labels=dict(x='カテゴリ', y='曜日', color='支出額'),
            color_continuous_scale='Blues',
            aspect='auto'
        )

        fig.update_traces(
            hovertemplate='%{y}<br>%{x}<br>¥%{z:,.0f}<extra></extra>'
        )

        fig.update_layout(
            xaxis_tickangle=-45
        )

        return fig

    def comparison_bar_chart(self, title: str = "実際の支出 vs 理想比率") -> go.Figure:
        """理想比率との比較棒グラフ"""
        comparison = self.analyzer.compare_with_ideal()

        fig = go.Figure()

        fig.add_trace(go.Bar(
            name='実際',
            x=comparison.index,
            y=comparison['実際'] * 100,
            marker_color='#FF6B6B',
            hovertemplate='%{x}<br>実際: %{y:.1f}%<extra></extra>'
        ))

        fig.add_trace(go.Bar(
            name='理想',
            x=comparison.index,
            y=comparison['理想'] * 100,
            marker_color='#4ECDC4',
            hovertemplate='%{x}<br>理想: %{y:.1f}%<extra></extra>'
        ))

        fig.update_layout(
            title=title,
            xaxis_title='カテゴリ',
            yaxis_title='支出比率（%）',
            barmode='group',
            xaxis_tickangle=-45,
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        return fig

    def daily_spending_line(self, title: str = "日別支出推移") -> go.Figure:
        """日別支出折れ線グラフ"""
        daily = self.analyzer.daily_spending()

        fig = px.line(
            x=daily.index,
            y=daily.values,
            title=title,
            labels={'x': '日付', 'y': '支出額（円）'}
        )

        fig.add_trace(go.Scatter(
            x=daily.index,
            y=[daily.mean()] * len(daily),
            mode='lines',
            name='平均',
            line=dict(dash='dash', color='red')
        ))

        fig.update_traces(
            hovertemplate='%{x}<br>¥%{y:,.0f}<extra></extra>'
        )

        fig.update_layout(
            yaxis_tickformat=',',
            showlegend=True
        )

        return fig

    def spending_gauge(self, budget: float, title: str = "予算達成状況") -> go.Figure:
        """予算ゲージチャート"""
        total = self.analyzer.total_spending()
        percentage = (total / budget * 100) if budget > 0 else 0

        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=total,
            delta={'reference': budget, 'relative': False, 'valueformat': ',.0f'},
            number={'prefix': "¥", 'valueformat': ',.0f'},
            title={'text': title},
            gauge={
                'axis': {'range': [0, budget * 1.2], 'tickformat': ',.0f'},
                'bar': {'color': "#FF6B6B" if percentage > 100 else "#4ECDC4"},
                'steps': [
                    {'range': [0, budget * 0.5], 'color': "#E8F5E9"},
                    {'range': [budget * 0.5, budget * 0.8], 'color': "#FFF9C4"},
                    {'range': [budget * 0.8, budget], 'color': "#FFCCBC"},
                    {'range': [budget, budget * 1.2], 'color': "#FFCDD2"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': budget
                }
            }
        ))

        return fig

    def top_expenses_table(self, n: int = 10) -> go.Figure:
        """高額支出テーブル"""
        top = self.analyzer.top_expenses(n)

        fig = go.Figure(data=[go.Table(
            header=dict(
                values=['日付', 'カテゴリ', '金額', 'メモ'],
                fill_color='#4ECDC4',
                font=dict(color='black', size=14),
                align='left'
            ),
            cells=dict(
                values=[
                    top['日付'].dt.strftime('%Y-%m-%d'),
                    top['カテゴリ'],
                    top['金額'].apply(lambda x: f'¥{x:,.0f}'),
                    top['メモ']
                ],
                fill_color='lavender',
                align='left',
                font=dict(color='black', size=12)
            )
        )])

        fig.update_layout(
            title='高額支出一覧',
            margin=dict(l=0, r=0, t=40, b=0)
        )

        return fig

    def monthly_category_stacked(self, title: str = "月別カテゴリ構成") -> go.Figure:
        """月別カテゴリ積み上げ棒グラフ"""
        monthly_cat = self.analyzer.monthly_spending_by_category()

        fig = go.Figure()

        for i, category in enumerate(monthly_cat.columns):
            fig.add_trace(go.Bar(
                name=category,
                x=[str(m) for m in monthly_cat.index],
                y=monthly_cat[category],
                marker_color=self.COLORS[i % len(self.COLORS)],
                hovertemplate=f'{category}<br>%{{x}}<br>¥%{{y:,.0f}}<extra></extra>'
            ))

        fig.update_layout(
            title=title,
            xaxis_title='月',
            yaxis_title='支出額（円）',
            yaxis_tickformat=',',
            barmode='stack',
            legend=dict(orientation='h', yanchor='bottom', y=-0.3)
        )

        return fig

    def dashboard(self, budget: Optional[float] = None) -> go.Figure:
        """ダッシュボード（複合グラフ）"""
        fig = make_subplots(
            rows=2, cols=2,
            specs=[[{"type": "pie"}, {"type": "bar"}],
                   [{"type": "scatter"}, {"type": "heatmap"}]],
            subplot_titles=("カテゴリ別支出", "月別支出推移",
                          "日別支出推移", "曜日×カテゴリパターン")
        )

        # 円グラフ
        spending = self.analyzer.spending_by_category()
        fig.add_trace(
            go.Pie(labels=spending.index, values=spending.values,
                   hole=0.4, showlegend=False),
            row=1, col=1
        )

        # 月別棒グラフ
        monthly = self.analyzer.monthly_spending()
        fig.add_trace(
            go.Bar(x=[str(m) for m in monthly.index], y=monthly.values,
                   marker_color='#4ECDC4', showlegend=False),
            row=1, col=2
        )

        # 日別折れ線グラフ
        daily = self.analyzer.daily_spending()
        fig.add_trace(
            go.Scatter(x=daily.index, y=daily.values,
                      mode='lines', line=dict(color='#FF6B6B'), showlegend=False),
            row=2, col=1
        )

        # ヒートマップ
        heatmap_data = self.analyzer.weekday_category_heatmap()
        heatmap_data.index = [WEEKDAY_JA.get(d, d) for d in heatmap_data.index]
        fig.add_trace(
            go.Heatmap(z=heatmap_data.values, x=heatmap_data.columns,
                      y=heatmap_data.index, colorscale='Blues', showlegend=False),
            row=2, col=2
        )

        fig.update_layout(
            height=800,
            title_text="家計ダッシュボード",
            showlegend=False
        )

        return fig
