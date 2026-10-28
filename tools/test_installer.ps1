#Requires -Version 5.1
<#
  Проверка установщика dist\VoskDictation-*-setup.exe:
  тихая установка в build\test-install (без ярлыков и автозапуска), проверка файлов,
  реестра, встроенного Python, распознавания и запускателя, затем тихое удаление.
  Ярлыки «Vosk Dictation» и автозапуск пользователя не должны измениться —
  скрипт это проверяет и при необходимости возвращает как было.
  Журнал: build\test_installer.log
#>
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$Root  = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Build = Join-Path $Root 'build'
$Dir   = Join-Path $Build 'test-install'
$Log   = Join-Path $Build 'test_installer.log'
New-Item -ItemType Directory -Force $Build | Out-Null
try { Start-Transcript -Path $Log -Force | Out-Null } catch {}

$script:fails = 0
function Check([string]$Name, $Ok, [string]$Detail = '') {
    if ($Ok) { $tag = 'OK  ' } else { $tag = 'FAIL'; $script:fails++ }
    Write-Host ("[{0}] {1} {2}" -f $tag, $Name, $Detail)
}
function Same-Bytes($a, $b) {
    if ($null -eq $a -and $null -eq $b) { return $true }
    if ($null -eq $a -or $null -eq $b) { return $false }
    return [Convert]::ToBase64String($a) -eq [Convert]::ToBase64String($b)
}
function Read-Bytes([string]$Path) {
    if (Test-Path -LiteralPath $Path) { return [IO.File]::ReadAllBytes($Path) } else { return $null }
}

$runKey     = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$uninstKey  = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\VoskDictation'
$settingKey = 'HKCU:\Software\VoskDictation'
$desktopLnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Vosk Dictation.lnk'
$startLnk   = Join-Path ([Environment]::GetFolderPath('Programs')) 'Vosk Dictation.lnk'

$setup = Get-ChildItem (Join-Path $Root 'dist') -Filter 'VoskDictation-*-setup.exe' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host "Установщик: $($setup.FullName)"
if (-not $setup) { Write-Host 'ОШИБКА: установщик не найден в dist\'; exit 1 }
if ((Test-Path $uninstKey) -or (Test-Path $settingKey)) {
    Write-Host 'Проверка пропущена: Vosk Dictation уже установлен через установщик на этом компьютере.'
    exit 1
}
if (Test-Path $Dir) {
    # остатки прошлой проверки — это папка только для тестов
    Remove-Item -Recurse -Force $Dir -ErrorAction SilentlyContinue
    if (Test-Path $Dir) { Write-Host "ОШИБКА: не удалось очистить $Dir"; exit 1 }
    Write-Host "Удалены остатки прошлой проверки: $Dir"
}
function Get-DirProcs([string]$Prefix) {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase) })
}

# ------------------------------------------------------------ что было до
$runBefore   = (Get-ItemProperty $runKey -Name VoskDictation -ErrorAction SilentlyContinue).VoskDictation
$deskBefore  = Read-Bytes $desktopLnk
$startBefore = Read-Bytes $startLnk
$pywBefore   = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | ForEach-Object { $_.ProcessId })
Write-Host "Автозапуск до: $runBefore"
Write-Host "Запущенные pythonw.exe: $($pywBefore -join ', ')"

