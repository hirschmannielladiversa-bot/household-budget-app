"""
汎用PDFページ分割ツール（CLI + GUI）

- CLI:
  python3 pdf_splitter.py /path/to/file.pdf --ranges "1-3,4-7,8-10" --output-dir "./out"

- GUI:
  python3 pdf_splitter.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

from modules.pdf_splitter import get_num_pages, parse_page_ranges, split_pdf_by_page_ranges


def cli_main(args: argparse.Namespace) -> int:
    input_path = Path(args.input_pdf)
    output_dir = Path(args.output_dir)

    ranges: List[Tuple[int, int]] = parse_page_ranges(args.ranges)
    _ = get_num_pages(input_path)  # boundsチェック用に一度ページ数取得

    outputs = split_pdf_by_page_ranges(
        input_path,
        output_dir,
        ranges,
        output_prefix=args.output_prefix or "",
    )

    for p in outputs:
        print(str(p))

    print(f"✓ 分割完了: {len(outputs)}ファイル")
    return 0


def gui_main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("PDF分割ツール")
    root.geometry("720x520")

    selected_pdf_var = tk.StringVar(value="")
    output_dir_var = tk.StringVar(value="")
    ranges_var = tk.StringVar(value="1-3,4-7,8-10")
    pages_var = tk.StringVar(value="(未選択)")

    def append_log(msg: str) -> None:
        log_text.configure(state="normal")
        log_text.insert("end", msg + "\n")
        log_text.configure(state="disabled")
        log_text.see("end")

    def choose_input() -> None:
        pdf_path = filedialog.askopenfilename(
            title="PDFを選択",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not pdf_path:
            return
        selected_pdf_var.set(pdf_path)
        try:
            n = get_num_pages(pdf_path)
            pages_var.set(f"{n}ページ")
            append_log(f"入力PDF: {pdf_path}（{n}ページ）")
        except Exception as e:
            pages_var.set("(エラー)")
            append_log(f"ページ数取得に失敗: {e}")
            messagebox.showerror("エラー", f"ページ数取得に失敗しました: {e}")

    def choose_output_dir() -> None:
        out_dir = filedialog.askdirectory(title="保存先フォルダを選択")
        if not out_dir:
            return
        output_dir_var.set(out_dir)
        append_log(f"出力先: {out_dir}")

    def on_split() -> None:
        pdf_path = selected_pdf_var.get().strip()
        out_dir = output_dir_var.get().strip()
        ranges_text = ranges_var.get().strip()

        if not pdf_path:
            messagebox.showwarning("確認", "入力PDFを選択してください")
            return
        if not out_dir:
            messagebox.showwarning("確認", "保存先フォルダを選択してください")
            return

        try:
            page_ranges = parse_page_ranges(ranges_text)
            n = get_num_pages(pdf_path)
            append_log(f"指定範囲: {ranges_text}")
            append_log(f"PDFページ数: {n}")

            outputs = split_pdf_by_page_ranges(
                pdf_path,
                out_dir,
                page_ranges,
            )

            append_log("✓ 分割完了")
            for p in outputs:
                append_log(f"  - {p}")
            messagebox.showinfo("完了", f"分割完了: {len(outputs)}ファイル")
        except Exception as e:
            append_log(f"× 分割失敗: {e}")
            messagebox.showerror("エラー", f"分割に失敗しました: {e}")

    # UI
    container = tk.Frame(root, padx=12, pady=12)
    container.pack(fill="both", expand=True)

    tk.Label(container, text="入力PDF").grid(row=0, column=0, sticky="w")
    tk.Entry(container, textvariable=selected_pdf_var, width=70).grid(row=0, column=1, sticky="we", padx=8)
    tk.Button(container, text="参照", command=choose_input, width=10).grid(row=0, column=2, sticky="e")

    tk.Label(container, text="保存先フォルダ").grid(row=1, column=0, sticky="w")
    tk.Entry(container, textvariable=output_dir_var, width=70).grid(row=1, column=1, sticky="we", padx=8)
    tk.Button(container, text="参照", command=choose_output_dir, width=10).grid(row=1, column=2, sticky="e")

    tk.Label(container, text="分割ページ範囲").grid(row=2, column=0, sticky="w")
    tk.Entry(container, textvariable=ranges_var, width=70).grid(row=2, column=1, sticky="we", padx=8)
    tk.Label(container, textvariable=pages_var).grid(row=2, column=2, sticky="e")

    # 入力例
    tk.Label(
        container,
        text="例: 1-3,4-7,8-10（1ページ単独: 5）",
        fg="#555"
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 10))

    tk.Button(container, text="分割実行", command=on_split, bg="#2b6cb0", fg="white", height=2).grid(
        row=4, column=0, columnspan=3, sticky="we"
    )

    log_text = tk.Text(container, height=12, state="disabled")
    log_text.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(12, 0))

    container.grid_rowconfigure(5, weight=1)
    container.grid_columnconfigure(1, weight=1)

    # 初期ログ
    append_log("PDF分割ツールを起動しました。")

    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="汎用PDFページ分割ツール（CLI + GUI）")
    parser.add_argument("input_pdf", nargs="?", help="入力PDFパス（指定するとCLI動作）")
    parser.add_argument(
        "--ranges",
        default="1-3,4-7,8-10",
        help="ページ範囲（例: 1-3,4-7,8-10 / 1:3 / 5）"
    )
    parser.add_argument(
        "--output-dir",
        default="./pdf_splits",
        help="分割後PDFの保存先ディレクトリ"
    )
    parser.add_argument(
        "--output-prefix",
        default="",
        help="出力ファイル名の先頭に付ける任意の接頭辞（例: credit_card）"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="GUIを強制起動（input_pdf を指定してもGUI）"
    )

    args = parser.parse_args()

    if args.gui or not args.input_pdf:
        return gui_main()
    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main())

