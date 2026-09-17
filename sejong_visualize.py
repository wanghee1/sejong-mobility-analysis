import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from matplotlib import font_manager
import numpy as np
import os, platform

# 폰트 설정
if platform.system() == 'Windows':
    plt.rcParams['font.family'] = 'Malgun Gothic'
elif platform.system() == 'Darwin':
    plt.rcParams['font.family'] = 'AppleGothic'
else:
    fp = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    if os.path.exists(fp):
        font_manager.fontManager.addfont(fp)
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
plt.rcParams['axes.unicode_minus'] = False

# 스크립트와 같은 프로젝트의 output/ (main.py 결과물과 같은 폴더)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_SCRIPT_DIR, "output")
os.makedirs(OUT, exist_ok=True)

C = {
    'teal':   {'bg':'#E1F5EE','bd':'#0F6E56','tx':'#085041','sub':'#1D9E75'},
    'purple': {'bg':'#EEEDFE','bd':'#534AB7','tx':'#26215C','sub':'#7F77DD'},
    'blue':   {'bg':'#E6F1FB','bd':'#185FA5','tx':'#042C53','sub':'#378ADD'},
    'red':    {'bg':'#FCEBEB','bd':'#A32D2D','tx':'#501313','sub':'#E24B4A'},
    'amber':  {'bg':'#FAEEDA','bd':'#854F0B','tx':'#412402','sub':'#BA7517'},
    'gray':   {'bg':'#F1EFE8','bd':'#888780','tx':'#2C2C2A','sub':'#5F5E5A'},
}

def box(ax, x, y, w, h, c, title, sub=None, fs=9, fs2=7.5):
    p = FancyBboxPatch((x,y), w, h, boxstyle="round,pad=0.02",
        facecolor=c['bg'], edgecolor=c['bd'], linewidth=0.8, zorder=3)
    ax.add_patch(p)
    ty = y+h/2+(h*0.1 if sub else 0)
    ax.text(x+w/2, ty, title, ha='center', va='center',
            fontsize=fs, fontweight='bold', color=c['tx'], zorder=4)
    if sub:
        ax.text(x+w/2, y+h/2-h*0.18, sub, ha='center', va='center',
                fontsize=fs2, color=c['sub'], zorder=4)

def arr(ax, x1,y1,x2,y2, col='#555', lw=1.2, ls='-'):
    ax.annotate('', xy=(x2,y2), xytext=(x1,y1),
        arrowprops=dict(arrowstyle='->', color=col, lw=lw, linestyle=ls,
                        connectionstyle='arc3,rad=0'))

# ══════════════════════════════════════════════════════
# 시각자료 1 — 대중교통 구조도 및 환승 실패 구조
# ══════════════════════════════════════════════════════
fig1, ax1 = plt.subplots(figsize=(11, 6.8))
ax1.set_xlim(0,11); ax1.set_ylim(0,6.8); ax1.axis('off')
fig1.patch.set_facecolor('white')

ax1.text(5.5,6.4,'정상 운행 시', ha='center', fontsize=9, color='#888')
box(ax1, 0.2,5.0,2.0,1.0, C['teal'],  '생활권','읍·면·동 주거지')
box(ax1, 3.2,5.0,2.8,1.0, C['purple'],'BRT 환승 정류장','지선버스 도착 → BRT 탑승')
box(ax1, 7.3,5.0,2.0,1.0, C['blue'],  '목적지','직장·병원·학교')
arr(ax1,2.2,5.5,3.2,5.5, col=C['teal']['sub'])
ax1.text(2.7,5.65,'지선버스',ha='center',fontsize=7.5,color=C['teal']['bd'])
arr(ax1,6.0,5.5,7.3,5.5, col=C['purple']['sub'])
ax1.text(6.65,5.65,'BRT',ha='center',fontsize=7.5,color=C['purple']['bd'])

ax1.axhline(4.7, color='#ccc', lw=0.8, ls='--', xmin=0.02, xmax=0.98)
ax1.text(5.5,4.45,'지선버스 지연 시', ha='center', fontsize=9, color='#888')

box(ax1, 0.2,2.9,2.0,1.0, C['teal'], '생활권','읍·면·동 주거지')
box(ax1, 3.2,2.9,2.8,1.0, C['red'],  'BRT 환승 정류장','도착했으나 BRT 이미 출발')
box(ax1, 7.3,2.9,2.0,1.0, C['gray'], '목적지','도착 지연')
box(ax1, 3.2,1.3,2.8,1.0, C['amber'],'다음 BRT 대기','추가 10분 이상 손실')
arr(ax1,2.2,3.4,3.2,3.4, col=C['red']['sub'])
ax1.text(2.7,3.62,'지선버스',ha='center',fontsize=7.5,color=C['red']['bd'])
ax1.text(2.7,3.22,'3~5분 지연',ha='center',fontsize=7.5,color=C['red']['sub'])
ax1.text(6.8,3.4,'X',ha='center',va='center',fontsize=20,
         color=C['red']['sub'],fontweight='bold',zorder=5)
