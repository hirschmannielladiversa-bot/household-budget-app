"""PDF分割ユーティリティ

汎用的に「指定したページ範囲」ごとに別ファイルとして書き出す。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple, Union


try:
    from pypdf import PdfReader, PdfWriter  # type: ignore

    PDF_SPLIT_AVAILABLE = True
except ImportError:  # pragma: no cover
    PdfReader = None
    PdfWriter = None
    PDF_SPLIT_AVAILABLE = False


PageRange = Tuple[int, int]  # (start_page, end_page) 1-indexed inclusive


def _normalize_ranges_text(s: str) -> str:
    # 日本語の全角記号や区切りを半角に寄せる
    s = s.replace("，", ",").replace("、", ",").replace("；", ";")
    s = s.replace("・", ",")
    # 全角ダッシュ(一部)を置換（- と : の両方に対応）
    s = s.replace("－", "-").replace("—", "-").replace("–", "-")
    return s.strip()


def parse_page_ranges(ranges_text: str) -> List[PageRange]:
    """
    ページ範囲をパースする。

    例:
      - "1-3,4-7,8-10"
      - "1-3 4-7 8-10"
      - "1:3,4:7"（: も "-" と同等）
      - "5"（単一ページ）
    """
    if not PDF_SPLIT_AVAILABLE:
        raise ImportError("pypdfがインストールされていません: pip install pypdf")

    text = _normalize_ranges_text(ranges_text)
    if not text:
        raise ValueError("ページ範囲が空です")

    parts = re.split(r"[,\s;]+", text)
    ranges: List[PageRange] = []

    for part in parts:
        if not part:
            continue

        # 1-3 or 1:3 or 3-10 のような形式
        if "-" in part:
            a, b = part.split("-", 1)
        elif ":" in part:
            a, b = part.split(":", 1)
        else:
            a, b = part, part

        start = int(a)
        end = int(b)

        if start <= 0 or end <= 0:
            raise ValueError(f"ページは1以上で指定してください: {part}")
        if end < start:
            raise ValueError(f"範囲の指定が不正です（end < start）: {part}")

        ranges.append((start, end))

    # 並び順が分かりやすいように整列
    ranges.sort(key=lambda x: (x[0], x[1]))

    # 重複はそのままだと無駄になるため統合するが、
    # ユーザーが「隣接する別セグメント」を指定するケースがあるため
    # end+1 のような“隣接”は結合しない。
    merged: List[PageRange] = []
    for start, end in ranges:
        if not merged:
            merged.append((start, end))
            continue
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def get_num_pages(pdf_path: Union[str, Path]) -> int:
    if not PDF_SPLIT_AVAILABLE:
        raise ImportError("pypdfがインストールされていません: pip install pypdf")

    path = Path(pdf_path)
    reader = PdfReader(str(path))
    try:
        # pypdf は pages の長さでページ数が取れる
        return len(reader.pages)
    finally:
        # PdfReader には close() が無い場合があるため例外握りつぶし
        try:
            reader.close()  # type: ignore[attr-defined]
        except Exception:
            pass


def split_pdf_by_page_ranges(
    pdf_path: Union[str, Path],
    output_dir: Union[str, Path],
    page_ranges: Sequence[PageRange],
    *,
    output_prefix: str = "",
) -> List[Path]:
    """
    指定したページ範囲ごとにPDFを書き出す（分割後PDFは別ファイル）。
    """
    if not PDF_SPLIT_AVAILABLE:
        raise ImportError("pypdfがインストールされていません: pip install pypdf")

    input_path = Path(pdf_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(str(input_path))

    reader = PdfReader(str(input_path))
    try:
        num_pages = len(reader.pages)

        normalized: List[PageRange] = []
        for start, end in page_ranges:
            if start > num_pages or end > num_pages:
                raise ValueError(
                    f"範囲がページ数を超えています: {start}-{end}（PDFは{num_pages}ページ）"
                )
            normalized.append((start, end))

        outputs: List[Path] = []

        for start, end in normalized:
            writer = PdfWriter()
            # pypdf は 0-indexed
            for page_idx in range(start - 1, end):
                writer.add_page(reader.pages[page_idx])

            base = input_path.stem
            prefix = output_prefix.strip()
            prefix = f"{prefix}_" if prefix else ""
            out_path = out_dir / f"{prefix}{base}_p{start}-{end}.pdf"

            with open(out_path, "wb") as f:
                writer.write(f)

            outputs.append(out_path)

        return outputs
    finally:
        try:
            reader.close()  # type: ignore[attr-defined]
        except Exception:
            pass

