# -*- coding: utf-8 -*-
"""
정류장 × 시간대별 BRT 환승 실패 위험도 히트맵 최종본

용도
- 최종 지도(grade_map_final.png)의 보조 근거 자료.
- 시간대별로 환승 실패가 얼마나 커지는지 보여준다.

주의
- 지선·BRT 배차간격은 운행 현황 기반이지만, 지연 분포와 환승 여유는 시뮬레이션 가정이다.
- TAGO 실시간 도착 데이터 수집 후 실측 지연 분포로 대체하는 것이 최종 고도화 방향이다.

선행 실행
    python analysis_final.py
    python merge_directions.py --output-dir output --direction-agg max

기본 실행
    python make_heatmap_final.py

출력
    ./output/heatmap_final.png
    ./output/heatmap_final.csv
    ./output/heatmap_fail_probability_final.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from analysis_io import load_analysis_df, safe_to_csv

EXPECTED_HEATMAP_STOPS = [
    "세종세무서", "서창리", "세종여자고등학교", "한화사원아파트", "부강3리", "부강면", "조치원역뒤편",
    "성호아파트", "부강삼거리", "송용리", "내판리(외판1교)", "연동중학교",
]


HOURS = [
    # 라벨, BRT 배차(분), 지선 지연 평균, 지선 지연 표준편차
    ("06시", 15, 1.5, 2.0),
    ("07시", 10, 4.5, 3.8),
    ("08시", 8, 6.2, 4.5),
    ("09시", 12, 3.5, 3.2),
    ("12시", 15, 2.2, 2.4),
    ("15시", 15, 2.0, 2.2),
    ("17시", 10, 4.8, 4.0),
    ("18시", 8, 6.5, 4.8),
    ("19시", 12, 4.0, 3.5),
    ("21시", 20, 1.8, 2.2),
]


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


def simulate_transfer_loss(rng: np.random.Generator, n: int, brt_headway: float, mu: float, sd: float, feeder_headway: float) -> tuple[float, float]:
    """
    총 체감 손실시간과 환승 실패 확률을 시뮬레이션한다.

    가정
    - 지선 지연 D ~ Gamma(시간대별 평균/표준편차)
    - 지선 배차가 길수록 지연 누적 위험이 커진다.
    - 지선-BRT 시간표가 완전히 연동되어 있지 않다고 보고 환승 여유시간은 Uniform(0, BRT배차)로 둔다.
    """
    feeder_headway = float(feeder_headway) if pd.notna(feeder_headway) else 60.0
    brt_headway = float(brt_headway)

    # 배차가 길수록 지연 누적 위험이 커지되, 극단값 영향을 줄이기 위해 120분에서 상한.
    accumulation = 1.0 + 0.018 * min(max(feeder_headway, 0), 120)
    mean_delay = max(mu * accumulation, 0.01)
    sd_delay = max(sd * accumulation, 0.01)

    shape = (mean_delay / sd_delay) ** 2
    scale = (sd_delay ** 2) / mean_delay
    delay = rng.gamma(shape, scale, n)

    buffer = rng.uniform(0, brt_headway, n)
    fail = delay > buffer
    extra_wait = np.where(fail, brt_headway - ((delay - buffer) % brt_headway), 0.0)
    return float((delay + extra_wait).mean()), float(fail.mean())


def select_stops(g: pd.DataFrame, top_e: int, top_d: int, pick: list[str] | None) -> pd.DataFrame:
    """히트맵 대상 정류장 선택. 기본은 E등급 상위 + D등급 상위."""
    if pick:
        found = g[g["정류소명"].isin(pick)].copy()
        missing = [name for name in pick if name not in set(found["정류소명"])]
        if missing:
            print(f"[경고] 분석 결과에서 찾지 못한 정류장명: {missing}")
        if found.empty:
            raise ValueError("--pick으로 지정한 정류장을 하나도 찾지 못했습니다.")
        order = {name: i for i, name in enumerate(pick)}
        found["_order"] = found["정류소명"].map(order)
        return found.drop_duplicates("정류소명").sort_values("_order")

    env = g[~g["BRT경유"]].copy()
    sort_cols = ["취약도점수", "대표배차분", "최근접BRT_m"]
    e = env[env["등급"] == "E"].sort_values(sort_cols, ascending=False).head(top_e)
    d = env[env["등급"] == "D"].sort_values(sort_cols, ascending=False).head(top_d)
    selected = pd.concat([e, d], axis=0)

    if selected.empty:
        selected = env.sort_values(sort_cols, ascending=False).head(top_e + top_d)
    return selected.drop_duplicates("정류소명")


def validate_heatmap_selection(selected: pd.DataFrame, top_e: int, top_d: int) -> None:
    names = selected["정류소명"].tolist()
    if len(names) != top_e + top_d:
        raise ValueError(f"히트맵 행 수 오류: {len(names)}행 (기대 {top_e + top_d}행)")
    if names != EXPECTED_HEATMAP_STOPS:
        raise ValueError(
            "히트맵 정류장 순서/구성이 기대와 다릅니다.\n"
            f"  기대: {EXPECTED_HEATMAP_STOPS}\n"
            f"  실제: {names}\n"
            "  → merge_directions.py 실행 후 다시 시도하세요."
        )
    grades = selected["등급"].tolist()
    if grades[:top_e] != ["E"] * top_e or grades[top_e:] != ["D"] * top_d:
        raise ValueError(f"E/D 등급 구분 오류: {grades}")


def make_heatmap(output_dir: Path, n: int, seed: int, top_e: int, top_d: int, pick: list[str] | None) -> tuple[Path, Path]:
    set_korean_font()
    output_dir.mkdir(parents=True, exist_ok=True)
    g = load_analysis_df(output_dir)
    required = {"정류소ID", "정류소명", "동", "등급", "대표배차분", "취약도점수", "BRT경유"}
    missing = sorted(required - set(g.columns))
    if missing:
        raise ValueError(f"분석 결과에 필요한 컬럼이 없습니다: {missing}")

    selected = select_stops(g, top_e=top_e, top_d=top_d, pick=pick)
    if pick is None:
        validate_heatmap_selection(selected, top_e, top_d)
    if selected.empty:
        raise ValueError("히트맵 대상 정류장이 없습니다.")

    rng = np.random.default_rng(seed)
    risk = np.zeros((len(selected), len(HOURS)))
    fail_prob = np.zeros_like(risk)

    for i, (_, row) in enumerate(selected.iterrows()):
        feeder_headway = row["대표배차분"]
        for j, (_, brt_hw, mu, sd) in enumerate(HOURS):
            risk[i, j], fail_prob[i, j] = simulate_transfer_loss(rng, n, brt_hw, mu, sd, feeder_headway)

    stop_names = selected["정류소명"].tolist()
    hour_labels = [h[0] for h in HOURS]
    risk_df = pd.DataFrame(risk.round(2), index=stop_names, columns=hour_labels)
    fail_df = pd.DataFrame(fail_prob.round(4), index=stop_names, columns=hour_labels)

    risk_csv = output_dir / "heatmap_final.csv"
    fail_csv = output_dir / "heatmap_fail_probability_final.csv"
    risk_csv = safe_to_csv(risk_df, risk_csv, encoding="utf-8-sig")
    fail_csv = safe_to_csv(fail_df, fail_csv, encoding="utf-8-sig")

    print("[총 체감 손실시간, 분]")
    print(risk_df.round(1).to_string())
    print("\n[시간대별 평균 환승 실패 확률]")
    print(pd.Series(fail_prob.mean(axis=0).round(3), index=hour_labels).to_string())

    labels = []
    for _, row in selected.iterrows():
        dong = row.get("동", "")
        grade = row.get("등급", "")
        headway = row.get("대표배차분", np.nan)
        score = row.get("취약도점수", np.nan)
        labels.append(f"{row['정류소명']}\n({dong}·{grade}등급·배차{headway:.0f}분·점수{score:.2f})")

    cmap = LinearSegmentedColormap.from_list(
        "transfer_risk",
        ["#F4F7F9", "#FCE9C8", "#F5B041", "#E67E22", "#C0392B", "#7B241C"],
    )

    fig, ax = plt.subplots(figsize=(14, 11), dpi=220)
    vmax = max(float(np.nanmax(risk)), 1.0)
    im = ax.imshow(risk, cmap=cmap, aspect="auto", vmin=0, vmax=vmax)

    def _row_axes_y(row_idx: float) -> float:
        y_lo, y_hi = ax.get_ylim()
        return (row_idx - y_lo) / (y_hi - y_lo)

    ax.set_xticks(range(len(hour_labels)))
    ax.set_xticklabels(hour_labels, fontsize=11.5)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9.0, linespacing=1.28)
    ax.tick_params(top=True, bottom=False, labeltop=True, labelbottom=False, length=0, pad=6)

    for i in range(len(selected)):
        for j in range(len(hour_labels)):
            value = risk[i, j]
            ax.text(
                j, i, f"{value:.0f}", ha="center", va="center", fontsize=9.8,
                color="white" if value > vmax * 0.55 else "#333333",
                fontweight="bold" if value > vmax * 0.70 else "normal",
            )

    # 출퇴근 피크 구간 강조 (컬럼 헤더 바로 위)
    for j in [1, 2, 3, 6, 7, 8]:
        ax.axvspan(j - 0.5, j + 0.5, color="#C0392B", alpha=0.043, zorder=0)
    for j, text in [(2, "출근 피크"), (7, "퇴근 피크")]:
        ax.text(j, -0.8, text, ha="center", va="bottom", fontsize=9.8, fontweight="bold", color="#C0392B", clip_on=False)

    # E와 D 사이 구분선 및 좌측 등급 라벨 (axes 좌표, y축 라벨 왼쪽)
    grades = selected["등급"].tolist()
    n_rows = len(selected)
    if "E" in grades and "D" in grades:
        last_e = max(i for i, grd in enumerate(grades) if grd == "E")
        ax.axhline(last_e + 0.5, color="#555555", lw=1.35, ls="--")
        ax.text(
            -0.30, _row_axes_y(last_e / 2), "E등급\n최우선 개선",
            transform=ax.transAxes, ha="right", va="center",
            fontsize=9.0, fontweight="bold", color="#C0392B", linespacing=1.35, clip_on=False,
        )
        d_center = (last_e + 1 + n_rows - 1) / 2
        ax.text(
            -0.30, _row_axes_y(d_center), "D등급\n교통약자 취약",
            transform=ax.transAxes, ha="right", va="center",
            fontsize=9.0, fontweight="bold", color="#E67E22", linespacing=1.35, clip_on=False,
        )

    cb = fig.colorbar(im, ax=ax, fraction=0.022, pad=0.028)
    cb.set_label("총 체감 손실시간(분)", fontsize=10, rotation=270, labelpad=18)
    cb.ax.tick_params(labelsize=9.0)

    ax.set_title("시간대별 BRT 환승 실패 위험도 분석", fontsize=16.5, fontweight="bold", pad=60)
    fig.text(
        0.5, 0.93,
        "지선버스 지연 → BRT 환승 실패 → 추가 대기 / 숫자 = 총 체감 손실시간(분)",
        ha="center", fontsize=10.5, color="#555555",
    )
    fig.text(
        0.5, 0.014,
        "※ 배차간격은 운행 현황 기반. 지연 분포와 환승 여유시간은 시뮬레이션 가정이며, TAGO 실시간 도착 데이터 수집 후 실측치로 대체 가능.",
        ha="center", fontsize=8.3, color="#999999", style="italic",
    )

    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.subplots_adjust(left=0.28, right=0.88, top=0.88, bottom=0.10)
    out_img = output_dir / "heatmap_final.png"
    try:
        plt.savefig(out_img, dpi=220, bbox_inches="tight", facecolor="white")
    except PermissionError:
        out_img = output_dir / "heatmap_final_new.png"
        plt.savefig(out_img, dpi=220, bbox_inches="tight", facecolor="white")
        print(f"[경고] heatmap_final.png가 열려 있어 {out_img.name}으로 저장했습니다.")
    plt.close(fig)
    print(f"\nsaved {out_img.resolve()}")
    return out_img, risk_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="정류장 × 시간대별 BRT 환승 실패 위험도 히트맵 생성")
    parser.add_argument("--output-dir", default="output", type=Path, help="analysis_final.py 결과 폴더")
    parser.add_argument("--n", default=30000, type=int, help="정류장·시간대별 시뮬레이션 반복 횟수")
    parser.add_argument("--seed", default=42, type=int, help="난수 시드")
    parser.add_argument("--top-e", default=7, type=int, help="자동 선택 시 E등급 상위 정류장 수")
    parser.add_argument("--top-d", default=5, type=int, help="자동 선택 시 D등급 상위 정류장 수")
    parser.add_argument(
        "--pick",
        default="",
        help="직접 지정할 정류장명. 쉼표로 구분. 예: 전동초등학교,소정리역,연서중학교",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    pick = [x.strip() for x in args.pick.split(",") if x.strip()] or None
    make_heatmap(args.output_dir, args.n, args.seed, args.top_e, args.top_d, pick)
