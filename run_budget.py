"""Run the integrated budget app from any working directory."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
APP = ROOT / '2026-09-08_예산예측프로그램'

def main():
    try:
        from streamlit.web import cli
    except ImportError:
        raise SystemExit('먼저 실행방법.md의 가상환경 설치 단계를 진행하세요.')
    os.chdir(APP)
    sys.path.insert(0, str(APP))
    sys.argv = ['streamlit', 'run', str(APP/'app.py'), '--server.address=127.0.0.1',
                '--browser.gatherUsageStats=false', *sys.argv[1:]]
    return cli.main()

if __name__ == '__main__':
    sys.exit(main())
