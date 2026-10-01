# read-book.ps1 —— 从书里把指定行段"打开"到终端，带行号
#
# 用法：
#   .\read-book.ps1 python 5402            # Python Crash Course 第5402行起，默认 40 行
#   .\read-book.ps1 python 5402 -Count 110 # 第5402行起 110 行
#   .\read-book.ps1 js 1689 -Count 80      # JS DOM 书里 for 循环那一节
#   .\read-book.ps1 cpp 21109 -Count 60    # C++ Primer 第3章 Strings, Vectors
#   .\read-book.ps1 python -Index          # 只看章节 → 行号 索引表
#
# 行号从 -- 行号口径与 books\_src\*.index.md 一致 -- 起算。

[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [string]$Book,

    [Parameter(Position = 1)]
    [int]$Line = 1,

    [int]$Count = 40,

    [switch]$Index
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$srcDir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'books\_src'
if (-not (Test-Path $srcDir)) { throw "找不到 $srcDir" }

if ($Index) {
    Get-ChildItem $srcDir -Filter '*.index.md' | ForEach-Object { $_.Name }
    Write-Host ''
    Write-Host '看某一本的索引表：Get-Content (Join-Path books\_src python-crash-course.index.md)'
    return
}

# 注意：变量名不要用 $book —— PowerShell 变量不分大小写，会和参数 $Book 撞车并被强制转成字符串。
$fileInfo = Get-ChildItem $srcDir -Filter "*$Book*.txt" | Select-Object -First 1
if (-not $fileInfo) { throw "books\_src 里没有匹配 '$Book' 的书。先跑 .\read-book.ps1 x -Index 看有哪些。" }

$lines = Get-Content -LiteralPath $fileInfo.FullName -Encoding UTF8
$total = $lines.Count
if ($Line -gt $total) { throw "$($fileInfo.Name) 只有 $total 行，$Line 超了。" }

$end = [Math]::Min($Line + $Count - 1, $total)
Write-Host "===== $($fileInfo.Name)  L$Line..L$end / 共 $total 行 =====" -ForegroundColor DarkGray
for ($n = $Line; $n -le $end; $n++) {
    '{0,7}  {1}' -f $n, $lines[$n - 1]
}
Write-Host "===== 完 =====" -ForegroundColor DarkGray
