"""年末調整計算モジュール"""
import yaml
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class YearEndAdjustment:
    """年末調整の計算を行うクラス"""

    # 給与所得控除の速算表（2024年以降）
    SALARY_DEDUCTION_TABLE = [
        (1625000, 0.4, 0, 550000),        # 162.5万以下: 55万円
        (1800000, 0.3, 80000, None),       # 180万以下: 収入×40%-10万
        (3600000, 0.2, 180000, None),      # 360万以下: 収入×30%+8万
        (6600000, 0.1, 540000, None),      # 660万以下: 収入×20%+44万
        (8500000, 0.05, 1100000, None),    # 850万以下: 収入×10%+110万
        (float('inf'), 0, 1950000, 1950000) # 850万超: 195万円（上限）
    ]

    # 所得税率表
    INCOME_TAX_BRACKETS = [
        (1950000, 0.05, 0),
        (3300000, 0.10, 97500),
        (6950000, 0.20, 427500),
        (9000000, 0.23, 636000),
        (18000000, 0.33, 1536000),
        (40000000, 0.40, 2796000),
        (float('inf'), 0.45, 4796000),
    ]

    # 基礎控除額（所得2400万円以下）
    BASIC_DEDUCTION = 480000

    def __init__(self, year: int = None, config_path: str = None, data_dir: str = None):
        """初期化

        Args:
            year: 対象年度（デフォルト: 今年）
            config_path: 設定ファイルパス
            data_dir: データディレクトリパス
        """
        self.year = year or datetime.now().year
        self.config_path = config_path or str(Path(__file__).parent.parent / 'config' / 'assets.yaml')
        self._data_dir = data_dir

        # 月別給与データ
        self.monthly_data: List[Dict] = []

        # 控除データ
        self.deductions: Dict[str, Any] = {
            'life_insurance': {'general': 0, 'medical': 0, 'pension': 0},
            'earthquake_insurance': 0,
            'housing_loan': {'balance': 0, 'rate': 0.007, 'first_year': False},
            'spouse': {'applicable': False, 'income': 0},
            'dependents': [],
            'social_insurance': 0,  # 社会保険料（給与から自動計算）
            'small_enterprise': 0,  # 小規模企業共済
            'medical_expense': {'total': 0, 'insurance_reimbursement': 0, 'self_medication': 0, 'use_self_medication': False},
            'furusato_nouzei': {'total_donation': 0, 'use_one_stop': True},
        }

    def add_monthly_salary(self, month: int, salary: int, bonus: int = 0,
                           withheld_tax: int = 0, social_insurance: int = 0) -> None:
        """月別給与データを追加

        Args:
            month: 月（1-12）
            salary: 給与額
            bonus: 賞与額
            withheld_tax: 源泉徴収税額
            social_insurance: 社会保険料
        """
        # 入力値の範囲検証
        if not (1 <= month <= 12):
            raise ValueError(f"月は1から12の範囲で指定してください: {month}")
        if not (0 <= salary <= 100_000_000):
            raise ValueError(f"給与は0から100,000,000の範囲で指定してください: {salary}")
        if not (0 <= bonus <= 100_000_000):
            raise ValueError(f"賞与は0から100,000,000の範囲で指定してください: {bonus}")

        # 既存データがあれば更新
        existing = next((d for d in self.monthly_data if d['month'] == month), None)
        if existing:
            existing.update({
                'salary': salary,
                'bonus': bonus,
                'withheld_tax': withheld_tax,
                'social_insurance': social_insurance
            })
        else:
            self.monthly_data.append({
                'month': month,
                'salary': salary,
                'bonus': bonus,
                'withheld_tax': withheld_tax,
                'social_insurance': social_insurance
            })

    def get_annual_income(self) -> int:
        """年間給与収入を計算"""
        return sum(d['salary'] + d['bonus'] for d in self.monthly_data)

    def get_total_withheld_tax(self) -> int:
        """源泉徴収税額の合計"""
        return sum(d['withheld_tax'] for d in self.monthly_data)

    def get_total_social_insurance(self) -> int:
        """社会保険料の合計"""
        return sum(d.get('social_insurance', 0) for d in self.monthly_data)

    def calculate_salary_deduction(self, income: int) -> int:
        """給与所得控除を計算

        Args:
            income: 給与収入

        Returns:
            給与所得控除額
        """
        for threshold, rate, base, fixed in self.SALARY_DEDUCTION_TABLE:
            if income <= threshold:
                if fixed is not None:
                    return fixed
                return int(income * rate + base)
        return 1950000  # 上限

    def calculate_life_insurance_deduction(self) -> int:
        """生命保険料控除を計算

        Returns:
            控除額（上限12万円）
        """
        total = 0
        for key in ['general', 'medical', 'pension']:
            premium = self.deductions['life_insurance'].get(key, 0)
            if premium <= 20000:
                deduction = premium
            elif premium <= 40000:
                deduction = premium * 0.5 + 10000
            elif premium <= 80000:
                deduction = premium * 0.25 + 20000
            else:
                deduction = 40000
            total += int(deduction)

        return min(total, 120000)

    def calculate_earthquake_insurance_deduction(self) -> int:
        """地震保険料控除を計算

        Returns:
            控除額（上限5万円）
        """
        premium = self.deductions.get('earthquake_insurance', 0)
        return min(premium, 50000)

    def calculate_spouse_deduction(self, taxable_income: int) -> int:
        """配偶者控除を計算

        Args:
            taxable_income: 本人の合計所得金額

        Returns:
            控除額
        """
        if not self.deductions['spouse'].get('applicable', False):
            return 0

        spouse_income = self.deductions['spouse'].get('income', 0)

        # 配偶者の所得が48万円超なら控除なし
        if spouse_income > 480000:
            return 0

        # 本人の所得による控除額の段階
        if taxable_income <= 9000000:
            return 380000
        elif taxable_income <= 9500000:
            return 260000
        elif taxable_income <= 10000000:
            return 130000
        else:
            return 0

    def calculate_dependent_deduction(self) -> int:
        """扶養控除を計算

        Returns:
            控除額
        """
        total = 0
        for dep in self.deductions.get('dependents', []):
            age = dep.get('age', 0)
            if age < 16:
                continue  # 16歳未満は控除なし
            elif age < 19 or age >= 23:
                total += 380000  # 一般扶養
            else:
                total += 630000  # 特定扶養（19-22歳）

        return total

    def calculate_housing_loan_credit(self, tax_amount: int) -> int:
        """住宅ローン控除を計算（税額控除）

        Args:
            tax_amount: 算出税額

        Returns:
            控除額
        """
        loan_data = self.deductions.get('housing_loan', {})
        balance = loan_data.get('balance', 0)
        rate = loan_data.get('rate', 0.007)

        if balance == 0:
            return 0

        credit = int(balance * rate)
        # 税額を超えない
        return min(credit, tax_amount)

    def calculate_total_deductions(self, income: int) -> Dict[str, int]:
        """所得控除の合計を計算

        Args:
            income: 給与所得

        Returns:
            控除項目ごとの金額
        """
        # 生命保険料控除: CSVからインポートした場合は計算済み控除額を使用
        life_insurance = self.deductions.get('life_insurance_deduction', 0)
        if life_insurance == 0:
            life_insurance = self.calculate_life_insurance_deduction()

        deductions = {
            '基礎控除': self.BASIC_DEDUCTION,
            '社会保険料控除': self.get_total_social_insurance() or self.deductions.get('social_insurance', 0),
            '生命保険料控除': life_insurance,
            '地震保険料控除': self.calculate_earthquake_insurance_deduction(),
            '配偶者控除': self.calculate_spouse_deduction(income),
            '扶養控除': self.calculate_dependent_deduction(),
            '小規模企業共済等掛金控除': self.deductions.get('small_enterprise', 0),
        }
        return deductions

    def calculate_income_tax(self, taxable_income: int) -> int:
        """所得税を計算

        Args:
            taxable_income: 課税所得

        Returns:
            所得税額
        """
        if taxable_income <= 0:
            return 0

        for threshold, rate, deduction in self.INCOME_TAX_BRACKETS:
            if taxable_income <= threshold:
                return int(taxable_income * rate - deduction)

        # 最高税率
        return int(taxable_income * 0.45 - 4796000)

    def calculate_adjustment(self) -> Dict[str, Any]:
        """年末調整を計算

        Returns:
            計算結果の辞書
        """
        # 1. 年間給与収入
        annual_income = self.get_annual_income()

        # 2. 給与所得控除
        salary_deduction = self.calculate_salary_deduction(annual_income)

        # 3. 給与所得
        salary_income = max(annual_income - salary_deduction, 0)

        # 4. 所得控除
        deductions = self.calculate_total_deductions(salary_income)
        total_deduction = sum(deductions.values())

        # 5. 課税所得
        taxable_income = max(salary_income - total_deduction, 0)
        # 1000円未満切り捨て
        taxable_income = (taxable_income // 1000) * 1000

        # 6. 算出税額
        calculated_tax = self.calculate_income_tax(taxable_income)

        # 7. 住宅ローン控除（税額控除）
        housing_credit = self.calculate_housing_loan_credit(calculated_tax)

        # 8. 年税額（100円未満切り捨て）
        annual_tax = max(calculated_tax - housing_credit, 0)
        annual_tax = (annual_tax // 100) * 100

        # 9. 復興特別所得税
        reconstruction_tax = int(annual_tax * 0.021)

        # 10. 年調年税額
        final_tax = annual_tax + reconstruction_tax

        # 11. 源泉徴収税額との差額
        withheld_tax = self.get_total_withheld_tax()
        adjustment = withheld_tax - final_tax

        return {
            '年間給与収入': annual_income,
            '給与所得控除': salary_deduction,
            '給与所得': salary_income,
            '所得控除': deductions,
            '所得控除合計': total_deduction,
            '課税所得': taxable_income,
            '算出税額': calculated_tax,
            '住宅ローン控除': housing_credit,
            '年税額': annual_tax,
            '復興特別所得税': reconstruction_tax,
            '年調年税額': final_tax,
            '源泉徴収税額': withheld_tax,
            '過不足額': adjustment,
            '結果': '還付' if adjustment > 0 else '徴収' if adjustment < 0 else '精算なし'
        }

    def set_life_insurance(self, general: int = 0, medical: int = 0, pension: int = 0) -> None:
        """生命保険料を設定

        Args:
            general: 一般生命保険料
            medical: 介護医療保険料
            pension: 個人年金保険料
        """
        self.deductions['life_insurance'] = {
            'general': general,
            'medical': medical,
            'pension': pension
        }

    def set_earthquake_insurance(self, amount: int) -> None:
        """地震保険料を設定"""
        self.deductions['earthquake_insurance'] = amount

    def set_housing_loan(self, balance: int, rate: float = 0.007) -> None:
        """住宅ローン控除を設定

        Args:
            balance: 年末残高
            rate: 控除率（デフォルト0.7%）
        """
        self.deductions['housing_loan'] = {
            'balance': balance,
            'rate': rate
        }

    def set_spouse(self, applicable: bool, income: int = 0) -> None:
        """配偶者控除を設定

        Args:
            applicable: 適用するか
            income: 配偶者の所得
        """
        self.deductions['spouse'] = {
            'applicable': applicable,
            'income': income
        }

    def add_dependent(self, age: int, relationship: str = '') -> None:
        """扶養親族を追加

        Args:
            age: 年齢
            relationship: 続柄
        """
        self.deductions['dependents'].append({
            'age': age,
            'relationship': relationship
        })

    def set_social_insurance(self, amount: int) -> None:
        """社会保険料を設定（月次データがない場合）"""
        self.deductions['social_insurance'] = amount

    def set_small_enterprise(self, amount: int) -> None:
        """小規模企業共済等掛金を設定"""
        self.deductions['small_enterprise'] = amount

    def set_medical_expense(self, total: int, insurance_reimbursement: int = 0,
                            self_medication: int = 0, use_self_medication: bool = False) -> None:
        self.deductions['medical_expense'] = {
            'total': total,
            'insurance_reimbursement': insurance_reimbursement,
            'self_medication': self_medication,
            'use_self_medication': use_self_medication,
        }

    def set_furusato_nouzei(self, total_donation: int, use_one_stop: bool = True) -> None:
        self.deductions['furusato_nouzei'] = {
            'total_donation': total_donation,
            'use_one_stop': use_one_stop,
        }

    def to_dict(self) -> Dict:
        """辞書形式で出力（保存用）"""
        return {
            'year': self.year,
            'monthly_data': self.monthly_data,
            'deductions': self.deductions
        }

    def from_dict(self, data: Dict) -> None:
        """辞書形式から復元"""
        self.year = data.get('year', self.year)
        self.monthly_data = data.get('monthly_data', [])
        self.deductions = data.get('deductions', self.deductions)
        if 'medical_expense' not in self.deductions:
            self.deductions['medical_expense'] = {'total': 0, 'insurance_reimbursement': 0, 'self_medication': 0, 'use_self_medication': False}
        if 'furusato_nouzei' not in self.deductions:
            self.deductions['furusato_nouzei'] = {'total_donation': 0, 'use_one_stop': True}

    def save_to_yaml(self, path: str = None) -> None:
        """YAMLファイルに保存"""
        default = str(Path(self._data_dir) / 'year_end_adjustment.yaml') if self._data_dir else str(Path(__file__).parent.parent / 'data' / 'year_end_adjustment.yaml')
        save_path = path or default
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True, default_flow_style=False)

    def load_from_yaml(self, path: str = None) -> bool:
        """YAMLファイルから読み込み"""
        default = str(Path(self._data_dir) / 'year_end_adjustment.yaml') if self._data_dir else str(Path(__file__).parent.parent / 'data' / 'year_end_adjustment.yaml')
        load_path = path or default

        if not Path(load_path).exists():
            return False

        with open(load_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if data:
            self.from_dict(data)
            return True
        return False

    def generate_monthly_df(self) -> pd.DataFrame:
        """月別データをDataFrameで取得"""
        if not self.monthly_data:
            return pd.DataFrame(columns=['月', '給与', '賞与', '源泉徴収税額', '社会保険料'])

        df = pd.DataFrame(self.monthly_data)
        df = df.rename(columns={
            'month': '月',
            'salary': '給与',
            'bonus': '賞与',
            'withheld_tax': '源泉徴収税額',
            'social_insurance': '社会保険料'
        })
        return df.sort_values('月').reset_index(drop=True)

    def generate_report(self) -> str:
        """年末調整レポートを生成"""
        result = self.calculate_adjustment()

        report = f"""
========================================
        年末調整計算書（{self.year}年分）
========================================

【収入】
  年間給与収入: ¥{result['年間給与収入']:,}

【所得】
  給与所得控除: ¥{result['給与所得控除']:,}
  給与所得:     ¥{result['給与所得']:,}

【所得控除】
"""
        for name, amount in result['所得控除'].items():
            if amount > 0:
                report += f"  {name}: ¥{amount:,}\n"

        report += f"""
  所得控除合計: ¥{result['所得控除合計']:,}

【税額計算】
  課税所得:       ¥{result['課税所得']:,}
  算出税額:       ¥{result['算出税額']:,}
  住宅ローン控除: ¥{result['住宅ローン控除']:,}
  年税額:         ¥{result['年税額']:,}
  復興特別所得税: ¥{result['復興特別所得税']:,}
  年調年税額:     ¥{result['年調年税額']:,}

【精算】
  源泉徴収税額:   ¥{result['源泉徴収税額']:,}
  過不足額:       ¥{abs(result['過不足額']):,} （{result['結果']}）

========================================
"""
        return report

    def import_from_csv(self, file) -> Dict[str, Any]:
        """源泉徴収票CSVをインポート

        Args:
            file: アップロードされたCSVファイル（BytesIOまたはファイルオブジェクト）

        Returns:
            インポートされたデータの辞書
        """
        import io
        import re

        # ファイル読み込み
        if hasattr(file, 'read'):
            content = file.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8')
        else:
            content = str(file)

        lines = content.strip().split('\n')

        # 1行目（タイトル）から年度を抽出
        year_match = re.search(r'令和(\d+)年', lines[0])
        if year_match:
            reiwa_year = int(year_match.group(1))
            self.year = 2018 + reiwa_year  # 令和1年 = 2019年

        # 2行目以降をCSVとして読み込み
        csv_content = '\n'.join(lines[1:])
        df = pd.read_csv(io.StringIO(csv_content))

        result = {}
        for _, row in df.iterrows():
            item = str(row.iloc[0])  # 項目列
            # カンマ区切りの数値を処理
            amount_str = str(row.iloc[1]).replace(',', '').replace('"', '').strip()
            try:
                amount = int(amount_str)
            except ValueError:
                continue

            if '支払金額' in item:
                result['annual_income'] = amount
            elif '源泉徴収税額' in item:
                result['withheld_tax'] = amount
            elif '社会保険料' in item:
                result['social_insurance'] = amount
            elif '小規模企業共済' in item:
                result['small_enterprise'] = amount
            elif '生命保険料' in item:
                result['life_insurance_deduction'] = amount

        # データを設定
        self.set_annual_totals(**result)
        return result

    def set_annual_totals(self, annual_income: int, withheld_tax: int = 0,
                          social_insurance: int = 0, small_enterprise: int = 0,
                          life_insurance_deduction: int = 0) -> None:
        """年間合計データを直接設定（月次入力の代替）

        Args:
            annual_income: 年間給与収入
            withheld_tax: 源泉徴収税額
            social_insurance: 社会保険料
            small_enterprise: 小規模企業共済等掛金
            life_insurance_deduction: 生命保険料控除額（計算済み）
        """
        # 月次データをクリアし、年間合計として1月に登録
        self.monthly_data = [{
            'month': 1,
            'salary': annual_income,
            'bonus': 0,
            'withheld_tax': withheld_tax,
            'social_insurance': social_insurance
        }]

        # 控除を設定
        self.set_small_enterprise(small_enterprise)

        # 生命保険料は「控除額」としてそのまま保存
        # （CSVには控除額が記載されているため、再計算不要）
        self.deductions['life_insurance_deduction'] = life_insurance_deduction

    def import_from_pdf(self, file) -> Dict[str, Any]:
        """源泉徴収票PDFをインポート

        Args:
            file: アップロードされたPDFファイル（BytesIOまたはファイルオブジェクト）

        Returns:
            インポートされたデータの辞書
        """
        import re
        import io

        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumberがインストールされていません。pip install pdfplumber を実行してください。")

        # ファイルをBytesIOに変換
        if hasattr(file, 'read'):
            content = file.read()
            if hasattr(file, 'seek'):
                file.seek(0)
            pdf_file = io.BytesIO(content)
        else:
            pdf_file = file

        # PDFからテキストを抽出
        text = ""
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        # 年度を抽出
        year_match = re.search(r'令和\s*(\d+)\s*年', text)
        if year_match:
            reiwa_year = int(year_match.group(1))
            self.year = 2018 + reiwa_year

        # 金額パターン（カンマ区切りの数値）
        def extract_amount(pattern: str, text: str) -> int:
            match = re.search(pattern, text)
            if match:
                amount_str = match.group(1).replace(',', '').replace(' ', '')
                try:
                    return int(amount_str)
                except ValueError:
                    return 0
            return 0

        result = {}

        # 各項目を抽出（源泉徴収票の一般的なフォーマットに対応）
        patterns = {
            'annual_income': [
                r'支払金額[^\d]*([0-9,]+)',
                r'給与.*支払.*金額[^\d]*([0-9,]+)',
                r'支払\s*金額\s*([0-9,]+)',
            ],
            'withheld_tax': [
                r'源泉徴収税額[^\d]*([0-9,]+)',
                r'源泉\s*徴収\s*税額[^\d]*([0-9,]+)',
            ],
            'social_insurance': [
                r'社会保険料等の金額[^\d]*([0-9,]+)',
                r'社会保険料[^\d]*([0-9,]+)',
            ],
            'small_enterprise': [
                r'小規模企業共済等掛金[^\d]*([0-9,]+)',
                r'小規模.*共済[^\d]*([0-9,]+)',
            ],
            'life_insurance_deduction': [
                r'生命保険料の控除額[^\d]*([0-9,]+)',
                r'生命保険料.*控除[^\d]*([0-9,]+)',
            ],
        }

        for key, pattern_list in patterns.items():
            for pattern in pattern_list:
                amount = extract_amount(pattern, text)
                if amount > 0:
                    result[key] = amount
                    break

        if not result.get('annual_income'):
            raise ValueError("PDFから支払金額を抽出できませんでした。フォーマットを確認してください。")

        # データを設定
        self.set_annual_totals(**result)
        return result
