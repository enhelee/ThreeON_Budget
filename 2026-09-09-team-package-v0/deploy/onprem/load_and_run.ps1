# [사내 서버 · Windows] 반입한 이미지를 적재하고 띄운다. 업데이트도 같은 명령이다.
#
#   powershell -ExecutionPolicy Bypass -File deploy\onprem\load_and_run.ps1 -Tar <threeon-budget_<커밋>.tar.gz> [-Pg]
#
#   -Pg : PostgreSQL 컨테이너까지 함께(.env 의 PG_PASSWORD 필요, DATABASE_URL 을 postgres 로).
#         없으면 SQLite(볼륨 budget_data) 모드.
#
# 이 서버에는 인터넷이 없다는 전제다 — 절대 빌드하지 않는다(--no-build).
# 빌드가 걸리면 pip·npm 이 밖으로 나가려다 조용히 오래 실패한다.
# Windows 에서 리눅스 이미지는 Docker Desktop(WSL2 백엔드)이 필요하다.
param(
    [Parameter(Mandatory = $true)][string]$Tar,
    [switch]$Pg
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")     # 패키지 루트: 여기 .env 와 deploy\ 가 있어야 한다

function Invoke-Native([string]$What, [scriptblock]$Cmd) {
    & $Cmd
    if ($LASTEXITCODE -ne 0) { throw "$What 실패 (종료코드 $LASTEXITCODE)" }
}

if (-not (Test-Path $Tar)) { throw "파일이 없습니다: $Tar" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "docker 가 없습니다. Docker Desktop 을 설치하세요." }
Invoke-Native "docker compose 확인" { docker compose version | Out-Null }

# ── 1. 반입 파일 무결성 ─────────────────────────────────────────────
$ShaFile = "$Tar.sha256"
if (Test-Path $ShaFile) {
    Write-Host "[1/5] 체크섬 확인"
    $expected = ((Get-Content $ShaFile -First 1) -split "\s+")[0].ToLower()
    $actual = (Get-FileHash $Tar -Algorithm SHA256).Hash.ToLower()
    if ($expected -ne $actual) { throw "체크섬 불일치 — 반입 중 파일이 손상됐습니다. 기대 $expected / 실제 $actual" }
    Write-Host "      OK $actual"
} else {
    Write-Host "[1/5] 체크섬 파일(.sha256) 없음 — 건너뜀"
}

# ── 2. .env ───────────────────────────────────────────────────────────
Write-Host "[2/5] .env 확인"
if (-not (Test-Path ".env")) { throw ".env 가 없습니다 — .env.example 을 .env 로 복사해 APP_PASSWORD · SECRET_KEY 를 채우세요." }
$envLines = Get-Content ".env"
function Get-EnvValue([string]$Key) {
    $line = $envLines | Where-Object { $_ -match "^$Key=(.+)$" } | Select-Object -First 1
    if ($line) { return ($line -replace "^$Key=", "").Trim() } else { return "" }
}
foreach ($k in @("APP_PASSWORD", "SECRET_KEY")) {
    if (-not (Get-EnvValue $k)) { throw ".env 의 $k 가 비어 있습니다." }
}
$profileArgs = @()
if ($Pg) {
    if (-not (Get-EnvValue "PG_PASSWORD")) { throw "-Pg 를 쓰려면 .env 의 PG_PASSWORD 가 필요합니다." }
    $profileArgs = @("--profile", "pg")
}
$HostPort = Get-EnvValue "HOST_PORT"
if (-not $HostPort) { $HostPort = "8080" }

# ── 3. 이미지 적재 → latest 태그 ─────────────────────────────────────
Write-Host "[3/5] 이미지 적재  $Tar"
$loadOut = docker load -i $Tar
if ($LASTEXITCODE -ne 0) { throw "docker load 실패 (종료코드 $LASTEXITCODE)" }
$m = ($loadOut | Select-String "Loaded image: (.+)$" | Select-Object -Last 1)
if (-not $m) { throw "docker load 가 이미지 이름을 돌려주지 않았습니다 — 파일이 손상됐을 수 있습니다." }
$Loaded = $m.Matches[0].Groups[1].Value.Trim()
Write-Host "      적재됨: $Loaded"
Invoke-Native "docker tag" { docker tag $Loaded threeon-budget:latest }   # compose 는 latest 를 본다. 롤백 = 이전 태그를 다시 latest 로

# ── 4. 기동 (빌드 금지) ───────────────────────────────────────────────
Write-Host "[4/5] 기동  (docker compose $profileArgs up -d --no-build)"
Invoke-Native "docker compose up" { docker compose -f deploy/docker-compose.yml @profileArgs up -d --no-build }

# ── 5. 헬스체크 대기 ─────────────────────────────────────────────────
Write-Host "[5/5] /healthz 대기 (최대 90초)"
$url = "http://127.0.0.1:$HostPort/healthz"
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5
        if ($r.StatusCode -eq 200) {
            Write-Host "      $($r.Content)"
            Write-Host ""
            Write-Host "기동 완료 → http://<서버IP>:$HostPort/   (점검: deploy\onprem\check.ps1)"
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 3
}
Write-Warning "90초 안에 /healthz 가 응답하지 않았습니다. 최근 로그:"
docker compose -f deploy/docker-compose.yml logs --tail=40 app
Write-Warning "포트 $HostPort 충돌이면 .env 의 HOST_PORT 를 바꾸세요."
exit 1
