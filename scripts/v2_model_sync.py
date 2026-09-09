# -*- coding: utf-8 -*-
"""팀 v2 앱(예산예측프로그램) 파일 ↔ budget_app 모델 레지스트리 동기화.

  py scripts/v2_model_sync.py --push [--v2 경로]   v2 폴더의 training_data.csv·project_type_training.csv·*.joblib → DB 레지스트리
  py scripts/v2_model_sync.py --pull [--v2 경로]   DB의 활성 모델·학습데이터 → v2 폴더 파일(v2 앱이 그대로 읽음)
  py scripts/v2_model_sync.py --status            레지스트리 현황

기본 v2 경로: ../예산예측프로그램_팀공유_v2 (또는 환경변수 V2_DIR). DB는 budget_app 설정(.env의 DATABASE_URL 또는 SQLite)을 따른다.
"""
import argparse
import getpass
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))

from budget import auth as authm            # noqa: E402
authm.load_dotenv_if_present(APP)
from budget import db as dbm, ml_registry   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--push", action="store_true", help="v2 파일 → 레지스트리")
    ap.add_argument("--pull", action="store_true", help="레지스트리 활성 버전 → v2 파일")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--v2", default=os.environ.get("V2_DIR") or os.path.join(os.path.dirname(APP), "예산예측프로그램_팀공유_v2"))
    ap.add_argument("--actor", default=os.environ.get("OPERATOR") or getpass.getuser())
    a = ap.parse_args()
    if not (a.push or a.pull or a.status):
        ap.print_help()
        return 1
    conn = dbm.connect()
    try:
        if a.push:
            if not os.path.isdir(a.v2):
                print("v2 폴더가 없습니다:", a.v2)
                return 2
            rep = ml_registry.import_v2_files(conn, a.v2, actor=a.actor)
            for k, v in rep.items():
                print(f"[push] {k}: {v}")
            if not rep:
                print("[push] 반입할 파일이 없습니다(training_data.csv / project_type_training.csv / *.joblib).")
        if a.pull:
            os.makedirs(a.v2, exist_ok=True)
            written = ml_registry.export_to_v2_files(conn, a.v2)
            print("[pull] 기록:", written or "활성 모델·학습데이터 없음")
        if a.status or a.push or a.pull:
            for m in ml_registry.list_models(conn):
                flag = "★" if m["active"] else " "
                print(f"{flag} {m['name']} v{m['version']} {m['trained_at']} 표본 {m['n_samples']} "
                      f"CV {m['metrics'].get('cv_accuracy')} by {m['created_by']} ({m['note'] or ''})")
            for n in ml_registry.MODEL_NAMES:
                st = ml_registry.example_stats(conn, n)
                print(f"  학습데이터 {n}: {st['total']}건 (확정 {st['confirmed']}) 재학습가능={st['trainable']}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
