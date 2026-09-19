# [사내 서버 · Windows] 운영 점검 — 언제든 실행. 아무것도 바꾸지 않는다.
#
#   powershell -ExecutionPolicy Bypass -File deploy\onprem\check.ps1
#
# 보는 것: 컨테이너 상태·헬스 · /healthz(버전·DB 종류) · 보안 헤더 · 볼륨 · 디스크 · 최근 로그
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
$Fail = $false

$HostPort = "8080"
if (Test-Path ".env") {
    $line = Get-Content ".env" | Where-Object { $_ -match "^HOST_PORT=(.+)$" } | Select-Object -First 1
    if ($line) { $HostPort = ($line -replace "^HOST_PORT=", "").Trim() }
}

Write-Host "── 컨테이너 ──────────────────────────────────────────────"
docker compose -f deploy/docker-compose.yml ps
$Health = "not-running"
try {
    $h = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' threeon-budget 2>$null
    if ($LASTEXITCODE -eq 0 -and $h) { $Health = $h.Trim() }
} catch {}
Write-Host "헬스: $Health"
if ($Health -ne "healthy") { $Fail = $true }

Write-Host ""
Write-Host "── /healthz ──────────────────────────────────────────────"
$Base = "http://127.0.0.1:$HostPort"
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "$Base/healthz" -TimeoutSec 5
    Write-Host $r.Content
    if ($r.Content -notmatch '"commit":"[0-9a-f]{7}"') { Write-Host "⚠ commit 이 비어 있습니다 — build_image 로 만든 이미지가 아닙니다"; $Fail = $true }
} catch {
    Write-Host "⚠ 응답 없음 (포트 $HostPort)"; $Fail = $true
}

Write-Host ""
Write-Host "── 보안 헤더 (Caddy 없이 앱이 직접 낸다 — 6-8) ──────────"
$hdr = @{}
try { $hdr = (Invoke-WebRequest -UseBasicParsing -Uri "$Base/healthz" -TimeoutSec 5).Headers } catch {}
foreach ($h in @("x-content-type-options", "x-frame-options", "referrer-policy")) {
    $present = $false
    foreach ($k in $hdr.Keys) { if ($k -ieq $h) { $present = $true } }
    if ($present) { Write-Host "  ✓ $h" } else { Write-Host "  ✗ $h 없음"; $Fail = $true }
}

Write-Host ""
Write-Host "── 볼륨·디스크 ───────────────────────────────────────────"
$vols = docker volume ls --format '{{.Name}}' | Where-Object { $_ -match "budget_data|pg_data" }
if ($vols) { $vols | ForEach-Object { Write-Host "  $_" } } else { Write-Host "  ⚠ budget_data 볼륨이 없습니다" }
docker system df | ForEach-Object { Write-Host "  $_" }

Write-Host ""
Write-Host "── 최근 로그 20줄 ────────────────────────────────────────"
try { docker compose -f deploy/docker-compose.yml logs --tail=20 app | ForEach-Object { Write-Host "  $_" } } catch {}

Write-Host ""
if (-not $Fail) { Write-Host "점검 결과: 정상"; exit 0 }
else { Write-Host "점검 결과: 이상 있음 (위 ⚠/✗ 항목)"; exit 1 }
