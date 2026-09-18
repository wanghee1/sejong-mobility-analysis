# BRT 환승권역별 환승·대기 취약도 등급 지도 최종본

## 목적

세종시 정류장을 대상으로 **BRT 환승권역별 환승·대기 취약도**를 산출하고, 어디를 먼저 개선해야 하는지 보여주는 **최종 우선순위 지도**를 만든다.

최종 산출물은 다음 2개를 중심으로 사용하면 된다.

1. `grade_map_final.png`
   - 발표 메인 지도
   - 정류장별 A~E 등급과 개선 우선순위 표시

2. `heatmap_final.png`
   - 보조 분석 자료
   - 시간대별 환승 실패 위험과 체감 손실시간 표시

---

## 파일 구성

```text
brt_final/
├─ analysis_final.py          # 등급 산출 메인 코드
├─ make_map_final.py          # 개선 우선순위 지도 생성
├─ make_heatmap_final.py      # 시간대별 환승 실패 위험도 히트맵 생성
├─ run_all_final.py           # 전체 실행 스크립트
├─ requirements.txt
└─ README_FINAL.md
```

실행 전 데이터 파일은 아래처럼 `data/` 폴더에 넣는다.

```text
brt_final/
├─ data/
│  ├─ bus_stops.csv
│  ├─ 세종특별자치시__버스운행_현황_20250527.csv
│  ├─ 한국교육시설안전원_초중등학교위치_20260320.csv
│  └─ hospitals.csv
└─ output/                    # 실행 후 자동 생성
```

---

## 실행 방법

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. 전체 실행

```bash
python run_all_final.py
```

### 3. 단계별 실행

```bash
python analysis_final.py
python make_map_final.py
python make_heatmap_final.py
```

또는 데이터/결과 폴더를 직접 지정할 수 있다.

```bash
python analysis_final.py --data-dir data --output-dir output --headway-basis combined_feeder
python make_map_final.py --data-dir data --output-dir output --annotate-top 10
python make_heatmap_final.py --output-dir output --top-e 7 --top-d 5
```

---

## 출력 파일

`output/` 폴더에 다음 파일이 생성된다.

```text
output/
├─ g.pkl
├─ stop_grades_final.csv
├─ priority_top20_final.csv
├─ analysis_summary_final.txt
├─ grade_map_final.png
├─ heatmap_final.png
├─ heatmap_final.csv
└─ heatmap_fail_probability_final.csv
```

### 핵심 결과물

- `grade_map_final.png`: 발표 메인 지도
- `priority_top20_final.csv`: 개선 우선순위 상위 20개 정류장
- `analysis_summary_final.txt`: 등급 분포와 핵심 요약
- `heatmap_final.png`: 시간대별 취약성 보조자료

---

## 등급 산정 기준

분위수 기반 상대평가가 아니라 정책적으로 설명 가능한 절대 기준을 사용한다.

### 주요 조건

| 조건 | 의미 | 기준 |
|---|---|---|
| 지선환승필수 | BRT 직접 접근이 어려워 지선 환승 필요 | BRT 미경유 + 최근접 BRT 정류장 500m 초과 |
| 대기취약 | 배차가 길어 대기 부담이 큼 | 대표배차 30분 이상 |
| 대기심각 | 대기 부담이 매우 큼 | 대표배차 60분 이상 |
| 약자인접 | 교통약자 수요가 있을 가능성 | 학교 500m 반경 또는 병의원 접근성 지표 충족 |

### 등급 정의

| 등급 | 기준 | 정책 처방 |
|---|---|---|
| A | 안정 또는 BRT 직결 | 현행 유지 및 정기 모니터링 |
| B | 지선환승필수 또는 대기취약 | 출퇴근·등하교 시간대 집중 모니터링 |
| C | 지선환승필수 + 대기심각 | 지선-BRT 환승 시간표 보정, 배차간격 조정 |
| D | 약자인접 + 대기취약 | 쉘터·의자·안내정보 등 대기환경 우선 개선 |
| E | 지선환승필수 + 대기심각 + 약자인접 | 배차 조정 + 두루타버스 연계 + 정류장 개선 패키지 |

---

## 대표배차 기준: 기본값은 합산배차

최종본의 기본 대표배차는 `combined_feeder`, 즉 **지선노선 합산배차**다.

여러 노선이 독립적으로 도착한다고 보면 체감 유효배차는 아래 공식으로 계산한다.

```text
유효배차 = 1 / Σ(1 / hᵢ)
```