arr(ax1,4.6,2.9,4.6,2.32, col=C['red']['sub'])
arr(ax1,6.0,1.8,7.8,2.9, col=C['amber']['sub'], ls='--')

ax1.axhline(1.0, color='#ccc', lw=0.8, ls='--', xmin=0.02, xmax=0.98)
mp = FancyBboxPatch((0.5,0.12),10.0,0.7, boxstyle="round,pad=0.04",
    facecolor=C['purple']['bg'], edgecolor=C['purple']['bd'], linewidth=0.8, zorder=3)
ax1.add_patch(mp)
ax1.text(5.5,0.48,'지선버스 3~5분 지연  →  BRT 환승 실패  →  실제 이동시간 10분 이상 추가 손실',
    ha='center',va='center',fontsize=9,fontweight='bold',color=C['purple']['tx'],zorder=4)

plt.tight_layout(pad=0.3)
fig1.savefig(f'{OUT}/시각자료1_대중교통구조도.png', dpi=180, bbox_inches='tight', facecolor='white')
plt.close(fig1)
print("[OK] 시각자료1_대중교통구조도.png 저장")

# ══════════════════════════════════════════════════════
# 시각자료 2 — 분석 흐름 플로우차트
# ══════════════════════════════════════════════════════
fig2, ax2 = plt.subplots(figsize=(11,7.5))
ax2.set_xlim(0,11); ax2.set_ylim(0,7.5); ax2.axis('off')
fig2.patch.set_facecolor('white')

STEPS = [
    (C['teal'],  'STEP 1','환승 정류장 도출'),
    (C['blue'],  'STEP 2','도착 안정성 분석'),
    (C['red'],   'STEP 3','환승 실패 위험도'),
    (C['amber'], 'STEP 4','교통약자 인접도'),
]
xs = [0.3,2.8,5.3,7.8]; bw,bh = 2.1,1.1
for i,(col,step,label) in enumerate(STEPS):
    box(ax2, xs[i],5.8,bw,bh, col, step, label, fs=9)
    if i<3:
        arr(ax2, xs[i]+bw,6.35, xs[i+1],6.35, col=col['sub'])

ax2.annotate('', xy=(5.5,5.5), xytext=(8.95,5.8),
    arrowprops=dict(arrowstyle='->', color=C['amber']['sub'], lw=1.2,
                    connectionstyle='angle,angleA=0,angleB=90'))
box(ax2, 1.0,4.4,9.0,1.0, C['purple'],
    'STEP 5', 'BRT 환승·대기 취약도 점수 산출 및 정류장 등급화 (A~E)', fs=10)

ax2.axhline(4.1, color='#ccc', lw=0.8, ls='--', xmin=0.02, xmax=0.98)
ax2.text(0.3,3.9,'활용 데이터', fontsize=8, color='#aaa')

DATA = [
    (C['teal'],  'TAGO\n버스노선정보'),
    (C['blue'],  'TAGO 버스\n도착·위치정보\n정류장 시설현황'),
    (C['red'],   'TAGO 버스\n도착·위치정보'),
    (C['amber'], '병의원·복지시설\n학교 현황\n(반경 300·500m)'),
]
for i,(col,label) in enumerate(DATA):
    box(ax2, xs[i],2.6,bw,1.1, col, label, fs=8)

ax2.axhline(2.35, color='#ccc', lw=0.8, ls='--', xmin=0.02, xmax=0.98)
ax2.text(0.3,2.15,'산출 결과', fontsize=8, color='#aaa')

RESULTS = [
    (C['gray'],   '환승 가능\n정류장 목록'),
    (C['gray'],   '95퍼센타일 대기시간\n배차간격 변동계수'),
    (C['gray'],   '환승 여유시간\n환승 실패 위험도'),
    (C['purple'], '취약도 점수\nA~E 등급'),
]
for i,(col,label) in enumerate(RESULTS):
    box(ax2, xs[i],0.8,bw,1.1, col, label, fs=8)

plt.tight_layout(pad=0.3)
fig2.savefig(f'{OUT}/시각자료2_분석흐름.png', dpi=180, bbox_inches='tight', facecolor='white')
plt.close(fig2)
print("[OK] 시각자료2_분석흐름.png 저장")

# ══════════════════════════════════════════════════════
# 시각자료 3 — 취약도 등급 사분면 (개념도)
# ══════════════════════════════════════════════════════
fig3, ax3 = plt.subplots(figsize=(9,7))
ax3.set_xlim(0,10); ax3.set_ylim(0,10); ax3.axis('off')
fig3.patch.set_facecolor('white')

