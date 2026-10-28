#Requires -Version 5.1
$ErrorActionPreference='Continue'
try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host '== Закрываю запущенные копии Vosk Dictation…'
$ids=@()
Get-Process pythonw,python -EA SilentlyContinue | Where-Object { $_.Path -and $_.Path -like '*vosk-dictation*' } | ForEach-Object { $ids += $_.Id }
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -EA SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -like '*vosk-dictation*main.pyw*' } | ForEach-Object { $ids += $_.ProcessId }
($ids | Sort-Object -Unique) | ForEach-Object { Write-Host ("  завершаю PID "+$_); Stop-Process -Id $_ -Force -EA SilentlyContinue }
Start-Sleep 2
Write-Host '== Запускаю приложение заново…'
Start-Process -FilePath (Join-Path $Root '.venv\Scripts\pythonw.exe') -ArgumentList ('"'+(Join-Path $Root 'app\main.pyw')+'"') -WorkingDirectory $Root
Start-Sleep 8
Write-Host '== Последние строки журнала:'
Get-Content (Join-Path $Root 'logs\app.log') -Tail 6 -Encoding utf8 | Out-Host
Start-Sleep 6