- `hᵢ`: i번 노선의 배차간격
- 노선이 늘어날수록 유효배차가 짧아진다.
- 하루 1회 수준의 마을버스가 평균을 끌어올려 정류장을 과도하게 취약하게 만드는 문제를 방지한다.
- 세종중학교처럼 30분 배차 지선이 여러 개 있고 하루 1회 노선도 함께 있는 정류장은 단순 평균배차보다 합산배차가 실제 체감 대기에 더 가깝다.
- 조치원역뒤편처럼 노선이 하나뿐인 곳은 합산배차가 해당 노선 배차 그대로 유지된다.

민감도 분석용으로 기존 기준도 남겨두었다.

```bash
python analysis_final.py --headway-basis combined_feeder # 기본/권장: 지선노선 합산배차
python analysis_final.py --headway-basis mean_feeder     # 민감도: 지선노선 평균배차
python analysis_final.py --headway-basis min_feeder      # 민감도: 지선노선 최소배차
python analysis_final.py --headway-basis max_feeder      # 민감도: 지선노선 최대배차
python analysis_final.py --headway-basis combined_any    # 참고: 전체노선 합산배차
python analysis_final.py --headway-basis min_any         # 참고: 전체노선 최소배차
python analysis_final.py --headway-basis mean_any        # 참고: 전체노선 평균배차
```

발표에서는 이렇게 말하면 된다.

```text
정류장에 여러 지선노선이 독립적으로 도착하는 경우 체감 대기는 개별 노선의 단순 평균이 아니라 합산배차로 계산했습니다. 따라서 노선이 많아질수록 정류장이 더 취약해 보이는 역전 현상을 방지했고, 노선이 하나뿐인 정류장은 해당 노선 배차가 그대로 반영됩니다.
```

---

## TOP20 중복 제거

`priority_top20_final.csv`는 양방향 정류소ID 중복을 제거하기 위해 `정류소명` 기준으로 접은 뒤 상위 20개 지점을 출력한다.

지도와 히트맵은 전체 정류장 좌표를 유지하되, 발표용 TOP20 표는 실제 개선 지점 기준으로 보이도록 정류소명 중복을 제거했다.

---

## 병의원 지표 처리

학교는 실제 좌표 기반 500m 반경으로 계산한다.

병의원은 데이터에 위도/경도가 있으면 500m 반경으로 계산하고, 좌표가 없으면 행정동 단위 병의원 수를 보조지표로 사용한다.

발표에서는 이렇게 설명하면 안전하다.

```text
학교는 좌표 기반 500m 반경으로 반영했고, 병의원은 좌표가 있는 경우 반경 기준으로, 좌표가 없는 경우 행정동 단위 접근 수요 보조지표로 반영했습니다.
```

---

## 개선 우선순위 산정

A~E 등급만 산출하지 않고, BRT 환승권역 정류장 내부에서 `개선우선순위`를 추가로 부여한다.

정렬 기준은 다음 순서다.

1. 등급 가중치: E > D > C > B > A
2. 취약도점수
3. 대표배차분
4. 최근접 BRT 거리
5. 약자인접도

---

## 발표용 설명 문장

```text
정류장별 BRT 접근성, 지선버스 유효배차, 교통약자 시설 접근성을 결합해 환승·대기 취약도를 A~E등급으로 분류했습니다. 특히 E등급은 BRT 500m 밖에 위치해 지선 환승이 필요하고, 대표배차가 60분 이상이며, 학교나 병의원 접근 수요까지 겹치는 정류장입니다. 따라서 E등급 지역은 배차 조정, 두루타버스 연계, 정류장 대기환경 개선을 패키지로 우선 적용해야 하는 최우선 개선 대상입니다.
```

---

## 한계와 고도화 방향

현재 분석은 정적 운행 현황과 시설 좌표를 기반으로 한다.  
따라서 실제 도착 지연, 시간대별 결행, 환승 대기시간 95퍼센타일, 배차간격 변동계수는 아직 실측 기반으로 산출하지 않았다.

발표에서는 숨기기보다 다음처럼 말하는 것이 좋다.

```text
이번 분석은 정적 운행 현황을 기반으로 우선 개선 후보지를 선별한 1차 진단입니다. 향후 TAGO 실시간 도착 데이터를 수집하면 실제 지연 분포, 환승 실패 확률, 95퍼센타일 대기시간까지 반영해 등급을 고도화할 수 있습니다.
```
