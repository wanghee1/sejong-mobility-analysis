# -*- coding: utf-8 -*-
"""
세종시 BRT 연계 정류장 환승·대기 취약도 분석 지도 (발표용)

선행 실행
    python analysis_final.py

기본 실행
    python make_map_final.py

출력
    ./output/brt_transfer_vulnerability_map_final_presentation.png
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
from urllib.request import Request, urlopen

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import mercantile
import numpy as np
import pandas as pd
from analysis_io import load_analysis_df
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from PIL import Image
from pyproj import Transformer


TO_MERC = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

TILE_SIZE = 256
BASEMAP_PROVIDERS = {
    "opentopomap": "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
    "carto_light": "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}

GRADE_COLORS = {
    "A": "#C3CDD6",
    "B": "#8FA8BC",
    "C": "#F5B041",
    "D": "#E67E22",
    "E": "#C0392B",
}
GRADE_SIZES = {"A": 10, "B": 13, "C": 22, "D": 52, "E": 105}
GRADE_ALPHA = {"A": 0.34, "B": 0.45, "C": 0.62, "D": 0.88, "E": 1.00}
GRADE_Z = {"A": 2, "B": 2, "C": 3, "D": 4, "E": 5}

BRT_LINE_LW = 1.5
BRT_LINE_ALPHA = 0.42

REGION_LABELS = {
    "전의·소정면": (36.700, 127.180, "left"),
    "연서면": (36.578, 127.218, "right"),
    "조치원 서부": (36.615, 127.252, "left"),
    "연기면": (36.548, 127.238, "right"),
    "부강면": (36.498, 127.395, "left"),
    "금남면": (36.438, 127.288, "left"),
}

CITY_LABELS = {
    "천안시": (36.745, 127.112),
    "공주시": (36.415, 127.095),
    "청주시": (36.785, 127.535),
    "대전광역시": (36.265, 127.420),
}

TOP5_FIXED: list[dict[str, str | float]] = [
    {"rank": 1, "name": "세종세무서", "dong": "조치원읍"},
    {"rank": 2, "name": "서창리", "dong": "조치원읍"},
    {"rank": 3, "name": "세종여자고등학교", "dong": "조치원읍"},
    {"rank": 4, "name": "한화사원아파트", "dong": "부강면"},
    {"rank": 5, "name": "부강3리", "dong": "부강면"},
]

TOP5_NAME_OFFSET: dict[int, tuple[float, float, str]] = {
    1: (10, 8, "left"),
    2: (-10, 8, "right"),
    3: (0, -12, "center"),
    4: (10, 4, "left"),
    5: (-10, 4, "right"),
}

JOCHIWON_LAT_RANGE = (36.598, 36.612)
JOCHIWON_REQUIRED_NAMES = {"세종세무서", "서창리", "세종여자고등학교"}
JEONUI_LAT_THRESHOLD = 36.650

FORBIDDEN_TABLE_TERMS = (
    "부강2리",
    "전의면",
    "정비면",
    "학생 통행",
    "수요 많음",
    "등하교 수요",
    "반경 500m 내 학교",
)

MAP_TITLE = "세종시 BRT 연계 정류장 환승·대기 취약도 분석"
FOOTER_LINES = (
    "※ 노선별 배차간격은 운행현황 기반 정적 데이터로 산정",
    "※ 실시간 도착정보, 시간대별 혼잡도, 실제 통행량은 TAGO 수집 데이터로 고도화 예정",
)
DEFAULT_OUTPUT_NAME = "brt_transfer_vulnerability_map_final_presentation.png"


def set_korean_font() -> None:
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    for path in candidates:
        p = Path(path)
        if p.exists():
            try:
                fm.fontManager.addfont(str(p))
            except Exception:
                pass

    available = {f.name for f in fm.fontManager.ttflist}
    for name in ["NanumGothic", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR"]:
        if name in available:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def read_csv_auto(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def normalize_route(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    return s[:-2] if s.endswith(".0") else s


def lonlat_to_merc(lon: np.ndarray | float, lat: np.ndarray | float) -> tuple[np.ndarray | float, np.ndarray | float]:
    return TO_MERC.transform(lon, lat)


def estimate_zoom(west: float, south: float, east: float, north: float, max_tiles: int = 36) -> int:
    for zoom in range(15, 8, -1):
        if len(list(mercantile.tiles(west, south, east, north, zooms=[zoom]))) <= max_tiles:
            return zoom
    return 10


def fetch_basemap(
    west: float,
    south: float,
    east: float,
    north: float,
    provider: str = "opentopomap",
    zoom: int | None = None,
) -> tuple[np.ndarray, list[float]] | None:
    if provider not in BASEMAP_PROVIDERS:
        provider = "opentopomap"
    if zoom is None:
        zoom = estimate_zoom(west, south, east, north)

    tiles = list(mercantile.tiles(west, south, east, north, zooms=[zoom]))
    if not tiles:
        return None

    xs = [t.x for t in tiles]
    ys = [t.y for t in tiles]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    width = (max_x - min_x + 1) * TILE_SIZE
    height = (max_y - min_y + 1) * TILE_SIZE
    mosaic = Image.new("RGBA", (width, height), (250, 251, 252, 255))

    url_template = BASEMAP_PROVIDERS[provider]
    headers = {"User-Agent": "Sejong-BRT-Analysis/1.0 (academic visualization)"}
    for tile in tiles:
        url = url_template.format(z=tile.z, x=tile.x, y=tile.y)
        try:
            with urlopen(Request(url, headers=headers), timeout=12) as resp:
                img = Image.open(io.BytesIO(resp.read())).convert("RGBA")
            mosaic.paste(img, ((tile.x - min_x) * TILE_SIZE, (tile.y - min_y) * TILE_SIZE))
        except Exception:
            continue

    ul = mercantile.xy_bounds(mercantile.Tile(min_x, min_y, zoom))
    lr = mercantile.xy_bounds(mercantile.Tile(max_x, max_y, zoom))
    extent = [ul.left, lr.right, lr.bottom, ul.top]
    return np.asarray(mosaic), extent


def add_merc_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    mx, my = lonlat_to_merc(out["경도"].to_numpy(), out["위도"].to_numpy())
    out["x_merc"] = mx
    out["y_merc"] = my
    return out


def plot_brt_lines(ax, stops: pd.DataFrame, routes: list[str]) -> int:
    if "노선번호" not in stops.columns:
        return 0
    stops = add_merc_columns(stops.copy())
    stops["노선번호"] = stops["노선번호"].apply(normalize_route)
    sort_cols = [c for c in ["노선번호", "연번"] if c in stops.columns]
    count = 0
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
        count += 1
    return count


def fmt_headway_minutes(value: float) -> str:
    return str(int(round(float(value))))


def fmt_brt_distance_km(value_m: float) -> str:
    return f"{float(value_m) / 1000:.1f}km"


def resolve_top5_row(env: pd.DataFrame, spec: dict[str, str | float]) -> pd.Series:
    name = str(spec["name"])
    dong = str(spec["dong"])
    matches = env[(env["정류소명"] == name) & (env["동"].astype(str) == dong)].copy()
    if matches.empty:
        raise ValueError(f"TOP5 정류장을 찾을 수 없습니다: {name} ({dong})")

    if len(matches) > 1:
        sort_cols = [c for c in ["개선우선순위", "취약도점수", "대표배차분"] if c in matches.columns]
        ascending = [True, False, False][: len(sort_cols)]
        matches = matches.sort_values(sort_cols, ascending=ascending).head(1)

    row = matches.iloc[0]
    lat = float(row["위도"])
    row_dong = str(row["동"]).strip()

    if name in {"세종세무서", "서창리"} and row_dong != "조치원읍":
        raise ValueError(f"{name}의 행정동이 조치원읍이 아닙니다: {row_dong}")

    if name in JOCHIWON_REQUIRED_NAMES:
        if lat >= JEONUI_LAT_THRESHOLD:
            raise ValueError(f"{name} 좌표가 전의·소정면 쪽에 찍혔습니다 (위도={lat:.5f})")
        lo, hi = JOCHIWON_LAT_RANGE
        if not (lo <= lat <= hi):
            raise ValueError(f"{name} 위도 {lat:.5f}가 조치원읍 범위({lo}~{hi}) 밖입니다")

    return row


def resolve_top5_stops(env: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.Series] = []
    for spec in TOP5_FIXED:
        rows.append(resolve_top5_row(env, spec))
    top = pd.DataFrame(rows).reset_index(drop=True)
    top["callout_rank"] = [spec["rank"] for spec in TOP5_FIXED]
    return add_merc_columns(top)


def build_presentation_table_rows(top5: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    for _, row in top5.iterrows():
        rank = int(row["callout_rank"])
        name = str(row["정류소명"])
        note = "학교 2개소/500m" if name == "세종여자고등학교" else ""
        rows.append([
            f"{rank}위",
            name,
            str(row["동"]).strip(),
            f"대표배차 {fmt_headway_minutes(row['대표배차분'])}분",
            f"BRT까지 {fmt_brt_distance_km(row['최근접BRT_m'])}",
            note,
        ])
    return rows


def validate_presentation_table(rows: list[list[str]]) -> None:
    full_text = "\n".join(" | ".join(r) for r in rows)
    for term in FORBIDDEN_TABLE_TERMS:
        if term in full_text:
            raise ValueError(f"TOP5 표에 금지 문구가 포함되어 있습니다: '{term}'")

    school_rows = [r for r in rows if "학교" in r[-1]]
    if len(school_rows) != 1 or school_rows[0][1] != "세종여자고등학교":
        raise ValueError("학교 관련 문구는 세종여자고등학교 행에만 있어야 합니다.")


def print_top5_debug_table(top5: pd.DataFrame) -> None:
    debug = pd.DataFrame({
        "순위": top5["callout_rank"].astype(int),
        "정류소명": top5["정류소명"],
        "행정동": top5["동"].astype(str),
        "위도": top5["위도"].astype(float).map(lambda v: f"{v:.5f}"),
        "경도": top5["경도"].astype(float).map(lambda v: f"{v:.5f}"),
        "대표배차": top5["대표배차분"].map(lambda v: f"{fmt_headway_minutes(v)}분"),
        "BRT까지": top5["최근접BRT_m"].map(fmt_brt_distance_km),
    })
    print("\n[TOP5 DEBUG] 지도 마커에 사용되는 정류장 정보")
    print(debug.to_string(index=False))
    print()


def plot_top5_number_markers(ax, top5: pd.DataFrame) -> None:
    for _, row in top5.iterrows():
        rank = int(row["callout_rank"])
        x, y = float(row["x_merc"]), float(row["y_merc"])
        name = str(row["정류소명"])

        ax.scatter(
            [x], [y], s=380, c="#C0392B", edgecolors="white", linewidths=1.4, zorder=11,
        )
        ax.text(
            x, y, str(rank), ha="center", va="center",
            fontsize=12, fontweight="bold", color="white", zorder=12,
        )

        dx, dy, ha = TOP5_NAME_OFFSET.get(rank, (8, 6, "left"))
        ax.annotate(
            name,
            (x, y),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=7.0,
            color="#333333",
            ha=ha,
            va="center",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="#DDDDDD", lw=0.5, alpha=0.88),
            zorder=11,
        )


def draw_side_panel(
    ax_panel,
    table_rows: list[list[str]],
    legend_items: list[Line2D],
) -> None:
    ax_panel.axis("off")
    ax_panel.set_title("TOP5 취약 정류장", fontsize=11.5, fontweight="bold", pad=10, loc="left")

    col_labels = ["순위", "정류소명", "행정동", "배차", "BRT거리", "비고"]
    table = ax_panel.table(
        cellText=table_rows,
        colLabels=col_labels,
        loc="upper center",
        cellLoc="left",
        colLoc="center",
        bbox=[0.0, 0.38, 1.0, 0.58],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.0)
    table.scale(1.0, 1.45)

    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#DDDDDD")
        if r == 0:
            cell.set_facecolor("#F3F4F6")
            cell.set_text_props(fontweight="bold", color="#333333")
        else:
            cell.set_facecolor("#FFFFFF")

    ax_panel.legend(
        handles=legend_items,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.30),
        fontsize=7.2,
        framealpha=0.96,
        edgecolor="#CCCCCC",
        borderpad=0.5,
        labelspacing=0.45,
        handlelength=1.4,
        handletextpad=0.5,
    )


def make_map(
    data_dir: Path,
    output_dir: Path,
    brt_routes: list[str],
    basemap: bool = False,
    basemap_provider: str = "opentopomap",
    output_name: str = DEFAULT_OUTPUT_NAME,
) -> Path:
    set_korean_font()
    output_dir.mkdir(parents=True, exist_ok=True)

    g_path = output_dir / "g.pkl"
    csv_path = output_dir / "stop_grades_final.csv"
    if not g_path.exists() and not csv_path.exists():
        raise FileNotFoundError(f"분석 결과가 없습니다. 먼저 analysis_final.py를 실행하세요.")

    g = add_merc_columns(load_analysis_df(output_dir))
    stops_path = data_dir / "bus_stops.csv"
    stops = read_csv_auto(stops_path) if stops_path.exists() else pd.DataFrame()

    required = {"위도", "경도", "BRT경유", "등급", "정류소명", "취약도점수"}
    missing = sorted(required - set(g.columns))
    if missing:
        raise ValueError(f"g.pkl에 필요한 컬럼이 없습니다: {missing}")

    fig = plt.figure(figsize=(13.5, 9.8), facecolor="white")
    gs = GridSpec(1, 2, figure=fig, width_ratios=[2.35, 1.0], wspace=0.06)
    ax = fig.add_subplot(gs[0, 0])
    ax_panel = fig.add_subplot(gs[0, 1])

    xmin, xmax = 127.10, 127.44
    ymin, ymax = 36.41, 36.77
    xpad = 0.015
    ypad = 0.015
    xmin = min(xmin, float(g["경도"].min()) - xpad)
    xmax = max(xmax, float(g["경도"].max()) + xpad)
    ymin = min(ymin, float(g["위도"].min()) - ypad)
    ymax = max(ymax, float(g["위도"].max()) + ypad)

    mxmin, mymin = lonlat_to_merc(xmin, ymin)
    mxmax, mymax = lonlat_to_merc(xmax, ymax)
    ax.set_xlim(mxmin, mxmax)
    ax.set_ylim(mymin, mymax)

    basemap_added = False
    if basemap:
        result = fetch_basemap(xmin, ymin, xmax, ymax, provider=basemap_provider)
        if result is not None:
            mosaic, extent = result
            ax.imshow(
                mosaic, extent=extent, origin="upper", alpha=0.94,
                zorder=0, interpolation="bilinear",
            )
            basemap_added = True
        else:
            print("[경고] 배경 지도를 불러오지 못했습니다. 단색 배경으로 대체합니다.")

    if not basemap_added:
        ax.set_facecolor("#F3F4F0")

    plotted_routes = plot_brt_lines(ax, stops, brt_routes) if not stops.empty else 0

    env = g[~g["BRT경유"]].copy()
    for grade in ["A", "B", "C", "D", "E"]:
        subset = env[env["등급"] == grade]
        if subset.empty:
            continue
        ax.scatter(
            subset["x_merc"], subset["y_merc"],
            s=GRADE_SIZES[grade], c=GRADE_COLORS[grade], alpha=GRADE_ALPHA[grade],
            edgecolors="white" if grade in {"D", "E"} else "none",
            linewidths=0.65, zorder=GRADE_Z[grade],
        )

    brt = g[g["BRT경유"]]
    if not brt.empty:
        ax.scatter(
            brt["x_merc"], brt["y_merc"], s=28, marker="s", c="#2E5F8A",
            alpha=0.88, edgecolors="white", linewidths=0.55, zorder=6,
        )

    top5 = resolve_top5_stops(env)
    table_rows = build_presentation_table_rows(top5)
    validate_presentation_table(table_rows)

    for name, (lat, lon, ha) in REGION_LABELS.items():
        x, y = lonlat_to_merc(lon, lat)
        ax.annotate(
            name, (x, y), fontsize=9.6, fontweight="bold", color="#A93226", ha=ha, va="center",
            bbox=dict(boxstyle="round,pad=0.24", fc="white", ec="#C0392B", lw=0.9, alpha=0.90),
            zorder=7,
        )

    for name, (lat, lon) in CITY_LABELS.items():
        x, y = lonlat_to_merc(lon, lat)
        ax.text(
            x, y, name, fontsize=8.6, color="#888888", ha="center", va="center",
            style="italic", alpha=0.85, zorder=6,
        )

    bx, by = lonlat_to_merc(127.258, 36.455)
    ax.annotate(
        "행복도시(신도시)\nBRT 순환축",
        (bx, by), fontsize=9.2, color="#1F4E79",
        fontweight="bold", ha="center",
        bbox=dict(boxstyle="round,pad=0.28", fc="#EAF1F7", ec="#1F4E79", lw=0.9, alpha=0.90),
        zorder=7,
    )

    plot_top5_number_markers(ax, top5)

    counts = env["등급"].value_counts()
    legend_items = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=GRADE_COLORS["E"], markersize=8,
               label=f"E ({counts.get('E', 0)}개)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=GRADE_COLORS["D"], markersize=7,
               label=f"D ({counts.get('D', 0)}개)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=GRADE_COLORS["C"], markersize=6,
               label=f"C ({counts.get('C', 0)}개)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=GRADE_COLORS["B"], markersize=6,
               label=f"B ({counts.get('B', 0)}개)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=GRADE_COLORS["A"], markersize=6,
               label=f"A ({counts.get('A', 0)}개)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#888888", markersize=6,
               label=f"원형 점 · 일반 ({len(env)}개)"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="#2E5F8A", markersize=7,
               label=f"파란 네모 · BRT ({len(brt)}개)"),
    ]
    if plotted_routes:
        legend_items.append(
            Line2D([0], [0], color="#2E5F8A", lw=BRT_LINE_LW, alpha=BRT_LINE_ALPHA,
                   label=f"선 · BRT 노선축 ({'·'.join(brt_routes)})")
        )

    draw_side_panel(ax_panel, table_rows, legend_items)

    ax.set_title(MAP_TITLE, fontsize=14.5, fontweight="bold", pad=10)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#BBBBBB")

    fig.subplots_adjust(left=0.04, right=0.98, top=0.93, bottom=0.07, wspace=0.08)

    map_center_x = gs[0, 0].get_position(fig).x0 + gs[0, 0].get_position(fig).width / 2
    fig.text(map_center_x, 0.028, FOOTER_LINES[0], ha="center", fontsize=7.8, color="#777777")
    fig.text(map_center_x, 0.008, FOOTER_LINES[1], ha="center", fontsize=7.8, color="#777777")

    print_top5_debug_table(top5)
    out_path = output_dir / output_name
    plt.savefig(out_path, dpi=300, bbox_inches="tight", pad_inches=0.1, facecolor="white")
    plt.close(fig)
    print(f"saved {out_path.resolve()}")
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="세종시 BRT 연계 정류장 환승·대기 취약도 분석 지도 (발표용)")
    parser.add_argument("--data-dir", default="data", type=Path, help="bus_stops.csv가 들어 있는 폴더")
    parser.add_argument("--output-dir", default="output", type=Path, help="analysis_final.py 결과 폴더")
    parser.add_argument("--brt-routes", default="B0,B2,B5", help="지도에 노선축으로 표시할 BRT 노선번호")
    parser.add_argument("--output-name", default=DEFAULT_OUTPUT_NAME, help="저장할 PNG 파일명")
    parser.add_argument("--basemap", action="store_true", help="배경 지도 타일 사용")
    parser.add_argument(
        "--basemap-provider",
        default="opentopomap",
        choices=sorted(BASEMAP_PROVIDERS),
        help="배경 지도 타일 제공자",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    routes = [r.strip() for r in args.brt_routes.split(",") if r.strip()]
    make_map(
        args.data_dir,
        args.output_dir,
        routes,
        basemap=args.basemap,
        basemap_provider=args.basemap_provider,
        output_name=args.output_name,
    )
