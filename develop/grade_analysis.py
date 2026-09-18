# -*- coding: utf-8 -*-
"""세종시 BRT 환승·대기 취약도 등급 산출 (실데이터 기반, 절대 기준)"""
import pandas as pd, numpy as np, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'

R = 6371.0
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return 2*R*np.arcsin(np.sqrt(a))

# ── 데이터 로드 ──────────────────────────────────────
stops = pd.read_csv(DATA_DIR / 'bus_stops.csv', encoding='utf-8')
hosp  = pd.read_csv(DATA_DIR / 'hospitals.csv', encoding='cp949')
sch   = pd.read_csv(DATA_DIR / 'schools.csv', encoding='cp949')

def extract_dong(addr):
    if pd.isna(addr): return None
    s = str(addr)
    m = re.search(r'\(([가-힣0-9]+[동읍면])\s*[,)]', s)
    if m: return m.group(1)
    m = re.search(r'세종특별자치시\s+(\S+[읍면동])', s)
    if m: return m.group(1)
    return None

hosp['dong'] = hosp['의료기관주소(도로명)'].apply(extract_dong)
sch['dong']  = sch['지역']

# ── 동 센트로이드 (정류장명 기반 도출) ─────────────────
ust = stops.drop_duplicates('정류소ID')[['정류소ID','정류소명','위도','경도']].copy()
all_dongs = sorted(set(hosp['dong'].dropna()) | set(sch['dong'].dropna()))
STEM = {'아름동':'아름','전의면':'전의','조치원읍':'조치원','종촌동':'종촌','해밀동':'해밀'}
MANUAL = {'산울동': (36.5250, 127.2570), '어진동': (36.5037, 127.2602)}  # 어진동=정부세종청사

centroids = {}
for d in all_dongs:
    if d in MANUAL:
        centroids[d] = MANUAL[d]; continue
    key = STEM.get(d, d)
    m = ust[ust['정류소명'].str.contains(key, na=False, regex=False)]
    if len(m):
        centroids[d] = (m['위도'].mean(), m['경도'].mean())
cent_df = pd.DataFrame([(d, la, lo) for d, (la, lo) in centroids.items()],
                       columns=['dong','lat','lon'])

# ── 동별 교통약자 시설 수 ──────────────────────────────
fac = (hosp['dong'].value_counts().rename('병원')
       .to_frame().join(sch['dong'].value_counts().rename('학교'), how='outer')
       .fillna(0).astype(int))
fac['시설합'] = fac['병원'] + fac['학교']

# ── 정류장별 지표 ─────────────────────────────────────
BRT_ROUTES = {'B0','B2','B5'}
routes_per_stop = stops.groupby('정류소ID')['노선번호'].apply(lambda s: set(s.astype(str)))
df = ust.set_index('정류소ID')
df['노선들'] = routes_per_stop
df['노선수'] = df['노선들'].apply(len)
df['BRT경유'] = df['노선들'].apply(lambda s: len(s & BRT_ROUTES) > 0)
df['지선노선수'] = df['노선들'].apply(lambda s: len(s - BRT_ROUTES))

# 최근접 BRT 정류장 거리
brt_stops = df[df['BRT경유']][['위도','경도']].values
lat = df['위도'].values[:, None]; lon = df['경도'].values[:, None]
dists = haversine(lat, lon, brt_stops[:,0][None,:], brt_stops[:,1][None,:])
df['BRT최근접거리km'] = dists.min(axis=1)

# 정류장 → 최근접 동 → 동 시설 수
clat = cent_df['lat'].values[None,:]; clon = cent_df['lon'].values[None,:]
dc = haversine(lat, lon, clat, clon)
df['동'] = cent_df['dong'].values[dc.argmin(axis=1)]
df['동까지km'] = dc.min(axis=1)
df = df.join(fac, on='동')
df[['병원','학교','시설합']] = df[['병원','학교','시설합']].fillna(0).astype(int)
# 동 센트로이드에서 1.2km 이상 떨어진 정류장(외곽)은 시설 인접 아님으로 처리
FAC_RADIUS = 1.2
df.loc[df['동까지km'] > FAC_RADIUS, ['병원','학교','시설합']] = 0

# ── 취약도 점수 (0~1 정규화 후 가중합) ──────────────────
# 1) 환승 부담: 최근접 BRT 거리 (2km 상한)
df['환승부담'] = np.clip(df['BRT최근접거리km'] / 2.0, 0, 1)
# 2) 대안 부족: 경유 노선 수 역수 (1개 노선=1.0, 2개=0.5 ...)
df['대안부족'] = 1.0 / df['노선수']
# 3) 교통약자 인접: 동 시설 수 로그 정규화
df['약자인접'] = np.log1p(df['시설합']) / np.log1p(df['시설합'].max())

df['취약도점수'] = (0.35*df['환승부담'] + 0.30*df['대안부족'] + 0.35*df['약자인접']).round(3)

# ── 등급: 정책 의미 기반 절대 기준 ──────────────────────
def grade(r):
    # 환승 의존: BRT 미경유 + 최근접 BRT 1km 이상 → 지선-BRT 환승 필수 구간
    transfer_dep = (not r['BRT경유']) and (r['환승부담'] >= 0.5)
    # 대안 부족: 이용 가능 노선 1개 → 한 번 놓치면 대체 수단 없음
    no_alt = (r['노선수'] == 1)
    few_alt = (r['노선수'] <= 2)
    # 교통약자 시설 인접: 시설 밀집 생활권(병원+학교 10개 이상) 1.2km 이내
    fac_adj = (r['시설합'] >= 10)
    if transfer_dep and no_alt and fac_adj:   return 'E'  # 3중 취약: 최우선 개선
    if fac_adj and no_alt:                     return 'D'  # 교통약자 대기 취약
    if transfer_dep and no_alt:                return 'C'  # 환승 실패 위험(대안 없음)
    if transfer_dep or no_alt:                 return 'B'  # 일부 불안정
    return 'A'
df['등급'] = df.apply(grade, axis=1)

print(df['등급'].value_counts().sort_index())
print()
print('E등급 상위 10:')
top = df[df['등급']=='E'].sort_values('취약도점수', ascending=False)
print(top[['정류소명','동','노선수','BRT최근접거리km','시설합','취약도점수']].head(10).to_string())
print()
print('D등급 상위 5:')
topd = df[df['등급']=='D'].sort_values('취약도점수', ascending=False)
print(topd[['정류소명','동','노선수','BRT최근접거리km','시설합','취약도점수']].head(5).to_string())

df.drop(columns=['노선들']).to_csv(BASE_DIR / 'stop_grades.csv', encoding='utf-8-sig')
print('\n저장: stop_grades.csv')
