# -*- coding: utf-8 -*-
"""
정류소ID(상·하행) 단위 분석 결과를 물리적 정류장(정류소명) 단위로 병합.

선행 실행
    python analysis_final.py

기본 실행
    python merge_directions.py --output-dir output --direction-agg max

출력 (덮어씀)
    output/stop_grades_final.csv
    output/g.pkl
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from analysis_final import GRADE_ORDER, POLICY


NUM_MAX_COLS = [
    "노선수",
    "최소배차분_전체", "평균배차분_전체", "최대배차분_전체", "합산배차분_전체",
    "지선최소배차분", "지선평균배차분", "지선합산배차분", "지선최대배차분",
    "대표배차분", "최대배차폭", "최근접BRT_m",
    "반경500m_학교수", "동_병의원수", "반경500m_병의원수",
    "환승위험", "도착불안정", "약자인접도", "취약도점수",
]

BOOL_ANY_COLS = [
    "BRT경유", "지선환승필수", "대기취약", "대기심각", "약자인접", "병의원인접",
]

FIRST_COLS = ["배차기준", "병의원산정방식", "병의원접근성", "동"]


def _union_routes(series: pd.Series) -> list[str]:
    routes: set[str] = set()
    for val in series:
        if isinstance(val, list):
            routes.update(str(x) for x in val if str(x))
        elif pd.notna(val) and str(val).strip():
            routes.update(x.strip() for x in str(val).split(",") if x.strip())
    return sorted(routes)


def _grade_row(row: pd.Series) -> str:
    if row["BRT경유"]:
        return "A"
    if row["지선환승필수"] and row["대기심각"] and row["약자인접"]:
        return "E"
    if row["약자인접"] and row["대기취약"]:
        return "D"
    if row["지선환승필수"] and row["대기심각"]:
        return "C"
    if row["지선환승필수"] or row["대기취약"]:
        return "B"
    return "A"


def _pick_worst_dong(group: pd.DataFrame) -> str:
    idx = group["취약도점수"].idxmax()
    return str(group.loc[idx, "동"])


def load_raw(output_dir: Path) -> pd.DataFrame:
    pkl_path = output_dir / "g.pkl"
    csv_path = output_dir / "stop_grades_final.csv"
    if pkl_path.exists():
        return pd.read_pickle(pkl_path)
    if csv_path.exists():
        return pd.read_csv(csv_path, encoding="utf-8-sig")
    raise FileNotFoundError(f"{pkl_path} 또는 {csv_path}가 없습니다. analysis_final.py를 먼저 실행하세요.")


def merge_directions(df: pd.DataFrame, direction_agg: str = "max") -> pd.DataFrame:
    if direction_agg != "max":
        raise ValueError(f"지원하지 않는 direction-agg: {direction_agg} (현재 max만 지원)")

    work = df.copy()
    if "정류소명" not in work.columns:
        raise ValueError("정류소명 컬럼이 없습니다.")

    agg: dict[str, tuple] = {
        "정류소ID": ("정류소ID", lambda s: ",".join(sorted({str(x) for x in s if pd.notna(x)}))),
        "위도": ("위도", "mean"),
        "경도": ("경도", "mean"),
        "노선들": ("노선들", _union_routes),
        "지선노선": ("지선노선", _union_routes),
    }
    for col in NUM_MAX_COLS:
        if col in work.columns:
            agg[col] = (col, "max")
    for col in BOOL_ANY_COLS:
        if col in work.columns:
            agg[col] = (col, "max")
    for col in FIRST_COLS:
        if col in work.columns:
            agg[col] = (col, "first")

    merged = work.groupby("정류소명", as_index=False).agg(**agg)
    merged["동"] = work.groupby("정류소명", group_keys=False).apply(_pick_worst_dong, include_groups=False).to_numpy()

    if "노선들" in merged.columns:
        merged["BRT경유"] = merged["BRT경유"].astype(bool)
    if "지선노선" in merged.columns and "노선들" in merged.columns:
        merged["지선노선"] = merged.apply(
            lambda r: r["지선노선"] if isinstance(r["지선노선"], list) and r["지선노선"] else [],
            axis=1,
        )

    for col in BOOL_ANY_COLS:
        if col in merged.columns:
            merged[col] = merged[col].astype(bool)

    merged["등급"] = merged.apply(_grade_row, axis=1)
    merged["정책처방"] = merged["등급"].map(POLICY)
    merged["등급가중치"] = merged["등급"].map(GRADE_ORDER)

    env_mask = ~merged["BRT경유"]
    sort_cols = ["등급가중치", "취약도점수", "대표배차분", "최근접BRT_m", "약자인접도"]
    sort_cols = [c for c in sort_cols if c in merged.columns]
    sorted_env_idx = merged.loc[env_mask].sort_values(sort_cols, ascending=False).index
    merged["개선우선순위"] = np.nan
    merged.loc[sorted_env_idx, "개선우선순위"] = np.arange(1, len(sorted_env_idx) + 1)
    merged["개선우선순위"] = merged["개선우선순위"].astype("Int64")

    return merged


def save_merged(merged: pd.DataFrame, output_dir: Path) -> None:
    csv_out = merged.copy()
    if "노선들" in csv_out.columns:
        csv_out["노선들"] = csv_out["노선들"].apply(
            lambda x: ",".join(x) if isinstance(x, list) else x
        )
    if "지선노선" in csv_out.columns:
        csv_out["지선노선"] = csv_out["지선노선"].apply(
            lambda x: ",".join(x) if isinstance(x, list) else x
        )
    csv_out.to_csv(output_dir / "stop_grades_final.csv", index=False, encoding="utf-8-sig")
    merged.to_pickle(output_dir / "g.pkl", protocol=4)


def merge_and_save(output_dir: Path, direction_agg: str = "max") -> pd.DataFrame:
    output_dir = Path(output_dir)
    raw = load_raw(output_dir)
    before = len(raw)
    merged = merge_directions(raw, direction_agg=direction_agg)
    save_merged(merged, output_dir)
    print(f"[merge_directions] {before}행 → {len(merged)}행 (정류소명 기준, agg={direction_agg})")
    print(f"  저장: {output_dir / 'stop_grades_final.csv'}")
    print(f"  저장: {output_dir / 'g.pkl'}")
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="상·하행 정류소ID를 물리적 정류장(정류소명) 단위로 병합")
    parser.add_argument("--output-dir", default="output", type=Path)
    parser.add_argument("--direction-agg", default="max", choices=["max"], help="방향 병합 집계 (max=취약 쪽)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    merge_and_save(args.output_dir, args.direction_agg)
