"""税金計算モジュール"""
import yaml
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime


class TaxCalculator:
    """各種税金の計算を行うクラス

    日本の各種税金（所得税、住民税、自動車税、固定資産税など）を計算する。
    設定ファイルから税率を読み込み、存在しない場合はデフォルト値を使用する。
    """

    def __init__(self, config_path: str = "config/assets.yaml"):
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: str) -> dict:
        """設定ファイル読み込み"""
        path = Path(config_path)
        if not path.is_absolute():
            path = Path(__file__).parent.parent / config_path

        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                loaded_config = yaml.safe_load(f) or {}
                default_config = self._get_default_config()
                for key, value in default_config.items():
                    if key not in loaded_config:
                        loaded_config[key] = value
                return loaded_config
        return self._get_default_config()

    def _get_default_config(self) -> dict:
        """デフォルト設定（フォールバック）

        2024年度の日本の税率に基づくデフォルト値を返す。
        """
        return {
            # 自動車税（排気量別）- 令和元年10月以降登録車
            'vehicle_tax_rates': [
                {'cc_max': 1000, 'tax': 25000},
                {'cc_max': 1500, 'tax': 30500},
                {'cc_max': 2000, 'tax': 36000},
                {'cc_max': 2500, 'tax': 43500},
                {'cc_max': 3000, 'tax': 50000},
                {'cc_max': 3500, 'tax': 57000},
                {'cc_max': 4000, 'tax': 65500},
                {'cc_max': 4500, 'tax': 75500},
                {'cc_max': 6000, 'tax': 87000},
            ],

            # 重量税（車両重量別、2年分）
            'weight_tax_rates': [
                {'kg_max': 500, 'tax': 8200},
                {'kg_max': 1000, 'tax': 16400},
                {'kg_max': 1500, 'tax': 24600},
                {'kg_max': 2000, 'tax': 32800},
                {'kg_max': 2500, 'tax': 41000},
                {'kg_max': 3000, 'tax': 49200},
            ],

            # 所得税率（累進課税）
            'income_tax_brackets': [
                {'max': 1950000, 'rate': 0.05, 'deduction': 0},
                {'max': 3300000, 'rate': 0.10, 'deduction': 97500},
                {'max': 6950000, 'rate': 0.20, 'deduction': 427500},
                {'max': 9000000, 'rate': 0.23, 'deduction': 636000},
                {'max': 18000000, 'rate': 0.33, 'deduction': 1536000},
                {'max': 40000000, 'rate': 0.40, 'deduction': 2796000},
                {'max': float('inf'), 'rate': 0.45, 'deduction': 4796000},
            ],

            # 住民税率（一律10%）
            'resident_tax_rate': 0.10,

            # 基礎控除
            'basic_deduction': 480000,

            # 固定資産税率（標準税率）
            'property_tax_rate': 0.014,

            # 都市計画税率（上限）
            'city_planning_tax_rate': 0.003,

            # 復興特別所得税率
            'reconstruction_tax_rate': 0.021,

            # 税金カレンダー（支払月）
            'tax_calendar': {
                'vehicle_tax': [5],
                'resident_tax': [6, 8, 10, 1],
                'property_tax': [4, 7, 12, 2],
            },

            # 軽自動車税
            'light_vehicle_tax': 10800,

            # 自賠責保険（24ヶ月）
            'compulsory_insurance_24m': 17650,
        }

    # === 車両関連税 ===

    def calculate_vehicle_tax(self, cc: int) -> int:
        """自動車税計算（排気量から）

        Args:
            cc: 排気量（cc）

        Returns:
            年間自動車税額
        """
        if cc <= 660:
            return self.config.get('light_vehicle_tax', 10800)

        for rate in self.config.get('vehicle_tax_rates', []):
            if cc <= rate['cc_max']:
                return rate['tax']
        return 110000  # 6000cc超

    def calculate_weight_tax(self, weight_kg: int, years: int = 2) -> int:
        """重量税計算（車両重量から）

        Args:
            weight_kg: 車両重量（kg）
            years: 車検期間（年、通常2年）

        Returns:
            重量税額
        """
        for rate in self.config.get('weight_tax_rates', []):
            if weight_kg <= rate['kg_max']:
                return rate['tax'] * (years // 2)
        return 49200 * (years // 2)  # 3000kg超

    def calculate_total_vehicle_taxes(self, vehicles_df: pd.DataFrame) -> pd.DataFrame:
        """全車両の税金を計算

        Args:
            vehicles_df: 車両データ（columns: name, cc, weight_kg）

        Returns:
            税金計算結果（columns: name, vehicle_tax, weight_tax, total）
        """
        results = []

        for _, row in vehicles_df.iterrows():
            name = row.get('name', row.get('車名', ''))
            cc = int(row.get('cc', row.get('排気量', 0)))
            weight_kg = int(row.get('weight_kg', row.get('車両重量', 0)))

            vehicle_tax = self.calculate_vehicle_tax(cc)
            weight_tax = self.calculate_weight_tax(weight_kg)

            results.append({
                '車名': name,
                '排気量': cc,
                '車両重量': weight_kg,
                '自動車税': vehicle_tax,
                '重量税': weight_tax,
                '合計': vehicle_tax + weight_tax
            })

        return pd.DataFrame(results)

    # === 所得税・住民税 ===

    def calculate_income_tax(self, taxable_income: int) -> int:
        """所得税計算（課税所得から）

        Args:
            taxable_income: 課税所得

        Returns:
            所得税額
        """
        if taxable_income <= 0:
            return 0

        brackets = self.config.get('income_tax_brackets', [])

        for bracket in brackets:
            if taxable_income <= bracket['max']:
                return int(taxable_income * bracket['rate'] - bracket['deduction'])

        last = brackets[-1] if brackets else {'rate': 0.45, 'deduction': 4796000}
        return int(taxable_income * last['rate'] - last['deduction'])

    def calculate_resident_tax(self, taxable_income: int) -> int:
        """住民税計算（課税所得から）

        Args:
            taxable_income: 課税所得

        Returns:
            住民税額（均等割5000円を含む）
        """
        if taxable_income <= 0:
            return 0

        rate = self.config.get('resident_tax_rate', 0.10)
        income_based = int(taxable_income * rate)
        flat_rate = 5000  # 均等割（市区町村民税3500円 + 都道府県民税1500円）

        return income_based + flat_rate

    def calculate_taxable_income(self, annual_income: int, deductions: Optional[dict] = None) -> int:
        """課税所得計算

        Args:
            annual_income: 年収（給与収入）
            deductions: 追加控除（医療費控除、生命保険料控除など）

        Returns:
            課税所得
        """
        basic = self.config.get('basic_deduction', 480000)
        total_deductions = basic

        if deductions:
            total_deductions += sum(deductions.values())

        # 給与所得控除
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

        taxable = annual_income - employment_deduction - total_deductions
        return max(0, int(taxable))

    def calculate_total_tax(self, annual_income: int, deductions: Optional[dict] = None) -> dict:
        """総合税金計算

        Args:
            annual_income: 年収
            deductions: 追加控除

        Returns:
            税金計算結果の辞書
        """
        taxable = self.calculate_taxable_income(annual_income, deductions)
        income_tax = self.calculate_income_tax(taxable)
        resident_tax = self.calculate_resident_tax(taxable)

        reconstruction_rate = self.config.get('reconstruction_tax_rate', 0.021)
        reconstruction_tax = int(income_tax * reconstruction_rate)

        total_tax = income_tax + reconstruction_tax + resident_tax
        take_home = annual_income - total_tax

        return {
            '年収': annual_income,
            '課税所得': taxable,
            '所得税': income_tax,
            '復興特別所得税': reconstruction_tax,
            '住民税': resident_tax,
            '税金合計': total_tax,
            '手取り': take_home,
            '実効税率': round(total_tax / annual_income * 100, 1) if annual_income > 0 else 0
        }

    def calculate_social_insurance(self, monthly_salary: int) -> dict:
        """社会保険料の概算

        Args:
            monthly_salary: 月額給与（標準報酬月額の概算として使用）

        Returns:
            社会保険料の内訳
        """
        health_rate = 0.05  # 健康保険（本人負担分、約5%）
        pension_rate = 0.0915  # 厚生年金（本人負担分、9.15%）
        employment_rate = 0.006  # 雇用保険（本人負担分、0.6%）

        health = int(monthly_salary * health_rate)
        pension = int(monthly_salary * pension_rate)
        employment = int(monthly_salary * employment_rate)

        return {
            '健康保険': health,
            '厚生年金': pension,
            '雇用保険': employment,
            '社会保険合計': health + pension + employment,
            '年間社会保険': (health + pension + employment) * 12
        }

    # === 固定資産税 ===

    def estimate_property_tax(self, assessed_value: int, include_city_planning: bool = True) -> int:
        """固定資産税の概算

        Args:
            assessed_value: 固定資産税評価額
            include_city_planning: 都市計画税を含めるか

        Returns:
            固定資産税額
        """
        property_rate = self.config.get('property_tax_rate', 0.014)
        property_tax = int(assessed_value * property_rate)

        if include_city_planning:
            city_rate = self.config.get('city_planning_tax_rate', 0.003)
            city_tax = int(assessed_value * city_rate)
            return property_tax + city_tax

        return property_tax

    def estimate_property_tax_with_exemption(self, land_value: int, building_value: int,
                                              land_area: float, is_residential: bool = True) -> dict:
        """住宅用地の特例を考慮した固定資産税計算

        Args:
            land_value: 土地評価額
            building_value: 建物評価額
            land_area: 土地面積（平方メートル）
            is_residential: 住宅用地かどうか

        Returns:
            税額の内訳
        """
        property_rate = self.config.get('property_tax_rate', 0.014)
        city_rate = self.config.get('city_planning_tax_rate', 0.003)

        if is_residential:
            if land_area <= 200:
                land_reduction = 1/6
                city_land_reduction = 1/3
            else:
                small_portion = 200 / land_area
                large_portion = 1 - small_portion
                land_reduction = small_portion * (1/6) + large_portion * (1/3)
                city_land_reduction = small_portion * (1/3) + large_portion * (2/3)
        else:
            land_reduction = 1
            city_land_reduction = 1

        land_property_tax = int(land_value * land_reduction * property_rate)
        building_property_tax = int(building_value * property_rate)

        land_city_tax = int(land_value * city_land_reduction * city_rate)
        building_city_tax = int(building_value * city_rate)

        return {
            '土地固定資産税': land_property_tax,
            '建物固定資産税': building_property_tax,
            '土地都市計画税': land_city_tax,
            '建物都市計画税': building_city_tax,
            '固定資産税合計': land_property_tax + building_property_tax,
            '都市計画税合計': land_city_tax + building_city_tax,
            '総合計': land_property_tax + building_property_tax + land_city_tax + building_city_tax
        }

    # === 税金カレンダー ===

    def generate_tax_calendar(self, vehicles_df: Optional[pd.DataFrame] = None,
                               annual_income: int = 0,
                               property_value: int = 0) -> pd.DataFrame:
        """年間税金カレンダー生成

        Args:
            vehicles_df: 車両データ
            annual_income: 年収
            property_value: 固定資産評価額

        Returns:
            月別税金支払いスケジュール
        """
        events = []

        # 自動車税（5月）
        if vehicles_df is not None and len(vehicles_df) > 0:
            vehicle_total = 0
            for _, row in vehicles_df.iterrows():
                cc = int(row.get('cc', row.get('排気量', 0)))
                vehicle_total += self.calculate_vehicle_tax(cc)

            events.append({
                '月': 5,
                '税目': '自動車税',
                '金額': vehicle_total,
                '備考': f'{len(vehicles_df)}台分'
            })

        # 住民税（6,8,10,1月 - 普通徴収の場合）
        if annual_income > 0:
            result = self.calculate_total_tax(annual_income)
            resident_tax = result['住民税']

            first_payment = resident_tax - (resident_tax // 4) * 3
            subsequent = resident_tax // 4

            payment_months = [6, 8, 10, 1]
            for i, month in enumerate(payment_months):
                amount = first_payment if i == 0 else subsequent
                events.append({
                    '月': month,
                    '税目': '住民税',
                    '金額': amount,
                    '備考': f'普通徴収 第{i+1}期'
                })

        # 固定資産税（4,7,12,2月）
        if property_value > 0:
            prop_tax = self.estimate_property_tax(property_value)

            first_payment = prop_tax - (prop_tax // 4) * 3
            subsequent = prop_tax // 4

            payment_months = [4, 7, 12, 2]
            for i, month in enumerate(payment_months):
                amount = first_payment if i == 0 else subsequent
                events.append({
                    '月': month,
                    '税目': '固定資産税',
                    '金額': amount,
                    '備考': f'第{i+1}期'
                })

        df = pd.DataFrame(events)
        if len(df) > 0:
            month_order = {1: 13, 2: 14}
            df['sort_key'] = df['月'].map(lambda x: month_order.get(x, x))
            df = df.sort_values('sort_key').drop('sort_key', axis=1)
            df = df.reset_index(drop=True)

        return df

    def generate_annual_summary(self, vehicles_df: Optional[pd.DataFrame] = None,
                                 annual_income: int = 0,
                                 property_value: int = 0,
                                 monthly_salary: int = 0) -> dict:
        """年間税金サマリー生成

        Args:
            vehicles_df: 車両データ
            annual_income: 年収
            property_value: 固定資産評価額
            monthly_salary: 月額給与（社会保険料計算用）

        Returns:
            年間税金サマリー
        """
        summary = {
            '所得税': 0,
            '復興特別所得税': 0,
            '住民税': 0,
            '自動車税': 0,
            '重量税': 0,
            '固定資産税': 0,
            '社会保険料': 0,
        }

        if annual_income > 0:
            tax_result = self.calculate_total_tax(annual_income)
            summary['所得税'] = tax_result['所得税']
            summary['復興特別所得税'] = tax_result['復興特別所得税']
            summary['住民税'] = tax_result['住民税']

        if vehicles_df is not None and len(vehicles_df) > 0:
            vehicle_taxes = self.calculate_total_vehicle_taxes(vehicles_df)
            summary['自動車税'] = vehicle_taxes['自動車税'].sum()
            summary['重量税'] = vehicle_taxes['重量税'].sum() // 2

        if property_value > 0:
            summary['固定資産税'] = self.estimate_property_tax(property_value)

        if monthly_salary > 0:
            insurance = self.calculate_social_insurance(monthly_salary)
            summary['社会保険料'] = insurance['年間社会保険']

        summary['年間合計'] = sum(summary.values())

        return summary

    # === 追加メソッド ===

    def get_marginal_tax_rate(self, taxable_income: int) -> float:
        """課税所得に対する限界税率を返す

        Args:
            taxable_income: 課税所得

        Returns:
            限界所得税率
        """
        if taxable_income <= 0:
            return 0.0

        brackets = self.config.get('income_tax_brackets', [])
        for bracket in brackets:
            if taxable_income <= bracket['max']:
                return bracket['rate']

        return brackets[-1]['rate'] if brackets else 0.45

    def calculate_medical_deduction(self, total_medical: int, insurance_reimbursement: int,
                                     total_income: int, self_medication: int = 0) -> dict:
        """医療費控除の計算

        Args:
            total_medical: 医療費総額
            insurance_reimbursement: 保険補填額
            total_income: 総所得金額
            self_medication: セルフメディケーション対象額

        Returns:
            医療費控除の計算結果
        """
        # total_income は年収。総所得金額（給与所得）を算出
        employment_ded = self.calculate_taxable_income(total_income) + self.config.get('basic_deduction', 480000)
        # 給与所得 = 年収 - 給与所得控除（基礎控除は含まない）
        total_income_after_emp = total_income - (total_income - employment_ded - self.config.get('basic_deduction', 480000))
        # より正確: 給与所得控除を逆算
        if total_income <= 1625000:
            emp_ded = 550000
        elif total_income <= 1800000:
            emp_ded = int(total_income * 0.4 - 100000)
        elif total_income <= 3600000:
            emp_ded = int(total_income * 0.3 + 80000)
        elif total_income <= 6600000:
            emp_ded = int(total_income * 0.2 + 440000)
        elif total_income <= 8500000:
            emp_ded = int(total_income * 0.1 + 1100000)
        else:
            emp_ded = 1950000
        shotoku = total_income - emp_ded  # 総所得金額（給与所得）

        threshold = 100000 if shotoku >= 2000000 else int(shotoku * 0.05)
        net_medical = total_medical - insurance_reimbursement
        standard_deduction = max(0, net_medical - threshold)
        standard_deduction = min(standard_deduction, 2000000)

        self_med_deduction = max(0, self_medication - 12000)
        self_med_deduction = min(self_med_deduction, 88000)

        taxable_income = self.calculate_taxable_income(total_income)
        marginal_rate = self.get_marginal_tax_rate(taxable_income)
        combined_rate = marginal_rate + 0.10

        standard_savings = int(standard_deduction * combined_rate)
        self_med_savings = int(self_med_deduction * combined_rate)

        recommended = 'standard' if standard_savings >= self_med_savings else 'self_medication'

        threshold_remaining = max(0, threshold - net_medical)

        return {
            'standard': {'deduction': standard_deduction, 'savings': standard_savings},
            'self_medication': {'deduction': self_med_deduction, 'savings': self_med_savings},
            'recommended': recommended,
            'threshold_remaining': threshold_remaining
        }

    def calculate_furusato_limit(self, annual_income: int, deductions: dict = None) -> dict:
        """ふるさと納税の控除上限額を計算

        Args:
            annual_income: 年収
            deductions: 追加控除

        Returns:
            ふるさと納税上限額の計算結果
        """
        taxable_income = self.calculate_taxable_income(annual_income, deductions)
        rate = self.get_marginal_tax_rate(taxable_income)
        resident_tax = taxable_income * 0.10
        limit = int(resident_tax * 0.20 / (0.90 - rate * 1.021) + 2000)

        return {
            'limit': limit,
            'self_pay': 2000,
            'effective_limit': limit - 2000,
            'tax_rate': rate,
            'taxable_income': taxable_income
        }

    def calculate_furusato_savings(self, donation: int, annual_income: int,
                                    deductions: dict = None, one_stop: bool = True) -> dict:
        """ふるさと納税の税金軽減額を計算

        Args:
            donation: 寄付金額
            annual_income: 年収
            deductions: 追加控除
            one_stop: ワンストップ特例を利用するか

        Returns:
            税金軽減額の内訳
        """
        base = donation - 2000
        taxable_income = self.calculate_taxable_income(annual_income, deductions)
        rate = self.get_marginal_tax_rate(taxable_income)

        income_tax_portion = int(base * rate * 1.021)
        resident_tax_basic = int(base * 0.10)
        resident_tax_special = int(base * (0.90 - rate * 1.021))
        special_cap = int(taxable_income * 0.10 * 0.20)
        resident_tax_special = min(resident_tax_special, special_cap)

        if one_stop:
            total_savings = resident_tax_basic + resident_tax_special + income_tax_portion
            income_tax_refund = 0
            resident_tax_reduction = total_savings
        else:
            income_tax_refund = income_tax_portion
            resident_tax_reduction = resident_tax_basic + resident_tax_special
            total_savings = income_tax_refund + resident_tax_reduction

        return {
            'income_tax_refund': income_tax_refund,
            'resident_tax_reduction': resident_tax_reduction,
            'total_savings': total_savings,
            'effective_cost': donation - total_savings,
            'one_stop': one_stop
        }

    @staticmethod
    def extract_medical_expenses(expenses_df: pd.DataFrame, year: int = None) -> dict:
        """家計簿データから医療費を抽出

        Args:
            expenses_df: 支出データ（カテゴリ、日付、金額カラムを含む）
            year: 対象年（Noneの場合は全期間）

        Returns:
            医療費の集計結果
        """
        filtered = expenses_df[expenses_df['カテゴリ'] == '医療費'].copy()

        if year is not None:
            filtered = filtered[pd.to_datetime(filtered['日付']).dt.year == year]

        total = int(filtered['金額'].sum()) if len(filtered) > 0 else 0
        count = len(filtered)

        monthly = {}
        if len(filtered) > 0:
            dates = pd.to_datetime(filtered['日付'])
            for _, row in filtered.iterrows():
                dt = pd.to_datetime(row['日付'])
                month_str = dt.strftime('%Y-%m')
                monthly[month_str] = monthly.get(month_str, 0) + int(row['金額'])

        return {
            'total': total,
            'count': count,
            'monthly': monthly,
            'entries': filtered
        }
