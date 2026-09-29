# 애니위키 키트 설치: 도구(파이썬) 받기 → 위키 엔진(openNAMU) 받기 → 빈 위키 만들기 → 첫 화면
# 이미 끝난 단계는 건너뛰므로, 중간에 끊겨도 다시 실행하면 이어서 진행합니다.
param(
    [switch]$ToolsOnly   # 도구(파이썬)만 받고 끝냄 — 관리판을 처음 열 때 씀
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root  = Split-Path $PSScriptRoot -Parent
$Tools = Join-Path $Root 'tools'
$Wiki  = Join-Path $Root 'wiki'
$cfg   = Get-Content (Join-Path $Root 'sources.json') -Raw -Encoding UTF8 | ConvertFrom-Json
New-Item -ItemType Directory -Force $Tools, $Wiki | Out-Null

function Step($msg) { Write-Host ''; Write-Host "== $msg" -ForegroundColor Cyan }

function Get-Verified($url, $out, $sha256) {
    if ((Test-Path $out) -and (Get-FileHash $out -Algorithm SHA256).Hash -eq $sha256) { return }
    Write-Host "  받는 중: $url"
    Invoke-WebRequest $url -OutFile $out -UseBasicParsing
    $h = (Get-FileHash $out -Algorithm SHA256).Hash
    if ($h -ne $sha256) { Remove-Item $out; throw "해시가 맞지 않습니다: $out`n  기대 $sha256`n  실제 $h" }
}

# ---------------------------------------------------------------- 1. 도구
Step '1/3 도구 준비 (파이썬)'
$t = $cfg.tools
$pyZip = Join-Path $Tools 'python.zip'
Get-Verified $t.python.url $pyZip $t.python.sha256
$python = Join-Path $Tools 'python\python.exe'
if (-not (Test-Path $python)) { Expand-Archive $pyZip (Join-Path $Tools 'python') -Force }
Write-Host '  완료'
if ($ToolsOnly) { exit 0 }

# ---------------------------------------------------------------- 2. 위키 엔진
Step '2/3 위키 엔진(openNAMU) 받기'
$exe = Join-Path $Wiki 'main.amd64.exe'
Get-Verified $t.opennamu.url $exe $t.opennamu.sha256
Write-Host '  완료'

# ---------------------------------------------------------------- 3. 빈 위키 만들기
Step '3/3 빈 위키 만들기'
$Port = 3001   # openNAMU 내부 포트 (관리판은 중계 서버를 3000 에 띄움)
function Wait-Server($sec) {
    foreach ($i in 1..$sec) {
        if ($(try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', $Port); $c.Close(); $true } catch { $false })) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}
if (-not (Test-Path (Join-Path $Wiki 'data.db'))) {
    $p = Start-Process $exe -ArgumentList "$Port", '--localhost' -WorkingDirectory $Wiki -WindowStyle Hidden -PassThru
    $ok = Wait-Server 120
    Stop-Process -Id $p.Id -Force
    Start-Sleep -Seconds 1
    if (-not $ok) { throw "openNAMU 가 시작되지 않았습니다. $Port 번 포트를 다른 프로그램이 쓰고 있는지 확인하세요." }
}
$env:PYTHONUTF8 = '1'
& $python (Join-Path $PSScriptRoot 'add_frontpage.py') $Wiki
Write-Host ''
Write-Host '설치 완료. 관리판에서 [켜기]를 누르세요.' -ForegroundColor Green
