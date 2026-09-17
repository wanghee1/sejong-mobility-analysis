# 세종시 BRT 환승 취약 정류장 도출 및 교통약자 우선 개선 정책

> 2026 세종특별자치시 데이터·AI 활용 경진대회 — 데이터 분석 정책 제안 부문

세종시 버스 공공데이터를 분석하여 BRT 환승 실패 위험이 높은 정류장과 교통약자 대기 취약 정류장을 도출하고, 데이터 기반 정책 개선 우선순위를 제안하는 분석 모델입니다.

---

## 프로젝트 구조

```
sejong_brt/
├── sejong_analysis.py     # 메인 실행 파일
├── .env                   # API 키 (직접 생성, git 제외)
├── .env.example           # .env 템플릿
├── .gitignore
├── README.md
├── data/                  # 입력 파일 데이터
│   ├── bus_stops.csv      # 세종도시교통공사 버스정류장 시설현황
│   ├── hospitals.csv      # 세종특별자치시 병의원 현황
│   └── schools.csv        # 세종특별자치시 학교급별 학교현황
└── output/                # 분석 결과물 (자동 생성)
    ├── 01_bus_routes.csv
    ├── 02_route_stops.csv
    ├── 03_arrival_info.csv
    ├── 04a_bus_stops.csv
    ├── 04b_hospitals_geocoded.csv
    ├── 04c_welfare.csv
    ├── 04d_schools_geocoded.csv
    ├── 04_vulnerability_score.csv
    ├── 05_grade_distribution.png
    ├── 06_quadrant_scatter.png
    ├── 07_top10_table.png
    ├── 07_top10_stops.csv
    └── 08_vulnerability_map.html
```

---

## 활용 데이터

| 구분 | 데이터명 | 수집 방법 | 출처 |
|---|---|---|---|
| 핵심 | 국토교통부(TAGO) 버스노선정보 | API | 공공데이터포털 |
| 핵심 | 국토교통부(TAGO) 버스도착정보 | API | 공공데이터포털 |
| 핵심 | 국토교통부(TAGO) 버스위치정보 | API | 공공데이터포털 |
| 보조 | 세종도시교통공사 버스정류장 시설현황 | CSV | 공공데이터포털 |
| 보조 | 세종특별자치시 병의원 현황 | CSV + 지오코딩 | 공공데이터포털 |
| 보조 | 세종특별자치시 장애인복지시설 현황 | API | 공공데이터포털 |
| 보조 | 세종특별자치시 학교급별 학교현황 | CSV + 지오코딩 | 공공데이터포털 |

---

## 설치 및 실행

### 1. 패키지 설치

```bash
pip install requests pandas numpy matplotlib folium python-dotenv openpyxl
```

### 2. API 키 발급

