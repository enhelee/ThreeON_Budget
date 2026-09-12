# -*- coding: utf-8 -*-
"""공용 비밀번호 로그인 + 작업자 이름 + 감사 로그(수정 이력).

사용자 결정(2026-09-08): 개인 계정 대신 **팀 공용 비밀번호 1개**. 그래도 '누가 언제 무엇을
바꿨는지'는 남아야 하므로 로그인 때 **작업자 이름**을 받아 서명 쿠키에 넣고, 모든 변경 API
(POST/PUT/DELETE)를 audit_log에 기록한다.

환경변수(.env — Git에 올리지 않음, `.env.example` 참고):
  APP_PASSWORD   팀 공용 비밀번호. 비어 있으면 인증 비활성(로컬 개발 모드, 작업자='local').
  SECRET_KEY     세션 쿠키 서명 키(32자 이상 무작위). 비어 있으면 기동 시 임의 생성(재시작하면 로그아웃).
  SESSION_HOURS  세션 유효시간(기본 12).
  COOKIE_SECURE  1이면 https 전용 쿠키(공개 배포 시 1). 기본: 요청이 https면 자동.
"""
import hmac
import os
import secrets
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def load_dotenv_if_present(app_dir):
    """budget_app/.env → os.environ (이미 설정된 값은 건드리지 않음). python-dotenv 없으면 수동 파싱."""
    path = os.path.join(app_dir, ".env")
    if not os.path.exists(path):
        return False
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)
        return True
    except ImportError:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return True


class AuthConfig:
    def __init__(self):
        self.password = os.environ.get("APP_PASSWORD", "").strip()
        self.secret = os.environ.get("SECRET_KEY", "").strip() or secrets.token_urlsafe(48)
        self.session_hours = float(os.environ.get("SESSION_HOURS", "12") or 12)
        self.cookie_name = os.environ.get("COOKIE_NAME", "budget_session")
        self.cookie_secure = os.environ.get("COOKIE_SECURE", "").strip() == "1"
        self._ser = URLSafeTimedSerializer(self.secret, salt="budget-session")

    @property
    def enabled(self):
        return bool(self.password)

    def check_password(self, given):
        return self.enabled and hmac.compare_digest(str(given or ""), self.password)

    def issue(self, operator):
        return self._ser.dumps({"op": operator})

    def verify(self, token) -> Optional[str]:
        if not token:
            return None
        try:
            data = self._ser.loads(token, max_age=int(self.session_hours * 3600))
        except (BadSignature, SignatureExpired):
            return None
        op = data.get("op") if isinstance(data, dict) else None
        return op or None


def clean_operator(name):
    """작업자 이름 정리 — 1~40자, 제어문자 제거."""
    s = "".join(ch for ch in str(name or "") if ch.isprintable()).strip()
    return s[:40]


# 인증 없이 열리는 API 경로(로그인·상태·헬스체크). 그 외 /api/* 는 세션 필수.
PUBLIC_API = {"/api/login", "/api/logout", "/api/auth/status", "/healthz"}


def audit_detail(request_path, query, body_json):
    """감사 로그 요약 — 파일 본문·대용량은 넣지 않고 키/식별자만."""
    parts = []
    if query:
        parts.append("q=" + query[:300])
    if isinstance(body_json, dict):
        keep = {}
        for k, v in body_json.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                keep[k] = v if not isinstance(v, str) else v[:120]
            elif isinstance(v, list):
                keep[k] = f"[{len(v)}건]"
            elif isinstance(v, dict):
                keep[k] = {kk: (vv if not isinstance(vv, str) else vv[:80]) for kk, vv in list(v.items())[:12]}
        parts.append(str(keep)[:1500])
    return " ".join(parts)
