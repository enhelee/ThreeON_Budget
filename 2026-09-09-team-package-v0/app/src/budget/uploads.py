# -*- coding: utf-8 -*-
"""업로드 읽기 — 크기 상한과 xlsx 압축 폭탄 검사(QA 2026-09-20 P2).

`await file.read()` 는 파일 전체를 한 번에 메모리에 올린다. 상한이 없으면 큰 파일 하나로
Render 무료(512MB) 프로세스가 죽고, 모든 사용자의 화면이 함께 멈춘다.
"""
import io
import os
import zipfile

from fastapi import HTTPException

# 업로드 상한. 실제 자료는 zrfm2 1.2MB · 계획 0.3MB 정도다. 상한이 없으면 큰 파일 하나로
# Render 무료(512MB) 프로세스가 죽는다. xlsx 는 zip 이라 «풀린 크기»도 따로 본다(압축 폭탄).
MAX_UPLOAD_BYTES = int(float(os.environ.get("MAX_UPLOAD_MB", "20") or 20) * 1024 * 1024)
MAX_XLSX_UNZIPPED = 300 * 1024 * 1024


async def read_upload(file, xlsx=True):
    """UploadFile 을 상한까지만 읽는다. 넘으면 413, 깨진/부푼 xlsx 는 400."""
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buf += chunk
        if len(buf) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                413, f"파일이 너무 큽니다({file.filename}) — "
                     f"{MAX_UPLOAD_BYTES // (1024 * 1024)}MB 이하만 올릴 수 있습니다.")
    data = bytes(buf)
    if xlsx:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                unzipped = sum(i.file_size for i in zf.infolist())
        except zipfile.BadZipFile:
            raise HTTPException(400, f"엑셀(xlsx) 파일이 아닙니다({file.filename}).")
        if unzipped > MAX_XLSX_UNZIPPED:
            raise HTTPException(413, f"엑셀 내용이 비정상적으로 큽니다({file.filename}).")
    return data
