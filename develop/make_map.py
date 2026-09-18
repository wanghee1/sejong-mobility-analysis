# -*- coding: utf-8 -*-
"""세종시 BRT 환승·대기 취약도 등급 지도 (PPT용 고해상도 PNG)"""
import pandas as pd, numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.lines import Line2D
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'

def setup_korean_font():
    candidates = [
        Path(r'C:\Windows\Fonts\malgun.ttf'),
        Path(r'C:\Windows\Fonts\malgunbd.ttf'),
        Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf'),
        Path('/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'),
    ]
    for path in candidates:
        if path.exists():
            fm.fontManager.addfont(str(path))
    for name in ('Malgun Gothic', 'NanumGothic', 'Nanum Gothic'):
        if any(name.lower() in f.name.lower() for f in fm.fontManager.ttflist):
            plt.rcParams['font.family'] = name
            break
    plt.rcParams['axes.unicode_minus'] = False

setup_korean_font()

df = pd.read_csv(BASE_DIR / 'stop_grades.csv')
stops = pd.read_csv(DATA_DIR / 'bus_stops.csv', encoding='utf-8')

COLORS = {'A':'#B8C4CE','B':'#8FA8BC','C':'#F5B041','D':'#E67E22','E':'#C0392B'}
SIZES  = {'A':10,'B':10,'C':16,'D':42,'E':90}
ALPHA  = {'A':0.45,'B':0.45,'C':0.55,'D':0.9,'E':1.0}

fig, ax = plt.subplots(figsize=(10.5, 12), dpi=200)

# BRT 축 (노선별 정류장 순서 연결)
for r in ['B0','B2','B5']:
    line = stops[stops['노선번호']==r].sort_values('연번')
    ax.plot(line['경도'], line['위도'], color='#2E5F8A', lw=2.2, alpha=0.5, zorder=1)

# 등급별 정류장 (E를 맨 위에)
for g in ['A','B','C','D','E']:
    sub = df[df['등급']==g]
    ax.scatter(sub['경도'], sub['위도'], s=SIZES[g], c=COLORS[g], alpha=ALPHA[g],
               edgecolors='white' if g in 'DE' else 'none', linewidths=0.6,
               zorder={'A':2,'B':2,'C':3,'D':4,'E':5}[g])

# E등급 클러스터 지역 라벨
e = df[df['등급']=='E']
labels = {
    '전의면 일대':   (36.695, 127.185, 'left'),
    '연서면 일대':   (36.578, 127.222, 'right'),
    '조치원 서부':   (36.617, 127.272, 'right'),
    '장군면 일대':   (36.505, 127.185, 'right'),
    '부강면 일대':   (36.518, 127.372, 'left'),
    '금남면 일대':   (36.445, 127.275, 'left'),
}
for name, (la, lo, ha) in labels.items():
    ax.annotate(name, (lo, la), fontsize=11.5, fontweight='bold', color='#C0392B',
                ha=ha, va='center',
                bbox=dict(boxstyle='round,pad=0.32', fc='white', ec='#C0392B', lw=1.1, alpha=0.92))

# 행복도시(신도심) 참고 라벨
ax.annotate('행복도시(신도심)\nBRT 순환축', (127.258, 36.474), fontsize=10.5, color='#2E5F8A',
            fontweight='bold', ha='center',
            bbox=dict(boxstyle='round,pad=0.3', fc='#EAF1F7', ec='#2E5F8A', lw=1.0, alpha=0.92))

legend_items = [
    Line2D([0],[0], marker='o', color='none', markerfacecolor=COLORS['E'], markersize=13,
           label=f'E등급 · 최우선 개선 대상 (58개)'),
    Line2D([0],[0], marker='o', color='none', markerfacecolor=COLORS['D'], markersize=10,
           label=f'D등급 · 교통약자 대기 취약 (110개)'),
    Line2D([0],[0], marker='o', color='none', markerfacecolor=COLORS['C'], markersize=8,
           label=f'C등급 · 환승 실패 위험 (521개)'),
    Line2D([0],[0], marker='o', color='none', markerfacecolor=COLORS['B'], markersize=7,
           label=f'B등급 · 일부 불안정 (389개)'),
    Line2D([0],[0], marker='o', color='none', markerfacecolor=COLORS['A'], markersize=7,
           label=f'A등급 · 안정 (136개)'),
    Line2D([0],[0], color='#2E5F8A', lw=2.5, alpha=0.6, label='BRT 노선축 (B0·B2·B5)'),
]
ax.legend(handles=legend_items, loc='lower right', fontsize=10.5, framealpha=0.95,
          edgecolor='#CCCCCC', borderpad=0.9, labelspacing=0.7)

ax.set_title('정류장별 BRT 환승·대기 취약도 등급 지도', fontsize=17, fontweight='bold', pad=14)
ax.text(0.5, 1.005, 'E등급(적색) = 환승 의존 + 노선 대안 부족 + 교통약자 시설 인접이 동시에 나타나는 정류장',
        transform=ax.transAxes, ha='center', fontsize=10.5, color='#555555')

ax.set_xlim(127.10, 127.44); ax.set_ylim(36.41, 36.77)
ax.set_xticks([]); ax.set_yticks([])
for s in ax.spines.values(): s.set_color('#DDDDDD')
ax.set_facecolor('#FAFBFC')
plt.tight_layout()
plt.savefig(BASE_DIR / 'grade_map.png', dpi=200, bbox_inches='tight', facecolor='white')
print('saved grade_map.png')
