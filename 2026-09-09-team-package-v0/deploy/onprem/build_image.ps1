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
# docker save 는 gzip 을 알아서 풀어 읽으므로(docker load), 저장은 .tar 로 받은 뒤 압축한다.
$RawTar = Join-Path $Out "${Img}_${Sha}.tar"
docker save -o $RawTar "${Img}:${Sha}"
if ($LASTEXITCODE -ne 0) { throw "docker save 실패 (종료코드 $LASTEXITCODE)" }
# tar 는 Windows 10 1803+ 에 내장(bsdtar). -z 로 gzip.
tar -czf $Tar -C $Out "${Img}_${Sha}.tar"
if ($LASTEXITCODE -ne 0) { throw "tar 압축 실패 — Windows 10 1803 이상이면 tar.exe 가 내장입니다" }
Remove-Item $RawTar -Force

Write-Host "[3/3] 체크섬"
$Hash = (Get-FileHash $Tar -Algorithm SHA256).Hash.ToLower()
"$Hash  ${Img}_${Sha}.tar.gz" | Set-Content -Encoding ascii "$Tar.sha256"
Get-Content "$Tar.sha256"

Write-Host ""
Write-Host "완료. 반입할 것:"
Write-Host "  $Tar  (+ .sha256)"
Write-Host "  deploy\            (docker-compose.yml · onprem\)"
Write-Host "  .env               (.env.example 복사 후 APP_PASSWORD · SECRET_KEY 작성)"
Write-Host "서버에서:  powershell -ExecutionPolicy Bypass -File deploy\onprem\load_and_run.ps1 -Tar <tar.gz 경로>"
