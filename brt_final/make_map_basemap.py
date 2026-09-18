# -*- coding: utf-8 -*-
"""
세종시 BRT 연계 정류장 환승·대기 취약도 — 발표용 클린 베이스맵 (텍스트 없음)

선행 실행
    python analysis_final.py

기본 실행
    python make_map_basemap.py

출력
    ./output/brt_map_clean_no_text.png
    ./output/brt_map_clean_top5_only.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from analysis_io import load_analysis_df
from make_map_final import (
    GRADE_ALPHA,
    GRADE_COLORS,
    GRADE_Z,
    TOP5_FIXED,
    add_merc_columns,
    fetch_basemap,
    lonlat_to_merc,
    normalize_route,
    read_csv_auto,
    resolve_top5_stops,
)


CLEAN_GRADE_SIZES = {"A": 7, "B": 9, "C": 16, "D": 30, "E": 42}
BRT_LINE_LW = 1.2
BRT_LINE_ALPHA = 0.32
BRT_MARKER_SIZE = 20

TOP5_HALO_STYLE: list[dict[str, float]] = [
    {"outer_s": 540, "inner_s": 360, "outer_lw": 3.2, "inner_lw": 2.0},
    {"outer_s": 500, "inner_s": 330, "outer_lw": 3.0, "inner_lw": 1.9},
    {"outer_s": 460, "inner_s": 300, "outer_lw": 2.8, "inner_lw": 1.8},
    {"outer_s": 500, "inner_s": 330, "outer_lw": 3.0, "inner_lw": 1.9},
    {"outer_s": 460, "inner_s": 300, "outer_lw": 2.8, "inner_lw": 1.8},
]

OUTPUT_CLEAN = "brt_map_clean_no_text.png"
OUTPUT_TOP5 = "brt_map_clean_top5_only.png"


def validate_top5_for_basemap(top5: pd.DataFrame) -> None:
    expected = {(str(s["name"]), str(s["dong"])) for s in TOP5_FIXED}
    found = {(str(r["정류소명"]), str(r["동"]).strip()) for _, r in top5.iterrows()}
    if found != expected:
        raise ValueError(f"TOP5 매칭 오류: 기대={expected}, 실제={found}")

    jochiwon = {"세종세무서", "서창리", "세종여자고등학교"}
    bugang = {"한화사원아파트", "부강3리"}
    for _, row in top5.iterrows():
        name, dong = str(row["정류소명"]), str(row["동"]).strip()
        if name in jochiwon and dong != "조치원읍":
            raise ValueError(f"{name}의 행정동이 조치원읍이 아닙니다: {dong}")
        if name in bugang and dong != "부강면":
            raise ValueError(f"{name}의 행정동이 부강면이 아닙니다: {dong}")


def plot_brt_lines_faint(ax, stops: pd.DataFrame, routes: list[str]) -> None:
    if "노선번호" not in stops.columns:
        return
    stops = add_merc_columns(stops.copy())
    stops["노선번호"] = stops["노선번호"].apply(normalize_route)
    sort_cols = [c for c in ["노선번호", "연번"] if c in stops.columns]
    for route in routes:
        line = stops[stops["노선번호"] == route]
        if line.empty:
            continue
        if sort_cols:
            line = line.sort_values(sort_cols)
        ax.plot(
            line["x_merc"], line["y_merc"],
            color="#2E5F8A", lw=BRT_LINE_LW, alpha=BRT_LINE_ALPHA,
            solid_capstyle="round", zorder=1,
        )


def plot_top5_halo(ax, top5: pd.DataFrame) -> None:
    """텍스트 없이 TOP5 위치만 이중 halo로 강조한다."""
    for idx, row in top5.iterrows():
        style = TOP5_HALO_STYLE[idx]
        x, y = float(row["x_merc"]), float(row["y_merc"])
        z = 20 + idx

        ax.scatter(
            [x], [y],
            s=style["outer_s"], facecolors="none", edgecolors="#C0392B",
            linewidths=style["outer_lw"], alpha=0.92, zorder=z,
        )
        ax.scatter(
            [x], [y],
            s=style["inner_s"], facecolors="none", edgecolors="#E74C3C",
            linewidths=style["inner_lw"], alpha=0.75, zorder=z + 0.1,
        )


def compute_map_bounds(g: pd.DataFrame) -> tuple[float, float, float, float]:
    xmin, xmax = 127.10, 127.44
    ymin, ymax = 36.41, 36.77
    xpad, ypad = 0.012, 0.012
    xmin = min(xmin, float(g["경도"].min()) - xpad)
    xmax = max(xmax, float(g["경도"].max()) + xpad)
    ymin = min(ymin, float(g["위도"].min()) - ypad)
    ymax = max(ymax, float(g["위도"].max()) + ypad)
    return xmin, ymin, xmax, ymax


def draw_basemap_layers(
    ax,
    g: pd.DataFrame,
    stops: pd.DataFrame,
    brt_routes: list[str],
    basemap_provider: str,
) -> None:
    xmin, ymin, xmax, ymax = compute_map_bounds(g)
    mxmin, mymin = lonlat_to_merc(xmin, ymin)
    mxmax, mymax = lonlat_to_merc(xmax, ymax)
    ax.set_xlim(mxmin, mxmax)
    ax.set_ylim(mymin, mymax)

    result = fetch_basemap(xmin, ymin, xmax, ymax, provider=basemap_provider)
    if result is not None:
        mosaic, extent = result
        ax.imshow(mosaic, extent=extent, origin="upper", alpha=0.94, zorder=0, interpolation="bilinear")
    else:
        ax.set_facecolor("#F3F4F0")
        print("[경고] 배경 지도를 불러오지 못했습니다. 단색 배경으로 대체합니다.")

    plot_brt_lines_faint(ax, stops, brt_routes)

    env = g[~g["BRT경유"]].copy()
    for grade in ["A", "B", "C", "D", "E"]:
        subset = env[env["등급"] == grade]
        if subset.empty:
            continue
        ax.scatter(
            subset["x_merc"], subset["y_merc"],
            s=CLEAN_GRADE_SIZES[grade], c=GRADE_COLORS[grade], alpha=GRADE_ALPHA[grade],
            edgecolors="white" if grade in {"D", "E"} else "none",
            linewidths=0.5, zorder=GRADE_Z[grade],
        )

    brt = g[g["BRT경유"]]
    if not brt.empty:
        ax.scatter(
            brt["x_merc"], brt["y_merc"],
            s=BRT_MARKER_SIZE, marker="s", c="#2E5F8A",
            alpha=0.88, edgecolors="white", linewidths=0.45, zorder=6,
        )

    ax.set_xticks([])
    ax.set_yticks([])
    ax.axis("off")
    for spine in ax.spines.values():
        spine.set_visible(False)


def print_top5_coords(top5: pd.DataFrame) -> None:
    print("\n[TOP5 BASEMAP] 강조 마커 좌표")
    for _, row in top5.iterrows():
        print(
            f"  {row['정류소명']} ({row['동']}) "
            f"lat={float(row['위도']):.5f}, lon={float(row['경도']):.5f}"
        )
    print()


def make_basemaps(
    data_dir: Path,
    output_dir: Path,
    brt_routes: list[str],
    basemap_provider: str = "carto_light",
    pad_inches: float = 0.05,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    g_path = output_dir / "g.pkl"
    if not g_path.exists() and not (output_dir / "stop_grades_final.csv").exists():
        raise FileNotFoundError(f"분석 결과가 없습니다. 먼저 analysis_final.py를 실행하세요.")

    g = add_merc_columns(load_analysis_df(output_dir))
    stops_path = data_dir / "bus_stops.csv"
    stops = read_csv_auto(stops_path) if stops_path.exists() else pd.DataFrame()

    env = g[~g["BRT경유"]].copy()
    top5 = resolve_top5_stops(env)
    validate_top5_for_basemap(top5)
    print_top5_coords(top5)

    fig, ax = plt.subplots(figsize=(16, 9), facecolor="white")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    draw_basemap_layers(ax, g, stops, brt_routes, basemap_provider)

    clean_path = output_dir / OUTPUT_CLEAN
    fig.savefig(
        clean_path, dpi=300, bbox_inches="tight",
        pad_inches=pad_inches, facecolor="white",
    )
    print(f"saved {clean_path.resolve()}")

    plot_top5_halo(ax, top5)
    top5_path = output_dir / OUTPUT_TOP5
    fig.savefig(
        top5_path, dpi=300, bbox_inches="tight",
        pad_inches=pad_inches, facecolor="white",
    )
    print(f"saved {top5_path.resolve()}")

    plt.close(fig)
    return clean_path, top5_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="발표용 클린 베이스맵 생성 (텍스트 없음)")
    parser.add_argument("--data-dir", default="data", type=Path)
    parser.add_argument("--output-dir", default="output", type=Path)
    parser.add_argument("--brt-routes", default="B0,B2,B5")
    parser.add_argument("--basemap-provider", default="carto_light", choices=["carto_light", "opentopomap", "osm"])
    parser.add_argument("--pad-inches", default=0.05, type=float)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    routes = [r.strip() for r in args.brt_routes.split(",") if r.strip()]
    make_basemaps(
        args.data_dir,
        args.output_dir,
        routes,
        basemap_provider=args.basemap_provider,
        pad_inches=args.pad_inches,
    )