quads = [
    (0.8,5.0,4.2,4.5,'#E1F5EE'),
    (5.0,5.0,4.5,4.5,'#FCEBEB'),
    (0.8,0.8,4.2,4.2,'#E1F5EE'),
    (5.0,0.8,4.5,4.2,'#E6F1FB'),
]
for qx,qy,qw,qh,qc in quads:
    ax3.add_patch(FancyBboxPatch((qx,qy),qw,qh,
        boxstyle="round,pad=0.05", facecolor=qc, edgecolor='none', alpha=0.6, zorder=1))

ax3.annotate('',xy=(9.8,0.5),xytext=(0.5,0.5),
    arrowprops=dict(arrowstyle='->',color='#555',lw=1.2))
ax3.annotate('',xy=(0.5,9.8),xytext=(0.5,0.5),
    arrowprops=dict(arrowstyle='->',color='#555',lw=1.2))
ax3.text(5.0,0.1,'BRT 환승 실패 위험도 →',ha='center',fontsize=9,color='#666')
ax3.text(0.1,5.0,'교통약자 시설 인접도 →',ha='center',fontsize=9,
         color='#666',rotation=90,va='center')
ax3.axhline(5.0,color='#bbb',lw=0.6,ls='--',xmin=0.05,xmax=0.98)
ax3.axvline(5.0,color='#bbb',lw=0.6,ls='--',ymin=0.05,ymax=0.98)

box(ax3, 1.0,6.5,3.5,1.4, C['amber'], 'D등급','배차 보정·시설 개선', fs=10)
box(ax3, 1.0,1.5,3.5,1.4, C['teal'],  'A등급','모니터링 유지', fs=10)
box(ax3, 5.3,1.5,1.5,1.4, C['blue'],  'B','시간대별 관찰', fs=10)
box(ax3, 7.0,1.5,2.3,1.4, C['blue'],  'C등급','시간표 보정 검토', fs=10)

ax3.add_patch(FancyBboxPatch((5.2,5.8),4.2,2.2,
    boxstyle="round,pad=0.05", facecolor=C['red']['bg'],
    edgecolor=C['red']['bd'], linewidth=1.5, zorder=3))
ax3.text(7.3,7.4,'E등급',ha='center',fontsize=12,fontweight='bold',color=C['red']['tx'],zorder=4)
ax3.text(7.3,6.9,'최우선 개선 대상',ha='center',fontsize=9,color=C['red']['bd'],zorder=4)
ax3.text(7.3,6.4,'환승 실패 위험 높음 +\n교통약자 시설 인접',
         ha='center',fontsize=8,color=C['red']['sub'],zorder=4)
ax3.text(7.3,5.5,'두루타버스 연계·쉘터 개선·시간표 보정\n우선 적용',
         ha='center',fontsize=7.5,color=C['red']['bd'])

np.random.seed(42)
pts_a  = np.column_stack([np.random.uniform(1.0,4.5,6),np.random.uniform(1.0,4.5,6)])
pts_bc = np.array([[5.5,1.8],[6.5,2.5],[7.5,1.5],[8.5,3.0],[6.0,3.5],[8.0,4.0]])
pts_d  = np.array([[1.5,6.0],[2.5,7.0],[3.5,6.5],[1.8,8.0]])
pts_e  = np.array([[5.8,6.2],[6.8,7.5],[7.8,6.8],[8.5,7.8],[6.5,8.5]])
ax3.scatter(pts_a[:,0], pts_a[:,1],  c=C['teal']['sub'],   s=40, alpha=0.6, zorder=5)
ax3.scatter(pts_bc[:,0],pts_bc[:,1], c=C['blue']['sub'],   s=40, alpha=0.6, zorder=5)
ax3.scatter(pts_d[:,0], pts_d[:,1],  c=C['amber']['sub'],  s=40, alpha=0.7, zorder=5)
ax3.scatter(pts_e[:,0], pts_e[:,1],  c=C['red']['sub'],    s=60, alpha=0.85,zorder=5)

legend_items = [
    mpatches.Patch(color=C['teal']['sub'],  alpha=0.7,  label='A등급 정류장'),
    mpatches.Patch(color=C['blue']['sub'],  alpha=0.7,  label='B/C등급 정류장'),
    mpatches.Patch(color=C['amber']['sub'], alpha=0.7,  label='D등급 정류장'),
    mpatches.Patch(color=C['red']['sub'],   alpha=0.85, label='E등급 (우선 개선)'),
]
ax3.legend(handles=legend_items, loc='lower right', fontsize=8,
           framealpha=0.9, edgecolor='#ddd', bbox_to_anchor=(0.98,0.02))

plt.tight_layout(pad=0.3)
fig3.savefig(f'{OUT}/시각자료3_취약도사분면.png', dpi=180, bbox_inches='tight', facecolor='white')
plt.close(fig3)
print("[OK] 시각자료3_취약도사분면.png 저장")
print(f"\n완료! PNG 저장 위치: {OUT}")
