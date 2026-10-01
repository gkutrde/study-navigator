# verify-w3c.ps1 —— 用 W3C 官方校验引擎（vnu.jar，validator.w3.org/nu 背后那一套）校验本目录 HTML
#
# 用法：
#   pwsh -File verify-w3c.ps1
#   pwsh -File verify-w3c.ps1 -Files home.html,home-min.html
#
# 退出码：0 = 全部符合期望；1 = 有文件不符合期望；2 = 找不到 vnu.jar
#
# 期望值写死在下面：三档成品要求 0 条消息；_bad-structure.html 是反面教材，要求有 error。

param(
  [string[]]$Files = @('home.html', 'home-min.html', 'home-alt.html', '_bad-structure.html'),
  [string]$Jar
)

$期望 = @{
  'home.html'           = 'clean'
  'home-min.html'       = 'clean'
  'home-alt.html'       = 'clean'
  '_bad-structure.html' = 'dirty'
}

if (-not $Jar) { $Jar = $env:VNU_JAR }
if (-not $Jar -or -not (Test-Path $Jar)) {
  $候选 = @(
    (Join-Path $PSScriptRoot 'node_modules\vnu-jar\build\dist\vnu.jar'),
    (Join-Path $env:TEMP 'vnu-check\node_modules\vnu-jar\build\dist\vnu.jar')
  )
  foreach ($c in $候选) { if (Test-Path $c) { $Jar = $c; break } }
}
if (-not $Jar -or -not (Test-Path $Jar)) {
  $找 = Get-ChildItem -Path $env:TEMP -Recurse -Filter vnu.jar -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($找) { $Jar = $找.FullName }
}
if (-not $Jar -or -not (Test-Path $Jar)) {
  Write-Host "找不到 vnu.jar。装一次就有（约 31 MB，不装进项目目录）：" -ForegroundColor Yellow
  Write-Host '  npm install vnu-jar --prefix "$env:TEMP\vnu-check" --no-audit --no-fund' -ForegroundColor Cyan
  Write-Host '  然后重跑本脚本；或设 $env:VNU_JAR 指向 jar 路径。'
  exit 2
}

Write-Host "校验引擎：vnu.jar" -ForegroundColor DarkGray
Write-Host ("版本：" + (java -jar $Jar --version))
Write-Host ""

$结果 = @()
foreach ($f in $Files) {
  $路径 = Join-Path $PSScriptRoot $f
  if (-not (Test-Path $路径)) { Write-Host "跳过（不存在）：$f" -ForegroundColor Yellow; continue }
  $raw = (java -jar $Jar --format json $路径 2>&1 | Out-String)
  try { $msgs = @(($raw | ConvertFrom-Json).messages) } catch { $msgs = @() }
  $错 = @($msgs | Where-Object { $_.type -eq 'error' }).Count
  $其他 = @($msgs | Where-Object { $_.type -ne 'error' }).Count

  $要 = $期望[$f]
  $符合 = if ($要 -eq 'dirty') { $错 -gt 0 } elseif ($要) { $错 -eq 0 -and $其他 -eq 0 } else { $true }

  $结果 += [pscustomobject]@{
    文件 = $f; 期望 = if ($要) { $要 } else { '(未指定)'; }; error = $错; 其他 = $其他
    判定 = if ($符合) { '符合期望' } else { '不符合期望' }
  }

  if ($msgs.Count) {
    Write-Host "── $f ──" -ForegroundColor DarkGray
    $msgs | ForEach-Object { Write-Host ("  [{0}] 行{1} 列{2}: {3}" -f $_.type, $_.lastLine, $_.lastColumn, $_.message) }
  }
}

Write-Host ""
$结果 | Format-Table -AutoSize
$坏 = @($结果 | Where-Object { $_.判定 -ne '符合期望' })
if ($坏.Count) {
  Write-Host ("有 {0} 份文件不符合期望：" -f $坏.Count) -ForegroundColor Red
  $坏 | ForEach-Object { Write-Host ("  " + $_.文件) }
  exit 1
}
Write-Host "全部符合期望：三档成品 0 条消息（合法），反面教材有 error（预期如此）。" -ForegroundColor Green
exit 0
