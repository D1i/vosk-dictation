#Requires -Version 5.1
$ErrorActionPreference='Continue'
try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host '== Закрываю приложение Vosk Dictation…'
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
  Where-Object { $_.CommandLine -and $_.CommandLine -like '*vosk-dictation*main.pyw*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }
Write-Host '== Полностью закрываю Discord (сброс RPC-каналов)…'
Get-Process Discord -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
Start-Sleep -Seconds 3
Write-Host '== Запускаю Discord заново…'
$upd = Join-Path $env:LOCALAPPDATA 'Discord\Update.exe'
if (Test-Path $upd) { Start-Process $upd -ArgumentList '--processStart','Discord.exe' }
else { Write-Host 'Update.exe не найден по' $upd }
Write-Host '== Жду, пока Discord откроет RPC-канал…'
$ok=$false
for ($i=0; $i -lt 45; $i++) {
  Start-Sleep -Seconds 1
  try { $p = Get-ChildItem '\\.\pipe\' -EA SilentlyContinue | Where-Object { $_.Name -like 'discord-ipc-*' } } catch { $p=$null }
  if ($p) { $ok=$true; Write-Host ("   канал появился через {0} с: {1}" -f ($i+1), ($p.Name -join ',')); break }
}
if (-not $ok) { Write-Host '   канал так и не появился за 45 с' }
Start-Sleep -Seconds 3
Write-Host '== Запускаю приложение…'
Start-Process (Join-Path $Root '.venv\Scripts\pythonw.exe') -ArgumentList ('"'+(Join-Path $Root 'app\main.pyw')+'"') -WorkingDirectory $Root
Start-Sleep -Seconds 10
Write-Host '== Последние строки журнала:'
Get-Content (Join-Path $Root 'logs\app.log') -Tail 8 -Encoding UTF8 | Out-Host
Start-Sleep -Seconds 10
