# [인터넷 PC · Windows] 이미지를 만들어 파일로 저장한다 — 이 파일을 사내 서버로 반입한다.
#
#   powershell -ExecutionPolicy Bypass -File deploy\onprem\build_image.ps1 [-Out dist]
#
# 결과: dist\threeon-budget_<커밋>.tar.gz + .sha256
# 반입할 것: 위 두 파일 · deploy\ 폴더 · .env(.env.example 을 복사해 작성)
#
# 커밋 해시를 --build-arg 로 넣는 이유: /healthz 의 "commit" 이 사내에서도 찍혀야
# «지금 떠 있는 게 어느 버전인가»를 판별할 수 있다(Render 는 자동으로 넣어 주지만 사내는 아니다).
param([string]$Out = "dist")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")     # 패키지 루트

$Img = "threeon-budget"
$Sha = "manual"
try { $s = (git rev-parse --short HEAD 2>$null); if ($LASTEXITCODE -eq 0 -and $s) { $Sha = $s.Trim() } } catch {}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker 가 없습니다. Docker Desktop 을 설치하세요."
}

Write-Host "[1/3] 빌드  ${Img}:${Sha}  (프론트 빌드 + pip 설치, 처음은 5~10분)"
docker build -f deploy/Dockerfile --build-arg APP_COMMIT=$Sha -t "${Img}:${Sha}" -t "${Img}:latest" .
if ($LASTEXITCODE -ne 0) { throw "docker build 실패 (종료코드 $LASTEXITCODE)" }

$Tar = Join-Path $Out "${Img}_${Sha}.tar.gz"
Write-Host "[2/3] 저장  $Tar"
New-Item -ItemType Directory -Force $Out | Out-Null
# docker save 로 받은 .tar 를 gzip 스트림으로 **그대로** 압축한다 = bash 의 `docker save | gzip`.
# ⚠ `tar -czf x.tar.gz x.tar` 로 감싸면 «docker tar 를 담은 tar» 가 되어 docker load 가 못 읽는다.
#   그리고 tar.exe 는 PATH 에 따라 GNU tar(Git 동봉)가 잡혀 `C:\` 의 콜론을 원격 호스트로 해석해
#   실패한다(실측 2026-09-20). 외부 도구 없이 .NET 으로 처리한다.
$RawTar = Join-Path $Out "${Img}_${Sha}.tar"
docker save -o $RawTar "${Img}:${Sha}"
if ($LASTEXITCODE -ne 0) { throw "docker save 실패 (종료코드 $LASTEXITCODE)" }
$in = [System.IO.File]::OpenRead($RawTar)
try {
    $outFs = [System.IO.File]::Create($Tar)
    try {
        $gz = New-Object System.IO.Compression.GZipStream($outFs, [System.IO.Compression.CompressionMode]::Compress)
        try { $in.CopyTo($gz) } finally { $gz.Dispose() }
    } finally { $outFs.Dispose() }
} finally { $in.Dispose() }
Remove-Item $RawTar -Force

Write-Host "[3/3] 체크섬"
$Hash = (Get-FileHash $Tar -Algorithm SHA256).Hash.ToLower()
# ⚠ 줄 끝은 LF 하나여야 한다. Set-Content 는 CRLF 를 붙이는데, 이 파일을 Linux 서버의
#   `sha256sum -c` 가 읽으면 파일명 끝의 \r 때문에 «no such file → FAILED» 가 난다
#   (Windows 에서 빌드 → Linux 서버 반입 조합에서 실측). 형식은 sha256sum 과 같은 «해시  이름».
[System.IO.File]::WriteAllText("$Tar.sha256", "$Hash  ${Img}_${Sha}.tar.gz`n", (New-Object System.Text.UTF8Encoding($false)))
Get-Content "$Tar.sha256"

Write-Host ""
Write-Host "완료. 반입할 것:"
Write-Host "  $Tar  (+ .sha256)"
Write-Host "  deploy\            (docker-compose.yml · onprem\)"
Write-Host "  .env               (.env.example 복사 후 APP_PASSWORD · SECRET_KEY 작성)"
Write-Host "서버에서:  powershell -ExecutionPolicy Bypass -File deploy\onprem\load_and_run.ps1 -Tar <tar.gz 경로>"
