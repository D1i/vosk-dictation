#Requires -Version 5.1
# Удаление Vosk Dictation из автозапуска и меню «Пуск». Папку проекта можно удалить вручную.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$Root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'
$Main   = Join-Path $Root 'app\main.pyw'

if (Test-Path $VenvPy) { & $VenvPy $Main --quit | Out-Null }
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$run = (Get-ItemProperty -Path $runKey -Name 'VoskDictation' -ErrorAction SilentlyContinue).VoskDictation
if ($run -and $run.Contains($Root)) { Remove-ItemProperty -Path $runKey -Name 'VoskDictation' }
# удаляем только ярлыки, которые ведут в эту папку
$ws = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
    $lnk = Join-Path $dir 'Vosk Dictation.lnk'
    if (Test-Path $lnk) {
        $sc = $ws.CreateShortcut($lnk)
        if ("$($sc.TargetPath) $($sc.Arguments)".StartsWith($Root, [StringComparison]::OrdinalIgnoreCase) -or
            "$($sc.Arguments)".Contains($Root)) {
            Remove-Item -Force $lnk
        }
    }
}
Write-Host 'Vosk Dictation закрыт, убран из автозапуска, меню «Пуск» и с рабочего стола.' -ForegroundColor Green
Write-Host "Чтобы удалить полностью, удалите папку: $Root"