try {
    # -------------------------------------------------------------- установка
    Write-Host ''
    Write-Host '=== Установка'
    $t = Measure-Command {
        $p = Start-Process -FilePath $setup.FullName -ArgumentList @('/S', '/NODESKTOP', '/NOSTARTMENU', '/NOAUTOSTART', "/D=$Dir") -Wait -PassThru
        $script:installCode = $p.ExitCode
    }
    Check 'код завершения установщика' ($installCode -eq 0) "$installCode за $([int]$t.TotalSeconds) c"
    foreach ($rel in 'python\pythonw.exe', 'python\python312._pth', 'app\main.pyw', 'app\assets\icon.ico',
                     'models\vosk-model-small-ru-0.22\am\final.mdl', 'tests\test_ru.wav',
                     'Vosk Dictation.exe', 'Uninstall.exe', 'README.txt', 'diagnose.bat', 'install.ini') {
        Check "файл $rel" (Test-Path -LiteralPath (Join-Path $Dir $rel))
    }
    $size = (Get-ChildItem $Dir -Recurse -File | Measure-Object Length -Sum).Sum
    Write-Host ("Размер установки: {0:N1} МБ" -f ($size / 1MB))
    Write-Host (Get-Content (Join-Path $Dir 'install.ini') -Raw)
    $ini = Get-Content (Join-Path $Dir 'install.ini') -Raw
    Check 'install.ini: ярлыки не создавались' (($ini -match 'startmenu=0') -and ($ini -match 'desktop=0'))
    $u = Get-ItemProperty $uninstKey -ErrorAction SilentlyContinue
    Check 'запись в «Приложениях»' ($u -and $u.InstallLocation -eq $Dir) "$($u.DisplayName) $($u.DisplayVersion) $($u.EstimatedSize) КБ"
    $runNow = (Get-ItemProperty $runKey -Name VoskDictation -ErrorAction SilentlyContinue).VoskDictation
    Check 'автозапуск не тронут' ($runNow -eq $runBefore) "$runNow"
    Check 'ярлык на рабочем столе не тронут' (Same-Bytes $deskBefore (Read-Bytes $desktopLnk))
    Check 'ярлык в «Пуске» не тронут' (Same-Bytes $startBefore (Read-Bytes $startLnk))

    # ------------------------------------------------------------ Python
    Write-Host ''
    Write-Host '=== Встроенный Python'
    $py = Join-Path $Dir 'python\python.exe'
    $out = & $py -c "import sys; sys.stdout.reconfigure(encoding='utf-8'); import vosk, sounddevice, pystray, PIL; print(sys.version); print(sys.executable); print(sys.path); print('flags: isolated=%d site=%d' % (sys.flags.isolated, not sys.flags.no_site)); print('imports OK')" 2>&1 | Out-String
    Write-Host $out
    Check 'импорт пакетов' ($out -match 'imports OK')
    Check 'используется встроенный Python' ($out -match [regex]::Escape("$Dir\python\python.exe"))

    $out = & $py (Join-Path $Dir 'app\main.pyw') --list-devices 2>&1 | Out-String
    Write-Host $out
    Check 'PortAudio: список устройств' ($LASTEXITCODE -eq 0) "код $LASTEXITCODE"

    $out = & $py (Join-Path $Dir 'app\main.pyw') --selftest (Join-Path $Dir 'tests\test_ru.wav') 2>&1 | Out-String
    Write-Host $out
    Check 'распознавание тестовой записи' ($out -match 'Привет, это проверка голосового ввода') "код $LASTEXITCODE"

    # ------------------------------------------------------------ запускатель
    Write-Host ''
    Write-Host '=== Запускатель «Vosk Dictation.exe»'
    $appLog = Join-Path $Dir 'logs\app.log'
    $before = @(Select-String -Path $appLog -Pattern 'model loaded' -ErrorAction SilentlyContinue).Count
    Start-Process -FilePath (Join-Path $Dir 'Vosk Dictation.exe') -ArgumentList @('--selftest', ('"' + (Join-Path $Dir 'tests\test_ru.wav') + '"'))
    $after = $before
    for ($i = 0; $i -lt 30 -and $after -le $before; $i++) {
        Start-Sleep -Seconds 1
        $after = @(Select-String -Path $appLog -Pattern 'model loaded' -ErrorAction SilentlyContinue).Count
    }
    Check 'запускатель стартует программу из своей папки' ($after -gt $before) "записей в журнале: $before -> $after"

    $pyPrefix = (Join-Path $Dir 'python') + '\'
    for ($i = 0; $i -lt 60 -and (Get-DirProcs $pyPrefix).Count -gt 0; $i++) { Start-Sleep -Milliseconds 500 }
    Check 'самопроверка через запускатель завершилась' ((Get-DirProcs $pyPrefix).Count -eq 0)

    $out = & $py (Join-Path $Dir 'app\main.pyw') --quit --only-from $Dir 2>&1 | Out-String
    Check '--quit --only-from не трогает чужую копию' ($LASTEXITCODE -ne 0) "код $LASTEXITCODE"
    Get-Content $appLog -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 6 | ForEach-Object { Write-Host "  log: $_" }

    # «зависший» процесс встроенного Python — удаление должно его завершить
    $stuck = Start-Process -FilePath (Join-Path $Dir 'python\pythonw.exe') -ArgumentList @('-c', '"import time; time.sleep(300)"') -PassThru
    Start-Sleep -Seconds 1
    Check 'запущен процесс-заглушка' (-not $stuck.HasExited) "PID $($stuck.Id)"
} finally {
    # ------------------------------------------------------------ удаление
    Write-Host ''
    Write-Host '=== Удаление'
    $un = Join-Path $Dir 'Uninstall.exe'
    if (Test-Path $un) {
        Start-Process -FilePath $un -ArgumentList '/S' -Wait
        for ($i = 0; $i -lt 60 -and (Test-Path $Dir); $i++) { Start-Sleep -Milliseconds 500 }
    }
    Check 'папка установки удалена' (-not (Test-Path $Dir))
    if ($stuck) {
        $alive = Get-Process -Id $stuck.Id -ErrorAction SilentlyContinue
        Check 'удаление завершило процессы из папки программы' (-not $alive)
        if ($alive) { Stop-Process -Id $stuck.Id -Force -ErrorAction SilentlyContinue }
    }
    if (Test-Path $Dir) { Get-ChildItem $Dir -Recurse | ForEach-Object { Write-Host "  осталось: $($_.FullName)" } }
    Check 'запись в «Приложениях» удалена' (-not (Test-Path $uninstKey))
    Check 'ключ настроек удалён' (-not (Test-Path $settingKey))

    # ---------------------------------------- ярлыки и автозапуск пользователя
    $runAfter = (Get-ItemProperty $runKey -Name VoskDictation -ErrorAction SilentlyContinue).VoskDictation
    Check 'автозапуск пользователя сохранён' ($runAfter -eq $runBefore) "$runAfter"
    if ($runAfter -ne $runBefore) {
        if ($null -eq $runBefore) { Remove-ItemProperty $runKey -Name VoskDictation -ErrorAction SilentlyContinue }
        else { Set-ItemProperty $runKey -Name VoskDictation -Value $runBefore }
        Write-Host '  -> автозапуск восстановлен'
    }
    foreach ($pair in @(@($desktopLnk, $deskBefore, 'рабочем столе'), @($startLnk, $startBefore, '«Пуске»'))) {
        $now = Read-Bytes $pair[0]
        Check "ярлык в $($pair[2]) сохранён" (Same-Bytes $pair[1] $now)
        if (-not (Same-Bytes $pair[1] $now) -and $null -ne $pair[1]) {
            [IO.File]::WriteAllBytes($pair[0], $pair[1])
            Write-Host '  -> ярлык восстановлен'
        }
    }
    $pywAfter = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | ForEach-Object { $_.ProcessId })
    $lost = @($pywBefore | Where-Object { $pywAfter -notcontains $_ })
    Check 'запущенная программа пользователя не закрыта' ($lost.Count -eq 0) "было: $($pywBefore -join ', '); стало: $($pywAfter -join ', ')"

    Write-Host ''
    if ($script:fails -eq 0) { Write-Host 'ИТОГ: все проверки пройдены' } else { Write-Host "ИТОГ: ошибок — $($script:fails)" }
    try { Stop-Transcript | Out-Null } catch {}
}
exit $script:fails
