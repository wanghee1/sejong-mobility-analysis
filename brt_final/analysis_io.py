# -*- coding: utf-8 -*-
"""analysis_final.py 산출물 로더 — CSV 우선 (Python/pandas 버전 호환)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


def load_analysis_df(output_dir: Path) -> pd.DataFrame:
    """
    분석 결과 DataFrame을 불러온다.

    stop_grades_final.csv를 우선 사용한다.
    g.pkl은 CSV가 없을 때만 사용하며, Python 3.8+ / pandas 2.x 환경에서 생성된
    pickle은 Python 3.7에서 읽을 수 없으므로 CSV 사용을 권장한다.
    """
    output_dir = Path(output_dir)
    csv_path = output_dir / "stop_grades_final.csv"
    pkl_path = output_dir / "g.pkl"

    if csv_path.exists():
        print(f"[INFO] 분석 결과 로드: {csv_path.name} (CSV)")
        return pd.read_csv(csv_path, encoding="utf-8-sig")

    if not pkl_path.exists():
        raise FileNotFoundError(
            f"{csv_path} 또는 {pkl_path}가 없습니다. 먼저 analysis_final.py를 실행하세요."
        )

    try:
        print(f"[INFO] 분석 결과 로드: {pkl_path.name} (pickle)")
        return pd.read_pickle(pkl_path)
    except Exception as exc:
        py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        raise RuntimeError(
            f"g.pkl을 읽을 수 없습니다 (현재 Python {py}).\n"
            "  → analysis_final.py를 다시 실행해 stop_grades_final.csv를 생성하거나,\n"
            "  → Python 3.11 환경에서 실행하세요.\n"
            f"원인: {exc}"
        ) from exc


def safe_to_csv(df: pd.DataFrame, path: Path, **kwargs) -> Path:
    """CSV 저장. 파일이 Excel 등에서 열려 있으면 대체 파일명으로 저장."""
    path = Path(path)
    try:
        df.to_csv(path, **kwargs)
        return path
    except PermissionError:
        alt = path.with_name(f"{path.stem}_new{path.suffix}")
        df.to_csv(alt, **kwargs)
        print(
            f"[경고] {path.name} 파일이 다른 프로그램에서 열려 있어 "
            f"{alt.name}으로 저장했습니다. Excel/뷰어에서 원본 파일을 닫은 뒤 다시 실행하세요."
        )
        return alt
