# 애니위키 키트 도구 준비: 윈도우용 파이썬(임베디드)을 받아 해시를 확인하고 푼다.
# 위키 엔진(openNAMU·Markdown·DokuWiki·MediaWiki)은 관리판의 '엔진' 칸에서 고르면 kit.py 가 설치한다.
#   powershell -File scripts\install.ps1            # 파이썬만 받기
#   powershell -File scripts\install.ps1 -Engine dokuwiki   # 파이썬 + 그 엔진까지(관리판 없이)
param(
    [string]$Engine = '',
    [switch]$ToolsOnly   # 예전 판과 같게 받아 둔다(지금은 기본이 도구만)
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root  = Split-Path $PSScriptRoot -Parent
$Tools = Join-Path $Root 'tools'
$cfg   = Get-Content (Join-Path $Root 'sources.json') -Raw -Encoding UTF8 | ConvertFrom-Json
New-Item -ItemType Directory -Force $Tools | Out-Null

function Get-Verified($url, $out, $sha256) {
    if ((Test-Path $out) -and (Get-FileHash $out -Algorithm SHA256).Hash -eq $sha256) { return }
    Write-Host "  받는 중: $url"
    Invoke-WebRequest $url -OutFile $out -UseBasicParsing
    $h = (Get-FileHash $out -Algorithm SHA256).Hash
    if ($h -ne $sha256) { Remove-Item $out; throw "해시가 맞지 않습니다: $out`n  기대 $sha256`n  실제 $h" }
}

Write-Host '== 도구 준비 (파이썬)' -ForegroundColor Cyan
$t = $cfg.tools
$pyZip = Join-Path $Tools 'python.zip'
Get-Verified $t.python.url $pyZip $t.python.sha256
$python = Join-Path $Tools 'python\python.exe'
if (-not (Test-Path $python)) { Expand-Archive $pyZip (Join-Path $Tools 'python') -Force }
Write-Host '  완료'
if ($Engine -eq '') { exit 0 }

$env:PYTHONUTF8 = '1'
& $python (Join-Path $PSScriptRoot 'kit.py') install $Engine
if ($LASTEXITCODE -ne 0) { throw "엔진 설치 실패: $Engine" }
