"""
세종 BRT 분석 실행 진입점 — main.py 와 동일 스크립트를 실행합니다.
  python sejong_analysis.py
"""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "main.py"), run_name="__main__")