[공공데이터포털](https://www.data.go.kr) 접속 후 아래 3개 API 활용신청:

- 국토교통부_버스노선정보 조회 서비스
- 국토교통부_버스도착정보 조회 서비스
- 국토교통부_버스위치정보 조회 서비스
- 세종특별자치시_장애인복지시설 현황

> 마이페이지 → 오픈API → 개발계정 → **일반 인증키(Decoding)** 복사

### 3. .env 파일 생성

```bash
cp .env.example .env
```

`.env` 파일을 열어 발급받은 키 입력:

```
PUBLIC_DATA_PORTAL_API_KEY=발급받은_키_입력
```

### 4. 파일 데이터 준비

아래 링크에서 파일 다운로드 후 `data/` 폴더에 저장:

| 파일명 | 공공데이터포털 링크 |
|---|---|
| bus_stops.csv | https://www.data.go.kr/data/15038726/fileData.do |
| hospitals.csv | https://www.data.go.kr/data/15108031/fileData.do |
| schools.csv | https://www.data.go.kr/data/15050939/fileData.do |

### 5. 실행

```bash
python sejong_analysis.py
```

---

## 분석 흐름

```
STEP 1   버스 노선 목록 수집          TAGO API → 01_bus_routes.csv
STEP 2   노선별 경유 정류장 수집       TAGO API → 02_route_stops.csv
STEP 3   정류장별 도착예정정보 수집    TAGO API → 03_arrival_info.csv
STEP 4-1 버스정류장 시설현황 로드      bus_stops.csv (위경도 포함)
STEP 4-2 병의원 좌표 부여           hospitals.csv → 주소 내 읍·면·동 매핑
STEP 4-3 장애인복지시설 수집          API → 04c_welfare.csv
STEP 4-4 학교 좌표 부여               schools.csv → 주소 내 읍·면·동 매핑
STEP 5   위경도 정규화                세종시 범위 필터링
STEP 6   반경 500m 내 시설 수 계산    Haversine 거리 계산
STEP 7   도착정보 통계 산출           95퍼센타일 대기시간, 배차간격 변동계수
STEP 8   BRT 환승 실패 위험도 산출
STEP 9   취약도 점수 산출 및 A~E 등급화
STEP 10  등급별 분포 막대그래프 저장
STEP 11  취약도 사분면 산점도 저장
STEP 12  TOP 10 취약 정류장 표 저장
STEP 13  정류장 등급 지도 저장 (folium)
STEP 14  결과 요약 출력
```

---

## 취약도 점수 산출 방식

각 지표를 0~1로 정규화한 뒤 가중 합산합니다.

```
BRT 환승·대기 취약도 점수 =
  0.25 × 95퍼센타일 대기시간
  0.20 × 배차간격 변동계수
  0.25 × BRT 환승 실패 위험도
  0.20 × 교통약자 시설 인접도  (병원 50% + 복지 30% + 학교 20%)
  0.10 × 정류장 시설 취약도    (무개 승강장 여부)
```

| 등급 | 범위 | 의미 | 정책 대응 |
|---|---|---|---|
| A | 하위 25% | 안정적 정류장 | 모니터링 유지 |
| B | 25~50% | 일부 불안정 | 시간대별 관찰 |
| C | 50~75% | 환승 실패 위험 | 환승 시간표 보정 검토 |
| D | 75~90% | 교통약자 대기 취약 | 배차 보정·정류장 개선 |
| E | 상위 10% | 최우선 개선 대상 | 두루타버스 연계·쉘터 개선 우선 적용 |

---

## 결과물 설명

| 파일 | 설명 |
|---|---|
| `04_vulnerability_score.csv` | 정류장별 취약도 점수 및 등급 전체 |
| `05_grade_distribution.png` | 등급별 정류장 수 막대그래프 |
| `06_quadrant_scatter.png` | 환승 실패 위험도 × 교통약자 인접도 사분면 |
| `07_top10_table.png` | E등급 TOP 10 정류장 요약 표 |
| `07_top10_stops.csv` | TOP 10 정류장 상세 데이터 |
| `08_vulnerability_map.html` | 세종시 정류장 등급 인터랙티브 지도 |

> `08_vulnerability_map.html`은 브라우저로 열면 등급별 레이어 ON/OFF 및 정류장 클릭 팝업 확인 가능

---

## 주의사항

- `.env` 파일은 절대 GitHub에 올리지 마세요 (`.gitignore`에 포함되어 있음)
- 병의원·학교 좌표는 주소 문자열에서 읍·면·동을 추출해 세종 행정구역별 근사 중심점으로 매핑합니다 (`output/geocache_sejong_regex_*.csv` 캐시). 매칭 실패 시 세종시청 일대 좌표로 폴백합니다.
- TAGO API는 실시간 데이터라 실행 시점에 따라 결과가 달라질 수 있음

---

## 참고 문헌

- 내외일보, "세종시민 10명 중 7명 '교통 바꿔야'", 2025.06.23
- 한국일보, "세종 '대중교통 중심도시' 성공하려면", 2023.05.08
- 연합뉴스TV, 세종시 공공기관 승용차 2부제 시행 후 버스 이용 증가 보도, 2026.04.28
- 공공데이터포털, 세종도시교통공사_버스정류장 시설현황
- 세종시 빅데이터 플랫폼 세담터, https://www2.sejong.go.kr/bigdata/
