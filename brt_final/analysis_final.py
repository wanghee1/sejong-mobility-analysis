# -*- coding: utf-8 -*-
"""
세종시 BRT 환승권역별 환승·대기 취약도 등급 산출 최종본

목적
- BRT 직접 이용이 어려워 지선 환승이 필요한 정류장을 대상으로 개선 우선순위를 산출한다.
- 분위수 기반 상대평가가 아니라, 발표에서 설명 가능한 절대 기준으로 A~E 등급을 부여한다.

입력 파일 기본 위치
- ./data/bus_stops.csv
- ./data/세종특별자치시__버스운행_현황_20250527.csv
- ./data/한국교육시설안전원_초중등학교위치_20260320.csv
- ./data/hospitals.csv

출력 파일 기본 위치
- ./output/g.pkl
- ./output/stop_grades_final.csv
- ./output/priority_top20_final.csv
- ./output/analysis_summary_final.txt

주요 보완점
1) Claude 전용 절대경로 제거 → 상대경로/인자 기반 실행
2) 평균배차의 과대평가 문제 보완 → 기본값은 지선노선 합산배차(combined_feeder)
3) 병의원 지표의 한계 명시 → 좌표가 있으면 500m 반경, 없으면 행정동 단위 보조지표 사용
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


DEFAULT_FILES = {
    "stops": "bus_stops.csv",
    "operation": "세종특별자치시__버스운행_현황_20250527.csv",
    "schools": "한국교육시설안전원_초중등학교위치_20260320.csv",
    "hospitals": "hospitals.csv",
}

BRT_ROUTE_FALLBACK = {"B0", "B2", "B3", "B4", "B5"}

POLICY = {
    "A": "현행 유지 및 정기 모니터링",
    "B": "출퇴근·등하교 시간대 집중 모니터링",
    "C": "지선-BRT 환승 시간표 보정, 배차간격 조정",
    "D": "쉘터·의자·안내정보 등 대기환경 우선 개선",
    "E": "배차 조정 + 두루타버스 연계 + 정류장 개선 패키지",
}

GRADE_ORDER = {"E": 5, "D": 4, "C": 3, "B": 2, "A": 1}


def read_csv_auto(path: Path, encodings: Sequence[str] = ("utf-8-sig", "utf-8", "cp949", "euc-kr")) -> pd.DataFrame:
    """여러 인코딩을 순차적으로 시도해 CSV를 읽는다."""
    if not path.exists():
        raise FileNotFoundError(f"입력 파일이 없습니다: {path}")

    errors: list[str] = []
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError as exc:
            errors.append(f"{enc}: {exc}")
    raise UnicodeDecodeError("csv", b"", 0, 1, f"인코딩 판별 실패: {path}\n" + "\n".join(errors))


def require_columns(df: pd.DataFrame, cols: Iterable[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{name}에 필요한 컬럼이 없습니다: {missing}\n현재 컬럼: {list(df.columns)}")


def normalize_route(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    # CSV에서 100.0처럼 읽힌 노선번호를 100으로 보정한다.
    s = re.sub(r"\.0$", "", s)
    return s


def haversine_m(lat1, lon1, lat2, lon2):
    """위경도 배열 간 거리(m). broadcasting 지원."""
    radius = 6_371_000.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * radius * np.arcsin(np.sqrt(a))


def parse_interval(x):
    """'8~12분', '15-20', '60' 등에서 평균 배차와 변동폭을 추출."""
    if pd.isna(x):
        return np.nan, np.nan
    nums = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", str(x))]
    if not nums:
        return np.nan, np.nan
    if len(nums) >= 2:
        lo, hi = min(nums[:2]), max(nums[:2])
        return (lo + hi) / 2, hi - lo
    return nums[0], 0.0


def parse_runs(x):
    """운행횟수에서 숫자만 추출."""
    if pd.isna(x):
        return np.nan
    nums = re.findall(r"\d+(?:\.\d+)?", str(x))
    return float(nums[0]) if nums else np.nan


def safe_mean(values: list[float], fallback: float) -> float:
    arr = np.array([v for v in values if pd.notna(v) and np.isfinite(v) and v > 0], dtype=float)
    return float(arr.mean()) if len(arr) else float(fallback)


def safe_min(values: list[float], fallback: float) -> float:
    arr = np.array([v for v in values if pd.notna(v) and np.isfinite(v) and v > 0], dtype=float)
    return float(arr.min()) if len(arr) else float(fallback)


def safe_max(values: list[float], fallback: float) -> float:
    arr = np.array([v for v in values if pd.notna(v) and np.isfinite(v) and v >= 0], dtype=float)
    return float(arr.max()) if len(arr) else float(fallback)


def combined_headway(values: list[float], fallback: float) -> float:
    """
    여러 노선이 독립적으로 도착한다고 볼 때의 유효/합산 배차.

    공식: H = 1 / Σ(1 / h_i)
    - h_i: i번 노선의 배차간격
    - 노선이 늘어날수록 체감 배차가 짧아지는 방향으로 계산된다.
    - 모든 값이 결측이면 fallback을 사용한다.
    """
    arr = np.array([v for v in values if pd.notna(v) and np.isfinite(v) and v > 0], dtype=float)
    return float(1.0 / np.sum(1.0 / arr)) if len(arr) else float(fallback)


def route_values(routes: list[str], mapping: dict[str, float], fallback: float) -> list[float]:
    return [float(mapping.get(r, fallback)) for r in routes if r]


def select_representative_headway(row: pd.Series, basis: str) -> float:
    if basis == "combined_feeder":
        return row["지선합산배차분"]
    if basis == "mean_feeder":
        return row["지선평균배차분"]
    if basis == "min_feeder":
        return row["지선최소배차분"]
    if basis == "max_feeder":
        return row["지선최대배차분"]
    if basis == "min_any":
        return row["최소배차분_전체"]
    if basis == "mean_any":
        return row["평균배차분_전체"]
    if basis == "combined_any":
        return row["합산배차분_전체"]
    raise ValueError(f"지원하지 않는 headway_basis입니다: {basis}")


def extract_dong(addr) -> str | None:
    """주소에서 읍/면/동 추출."""
    if pd.isna(addr):
        return None
    s = str(addr)
    # 괄호 안 행정동: 예) 세종시 ... (어진동)
    m = re.search(r"\(([가-힣0-9]+[동읍면])\s*[,)]", s)
    if m:
        return m.group(1)
    # 도로명 주소 앞부분: 예) 세종특별자치시 조치원읍 ...
    m = re.search(r"세종특별자치시\s+([가-힣0-9]+[읍면동])", s)
    return m.group(1) if m else None


def find_address_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if "주소" in col:
            return col
    return None


def add_hospital_access(g: pd.DataFrame, hosp: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """
    병의원 접근성 추가.
    - 병의원 데이터에 위도/경도 컬럼이 있으면 정류장 반경 500m 병의원 수를 사용한다.
    - 좌표가 없으면 주소에서 읍/면/동을 추출해 행정동 단위 보조지표로 사용한다.
    """
    lat = g["위도"].to_numpy()[:, None]
    lon = g["경도"].to_numpy()[:, None]

    if {"위도", "경도"}.issubset(hosp.columns):
        hcoord = hosp.dropna(subset=["위도", "경도"])
        if len(hcoord):
            dist = haversine_m(lat, lon, hcoord["위도"].to_numpy()[None, :], hcoord["경도"].to_numpy()[None, :])
            g["반경500m_병의원수"] = (dist <= 500).sum(axis=1)
            g["동"] = "좌표기반"
            g["동거리m"] = np.nan
            g["동_병의원수"] = 0
            g["병의원인접"] = g["반경500m_병의원수"] >= 1
            return g, "좌표 기반 500m 반경 병의원 수"

    addr_col = find_address_col(hosp)
    if addr_col is None:
        g["반경500m_병의원수"] = 0
        g["동"] = "미상"
        g["동거리m"] = np.nan
        g["동_병의원수"] = 0
        g["병의원인접"] = False
        return g, "병의원 주소/좌표 부재로 미반영"

    hosp = hosp.copy()
    hosp["dong"] = hosp[addr_col].apply(extract_dong)
    hcnt = hosp["dong"].dropna().value_counts()
    if hcnt.empty:
        g["반경500m_병의원수"] = 0
        g["동"] = "미상"
        g["동거리m"] = np.nan
        g["동_병의원수"] = 0
        g["병의원인접"] = False
        return g, "주소에서 행정동 추출 실패로 미반영"

    # 행정동 중심점은 정류장명 매칭 평균좌표로 근사한다. 매칭이 어려운 일부 동은 수동 좌표를 사용한다.
    stem = {"아름동": "아름", "전의면": "전의", "조치원읍": "조치원", "종촌동": "종촌", "해밀동": "해밀"}
    manual = {
        "산울동": (36.5250, 127.2570),
        "어진동": (36.5037, 127.2602),
        "나성동": (36.4896, 127.2588),
        "소담동": (36.4853, 127.3007),
    }

    centroids = []
    for dong_name in hcnt.index:
        if dong_name in manual:
            centroids.append((dong_name, *manual[dong_name]))
            continue
        key = stem.get(dong_name, dong_name)
        matched = g[g["정류소명"].astype(str).str.contains(key, na=False, regex=False)]
        if len(matched):
            centroids.append((dong_name, float(matched["위도"].mean()), float(matched["경도"].mean())))

    if not centroids:
        g["반경500m_병의원수"] = 0
        g["동"] = "미상"
        g["동거리m"] = np.nan
        g["동_병의원수"] = 0
        g["병의원인접"] = False
        return g, "행정동 중심점 근사 실패로 미반영"

    cdf = pd.DataFrame(centroids, columns=["dong", "lat", "lon"])
    dist_to_dong = haversine_m(lat, lon, cdf["lat"].to_numpy()[None, :], cdf["lon"].to_numpy()[None, :])
    nearest_idx = dist_to_dong.argmin(axis=1)

    g["동"] = cdf["dong"].to_numpy()[nearest_idx]
    g["동거리m"] = dist_to_dong.min(axis=1)
    g["동_병의원수"] = g["동"].map(hcnt).fillna(0).astype(int)
    # 동 중심점과 너무 멀면 해당 행정동 의료 접근성으로 보기 어렵다고 처리한다.
    g.loc[g["동거리m"] > 1200, "동_병의원수"] = 0
    g["반경500m_병의원수"] = 0
    g["병의원인접"] = g["동_병의원수"] >= 10
    return g, "행정동 단위 병의원 수 보조지표"


def build_analysis(data_dir: Path, output_dir: Path, headway_basis: str) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)

    stops = read_csv_auto(data_dir / DEFAULT_FILES["stops"])
    op = read_csv_auto(data_dir / DEFAULT_FILES["operation"])
    schools = read_csv_auto(data_dir / DEFAULT_FILES["schools"])
    hospitals = read_csv_auto(data_dir / DEFAULT_FILES["hospitals"])

    require_columns(stops, ["정류소ID", "정류소명", "위도", "경도", "노선번호"], "bus_stops.csv")
    require_columns(op, ["노선번호", "구분"], "버스운행 현황")
    require_columns(schools, ["위도", "경도"], "초중등학교 위치")

    if "배차간격" not in op.columns and "운행횟수" not in op.columns:
        raise ValueError("버스운행 현황 파일에 '배차간격' 또는 '운행횟수' 컬럼이 필요합니다.")

    stops = stops.copy()
    op = op.copy()
    schools = schools.copy()

    stops["노선번호"] = stops["노선번호"].apply(normalize_route)
    op["노선번호"] = op["노선번호"].apply(normalize_route)

    if "배차간격" in op.columns:
        parsed = op["배차간격"].apply(parse_interval)
        op["배차평균"], op["배차폭"] = zip(*parsed)
    else:
        op["배차평균"] = np.nan
        op["배차폭"] = np.nan

    if "운행횟수" in op.columns:
        op["운행횟수n"] = op["운행횟수"].apply(parse_runs)
        op["배차추정"] = np.where(op["운행횟수n"] > 0, 960.0 / op["운행횟수n"], np.nan)  # 06~22시 960분 가정
    else:
        op["운행횟수n"] = np.nan
        op["배차추정"] = np.nan

    op["배차분"] = op["배차평균"].fillna(op["배차추정"])
    op.loc[op["배차분"] <= 0, "배차분"] = np.nan
    op["배차폭"] = op["배차폭"].fillna(0.0)

    med_by_type = op.groupby("구분")["배차분"].median()
    overall_median = float(op["배차분"].median()) if pd.notna(op["배차분"].median()) else 60.0
    op["배차분"] = op["배차분"].fillna(op["구분"].map(med_by_type)).fillna(overall_median)

    hw = dict(zip(op["노선번호"], op["배차분"]))
    hww = dict(zip(op["노선번호"], op["배차폭"]))

    brt_mask = op["구분"].astype(str).str.upper().str.contains("BRT", na=False)
    brt_routes = set(op.loc[brt_mask, "노선번호"])
    if not brt_routes:
        brt_routes = {r for r in op["노선번호"] if r in BRT_ROUTE_FALLBACK}
    if not brt_routes:
        raise ValueError("BRT 노선 식별 실패: 버스운행 현황의 '구분' 컬럼 또는 BRT_ROUTE_FALLBACK을 확인하세요.")

    grouped = stops.groupby("정류소ID", as_index=False).agg(
        정류소명=("정류소명", "first"),
        위도=("위도", "mean"),
        경도=("경도", "mean"),
        노선들=("노선번호", lambda s: sorted({normalize_route(v) for v in s if normalize_route(v)})),
    )
    g = grouped.copy()
    g["BRT경유"] = g["노선들"].apply(lambda routes: len(set(routes) & brt_routes) > 0)
    g["노선수"] = g["노선들"].apply(len)
    g["지선노선"] = g["노선들"].apply(lambda routes: [r for r in routes if r not in brt_routes])

    def feeder_or_all(routes: list[str], feeders: list[str]) -> list[str]:
        return feeders if feeders else routes

    g["최소배차분_전체"] = g["노선들"].apply(lambda rs: safe_min(route_values(rs, hw, overall_median), overall_median))
    g["평균배차분_전체"] = g["노선들"].apply(lambda rs: safe_mean(route_values(rs, hw, overall_median), overall_median))
    g["최대배차분_전체"] = g["노선들"].apply(lambda rs: safe_max(route_values(rs, hw, overall_median), overall_median))
    g["합산배차분_전체"] = g["노선들"].apply(lambda rs: combined_headway(route_values(rs, hw, overall_median), overall_median))

    g["지선최소배차분"] = g.apply(
        lambda r: safe_min(route_values(feeder_or_all(r["노선들"], r["지선노선"]), hw, overall_median), overall_median),
        axis=1,
    )
    g["지선평균배차분"] = g.apply(
        lambda r: safe_mean(route_values(feeder_or_all(r["노선들"], r["지선노선"]), hw, overall_median), overall_median),
        axis=1,
    )
    g["지선합산배차분"] = g.apply(
        lambda r: combined_headway(route_values(feeder_or_all(r["노선들"], r["지선노선"]), hw, overall_median), overall_median),
        axis=1,
    )
    g["지선최대배차분"] = g.apply(
        lambda r: safe_max(route_values(feeder_or_all(r["노선들"], r["지선노선"]), hw, overall_median), overall_median),
        axis=1,
    )
    g["대표배차분"] = g.apply(lambda r: select_representative_headway(r, headway_basis), axis=1)
    g["최대배차폭"] = g.apply(
        lambda r: safe_max(route_values(feeder_or_all(r["노선들"], r["지선노선"]), hww, 0.0), 0.0),
        axis=1,
    )
    g["배차기준"] = headway_basis

    brt_coords = g.loc[g["BRT경유"], ["위도", "경도"]].to_numpy()
    if len(brt_coords) == 0:
        raise ValueError("BRT 경유 정류장이 0개입니다. BRT 노선 식별 또는 정류장 노선번호를 확인하세요.")

    lat = g["위도"].to_numpy()[:, None]
    lon = g["경도"].to_numpy()[:, None]
    g["최근접BRT_m"] = haversine_m(lat, lon, brt_coords[:, 0][None, :], brt_coords[:, 1][None, :]).min(axis=1)

    # 학교 접근성: 실제 좌표 기반 500m 반경
    school_addr_col = find_address_col(schools)
    if school_addr_col:
        schools_sj = schools[schools[school_addr_col].astype(str).str.contains("세종", na=False)]
    else:
        schools_sj = schools
    schools_sj = schools_sj.dropna(subset=["위도", "경도"])
    if len(schools_sj):
        school_dist = haversine_m(
            lat,
            lon,
            schools_sj["위도"].to_numpy()[None, :],
            schools_sj["경도"].to_numpy()[None, :],
        )
        g["반경500m_학교수"] = (school_dist <= 500).sum(axis=1)
    else:
        g["반경500m_학교수"] = 0

    g, hospital_method = add_hospital_access(g, hospitals)
    g["병의원산정방식"] = hospital_method

    # 3대 조건: 정책적으로 설명 가능한 절대 기준
    g["지선환승필수"] = (~g["BRT경유"]) & (g["최근접BRT_m"] > 500)  # 도보 환승 불가권역
    g["대기취약"] = (~g["BRT경유"]) & (g["대표배차분"] >= 30)      # 30분 이상 배차
    g["대기심각"] = (~g["BRT경유"]) & (g["대표배차분"] >= 60)      # 60분 이상 배차
    g["약자인접"] = (g["반경500m_학교수"] >= 1) | g["병의원인접"]

    # 점수: 제안서 원안 가중치에서 시설취약 15% 제외 후 85% 재정규화
    g["환승위험"] = np.where(g["BRT경유"], 0.0, np.clip(g["최근접BRT_m"] / 2000.0, 0, 1))
    g["도착불안정"] = (
        np.clip(g["대표배차분"] / 60.0, 0, 1) * 0.7
        + np.clip(g["최대배차폭"] / 20.0, 0, 1) * 0.3
    )

    if hospital_method.startswith("좌표 기반"):
        hospital_score = np.clip(g["반경500m_병의원수"] / 3.0, 0, 1)
    else:
        max_hosp = max(float(g["동_병의원수"].max()), 1.0)
        hospital_score = np.log1p(g["동_병의원수"]) / np.log1p(max_hosp)
    g["약자인접도"] = np.clip((g["반경500m_학교수"] / 3.0) * 0.6 + hospital_score * 0.4, 0, 1)

    weights = {"도착불안정": 0.30 / 0.85, "환승위험": 0.30 / 0.85, "약자인접도": 0.25 / 0.85}
    g["취약도점수"] = sum(g[col] * weight for col, weight in weights.items()).round(3)

    def grade(row: pd.Series) -> str:
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

    g["등급"] = g.apply(grade, axis=1)
    g["정책처방"] = g["등급"].map(POLICY)
    g["등급가중치"] = g["등급"].map(GRADE_ORDER)

    env_mask = ~g["BRT경유"]
    sort_cols = ["등급가중치", "취약도점수", "대표배차분", "최근접BRT_m", "약자인접도"]
    sorted_env_idx = g.loc[env_mask].sort_values(sort_cols, ascending=False).index
    g["개선우선순위"] = np.nan
    g.loc[sorted_env_idx, "개선우선순위"] = np.arange(1, len(sorted_env_idx) + 1)
    g["개선우선순위"] = g["개선우선순위"].astype("Int64")

    # CSV 저장용 문자열 컬럼
    csv_g = g.copy()
    csv_g["노선들"] = csv_g["노선들"].apply(lambda x: ",".join(x))
    csv_g["지선노선"] = csv_g["지선노선"].apply(lambda x: ",".join(x))

    csv_g.to_csv(output_dir / "stop_grades_final.csv", index=False, encoding="utf-8-sig")
    # protocol=4: Python 3.7+ 호환 (3.11 기본 protocol 5는 3.7에서 읽을 수 없음)
    g.to_pickle(output_dir / "g.pkl", protocol=4)

    top_cols = [
        "개선우선순위", "정류소명", "동", "등급", "취약도점수", "대표배차분", "최근접BRT_m",
        "반경500m_학교수", "반경500m_병의원수", "동_병의원수", "정책처방",
    ]
    # TOP20은 양방향 정류소ID 중복을 제거해, 실제 지점 기준 20개가 나오도록 정류소명 기준으로 접는다.
    top20 = g.loc[env_mask].sort_values("개선우선순위").drop_duplicates("정류소명").head(20)[top_cols].copy()
    top20["개선우선순위"] = np.arange(1, len(top20) + 1)
    top20.to_csv(output_dir / "priority_top20_final.csv", index=False, encoding="utf-8-sig")

    summary_lines = []
    summary_lines.append("[세종시 BRT 환승권역별 환승·대기 취약도 등급 산출 결과]")
    summary_lines.append(f"배차 기준: {headway_basis}")
    summary_lines.append(f"병의원 산정 방식: {hospital_method}")
    summary_lines.append("")
    summary_lines.append("등급 분포")
    summary_lines.append(g["등급"].value_counts().sort_index().to_string())
    summary_lines.append("")
    summary_lines.append(f"BRT 직결 정류장: {int(g['BRT경유'].sum())}개")
    summary_lines.append(f"BRT 환승권역 정류장: {int((~g['BRT경유']).sum())}개")
    summary_lines.append(f"지선환승필수: {int(g['지선환승필수'].sum())}개")
    summary_lines.append(f"대기취약(대표배차 30분 이상): {int(g['대기취약'].sum())}개")
    summary_lines.append(f"대기심각(대표배차 60분 이상): {int(g['대기심각'].sum())}개")
    summary_lines.append(f"약자인접: {int(g['약자인접'].sum())}개")
    summary_lines.append("")
    summary_lines.append("개선 우선순위 TOP 20")
    summary_lines.append(top20.round({"취약도점수": 3, "대표배차분": 1, "최근접BRT_m": 1}).to_string(index=False))
    (output_dir / "analysis_summary_final.txt").write_text("\n".join(summary_lines), encoding="utf-8")

    print("\n".join(summary_lines))
    print(f"\n저장 완료: {output_dir.resolve()}")
    return g


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="세종시 BRT 환승권역별 환승·대기 취약도 등급 산출")
    parser.add_argument("--data-dir", default="data", type=Path, help="입력 CSV 파일이 들어 있는 폴더")
    parser.add_argument("--output-dir", default="output", type=Path, help="결과 파일 저장 폴더")
    parser.add_argument(
        "--headway-basis",
        default="combined_feeder",
        choices=["combined_feeder", "mean_feeder", "min_feeder", "max_feeder", "min_any", "mean_any", "combined_any"],
        help=(
            "등급 산정에 사용할 대표 배차 기준. "
            "combined_feeder=지선노선 합산배차(기본/권장), mean_feeder=지선노선 평균배차(민감도), "
            "min_feeder=지선노선 최소배차(민감도), max_feeder=지선노선 최대배차(민감도), "
            "min_any=전체노선 최소배차, mean_any=전체노선 평균배차, combined_any=전체노선 합산배차"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_analysis(args.data_dir, args.output_dir, args.headway_basis)
