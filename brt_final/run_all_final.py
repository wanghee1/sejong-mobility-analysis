# -*- coding: utf-8 -*-
"""BRT 환승권역 취약도 분석 전체 실행 스크립트."""
from pathlib import Path
import subprocess
import sys

DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")

commands = [
    [sys.executable, "analysis_final.py", "--data-dir", str(DATA_DIR), "--output-dir", str(OUTPUT_DIR), "--headway-basis", "combined_feeder"],
    [sys.executable, "merge_directions.py", "--output-dir", str(OUTPUT_DIR), "--direction-agg", "max"],
    [sys.executable, "make_map_final.py", "--data-dir", str(DATA_DIR), "--output-dir", str(OUTPUT_DIR)],
    [sys.executable, "make_heatmap_final.py", "--output-dir", str(OUTPUT_DIR), "--top-e", "7", "--top-d", "5"],
]

for cmd in commands:
    print("\n$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)

print("\n완료: output 폴더에서 결과 파일을 확인하세요.")
