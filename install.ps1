#Requires -Version 5.1
<#
  Установка Vosk Dictation: Python-окружение, зависимости, модель Vosk,
  ярлык в меню «Пуск», автозапуск и первый запуск.

  Обычно запускается через install.bat. Параметры:
    -NoAutostart        не добавлять в автозагрузку
    -NoLaunch           не запускать приложение в конце
    -SkipSelftest       не проверять распознавание на тестовой записи
    -NoDesktopShortcut  не создавать ярлык на рабочем столе
    -ShortcutsOnly      только (пере)создать ярлыки в «Пуске» и на рабочем столе
#>
param(
    [switch]$NoAutostart,
    [switch]$NoLaunch,
    [switch]$SkipSelftest,
    [switch]$NoDesktopShortcut,
    [switch]$ShortcutsOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$Root      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv      = Join-Path $Root '.venv'
$VenvPy    = Join-Path $Venv 'Scripts\python.exe'
$VenvPyw   = Join-Path $Venv 'Scripts\pythonw.exe'
$Main      = Join-Path $Root 'app\main.pyw'
$Req       = Join-Path $Root 'requirements.txt'
$ModelName = 'vosk-model-small-ru-0.22'
$ModelUrl  = "https://alphacephei.com/vosk/models/$ModelName.zip"
$ModelsDir = Join-Path $Root 'models'
$ModelDir  = Join-Path $ModelsDir $ModelName
$ToolsDir  = Join-Path $Root '.tools'
$LogsDir   = Join-Path $Root 'logs'
Set-Location $Root

function Step([string]$t) { Write-Host ''; Write-Host "==> $t" -ForegroundColor Cyan }
function Ok([string]$t)   { Write-Host "    $t" -ForegroundColor Green }
function Warn([string]$t) { Write-Host "    $t" -ForegroundColor Yellow }

# Запуск внешней программы с выводом на экран. Возвращает код возврата.
# (В аргументах не должно быть двойных кавычек — PowerShell 5.1 их портит.)
function Run([string]$Exe, [string[]]$Arguments) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments | Out-Host
        return [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
}

# Тихий запуск. Возвращает объект { Code; Out = массив строк }.
function RunQuiet([string]$Exe, [string[]]$Arguments) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $out = @(& $Exe @Arguments 2>$null)
        return [pscustomobject]@{ Code = [int]$LASTEXITCODE; Out = $out }
    } catch {
        return [pscustomobject]@{ Code = 9999; Out = @() }
    } finally {
        $ErrorActionPreference = $old
    }
}

function Find-Uv {
    $cands = @()
    $cmd = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($cmd) { $cands += $cmd.Source }
    $cands += @(
        (Join-Path $ToolsDir 'uv.exe'),
        (Join-Path $ToolsDir 'bin\uv.exe'),
        (Join-Path $env:USERPROFILE '.local\bin\uv.exe'),
        (Join-Path $env:USERPROFILE '.cargo\bin\uv.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\uv.exe')
    )
    foreach ($c in $cands) {
        if ($c -and (Test-Path $c)) {
            if ((RunQuiet $c @('--version')).Code -eq 0) { return $c }
        }
    }
    return $null
}

function Install-Uv {
    Warn 'Python не найден — ставлю uv (менеджер Python от Astral) в папку .tools'
    New-Item -ItemType Directory -Force $ToolsDir | Out-Null
    $env:UV_UNMANAGED_INSTALL = $ToolsDir
    try {
        $script = Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' -UseBasicParsing
        Invoke-Expression $script | Out-Host
    } finally {
        Remove-Item Env:\UV_UNMANAGED_INSTALL -ErrorAction SilentlyContinue
    }
    $found = Find-Uv
    if (-not $found) { throw 'Не удалось установить uv. Установите Python 3.10+ с python.org и запустите установку снова.' }
    return $found
}

function New-AppShortcut([string]$Path) {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($Path)
    $lnk.TargetPath = $VenvPyw
    $lnk.Arguments = "`"$Main`""
    $lnk.WorkingDirectory = $Root
    $lnk.IconLocation = (Join-Path $Root 'app\assets\icon.ico') + ',0'
    $lnk.Description = 'Голосовой ввод Vosk (Ctrl+Space)'
    $lnk.Save()
    $chk = $ws.CreateShortcut($Path)
    Ok $Path
    Write-Host ("      -> {0} {1}" -f $chk.TargetPath, $chk.Arguments)
}

function Install-Shortcuts {
    Step 'Ярлыки'
    if (-not (Test-Path $VenvPyw)) { throw 'Приложение ещё не установлено: сначала запустите install.bat' }
    $startLnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'Vosk Dictation.lnk'
    New-AppShortcut $startLnk
    if (-not $NoDesktopShortcut) {
        New-AppShortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Vosk Dictation.lnk')
    }
    # такой же ярлык в папке проекта
    Copy-Item -Force $startLnk (Join-Path $Root 'Vosk Dictation.lnk')
}

function Find-Python {
    $probe = 'import sys; print(sys.executable); print(sys.version_info[0]*100+sys.version_info[1]); print(64 if sys.maxsize > 2**32 else 32)'
    $cands = @(
        @('py', '-3.13'), @('py', '-3.12'), @('py', '-3.11'), @('py', '-3.10'),
        @('py', '-3'), @('python', ''), @('python3', '')
    )
    foreach ($c in $cands) {
        if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
        $a = @()
        if ($c[1]) { $a += $c[1] }
        $a += @('-c', $probe)
        $r = RunQuiet $c[0] $a
        if ($r.Code -ne 0 -or $r.Out.Count -lt 3) { continue }
        $exe = "$($r.Out[0])".Trim()
        $ver = 0; $bits = 0
        if (-not [int]::TryParse("$($r.Out[1])".Trim(), [ref]$ver)) { continue }
        if (-not [int]::TryParse("$($r.Out[2])".Trim(), [ref]$bits)) { continue }
        if ($ver -ge 309 -and $ver -lt 400 -and $bits -eq 64 -and (Test-Path $exe)) {
            return [pscustomobject]@{ Path = $exe; Version = ('{0}.{1}' -f [math]::Floor($ver / 100), ($ver % 100)) }
        }
    }
    return $null
}

if ($ShortcutsOnly) {
    New-Item -ItemType Directory -Force $LogsDir | Out-Null
    try { Start-Transcript -Path (Join-Path $LogsDir 'shortcuts.log') -Force | Out-Null } catch {}
    $code = 0
    try {
        Install-Shortcuts
        Write-Host ''
        Write-Host '  Готово: ярлык «Vosk Dictation» на рабочем столе и в меню «Пуск».' -ForegroundColor Green
        Write-Host ''
    } catch {
        Write-Host "  ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
        $code = 1
    }
    try { Stop-Transcript | Out-Null } catch {}
    exit $code
}

New-Item -ItemType Directory -Force $LogsDir | Out-Null
try { Start-Transcript -Path (Join-Path $LogsDir 'install.log') -Force | Out-Null } catch {}

$exitCode = 0
try {
    Write-Host ''
    Write-Host '  Vosk Dictation — установка' -ForegroundColor White
    Write-Host "  Папка: $Root"

    # ----------------------------------------------------------------------
    Step 'Закрываю запущенную копию приложения (если есть)'
    if (Test-Path $VenvPy) {
        if ((RunQuiet $VenvPy @($Main, '--quit')).Code -eq 0) { Ok 'Закрыта' } else { Ok 'Не была запущена' }
    } else {
        Ok 'Пропускаю — первая установка'
    }

    # ----------------------------------------------------------------------
    Step 'Готовлю Python-окружение (.venv)'
    $uv = Find-Uv
    if ($uv) { Ok "uv: $uv" }
    $venvOk = $false
    if (Test-Path $VenvPy) {
        $venvOk = (RunQuiet $VenvPy @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)')).Code -eq 0
    }
    if ($venvOk) {
        Ok 'Окружение уже есть'
    } else {
        if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
        $py = Find-Python
        if ($py) {
            Ok "Python $($py.Version): $($py.Path)"
            if ($uv) {
                $code = Run $uv @('venv', '--python', $py.Path, $Venv)
            } else {
                $code = Run $py.Path @('-m', 'venv', $Venv)
            }
        } else {
            if (-not $uv) { $uv = Install-Uv; Ok "uv: $uv" }
            Warn 'Скачиваю Python 3.12 через uv'
            $code = Run $uv @('venv', '--python', '3.12', $Venv)
        }
        if ($code -ne 0 -or -not (Test-Path $VenvPy)) { throw "Не удалось создать окружение (код $code)" }
        Ok 'Окружение создано'
    }

    # ----------------------------------------------------------------------
    Step 'Ставлю зависимости (vosk, sounddevice, pystray, Pillow)'
    if ($uv) {
        $code = Run $uv @('pip', 'install', '--python', $VenvPy, '-r', $Req)
    } else {
        if ((RunQuiet $VenvPy @('-m', 'pip', '--version')).Code -ne 0) {
            $null = Run $VenvPy @('-m', 'ensurepip', '--upgrade')
        }
        $code = Run $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $Req)
    }
    if ($code -ne 0) { throw "Не удалось установить зависимости (код $code)" }
    if ((RunQuiet $VenvPy @('-c', 'import vosk, sounddevice, pystray, PIL')).Code -ne 0) {
        $null = Run $VenvPy @('-c', 'import vosk, sounddevice, pystray, PIL')
        throw 'Зависимости установились, но не импортируются (ошибка выше).'
    }
    Ok 'Готово'

    # ----------------------------------------------------------------------
    Step "Модель распознавания $ModelName (~45 МБ)"
    if (Test-Path (Join-Path $ModelDir 'am\final.mdl')) {
        Ok 'Уже скачана'
    } else {
        New-Item -ItemType Directory -Force $ModelsDir | Out-Null
        $zip = Join-Path $ModelsDir "$ModelName.zip"
        if (Test-Path $zip) { Remove-Item -Force $zip }
        if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
            $code = Run 'curl.exe' @('-L', '--fail', '--retry', '3', '-o', $zip, $ModelUrl)
            if ($code -ne 0) { throw "Не удалось скачать модель (curl, код $code): $ModelUrl" }
        } else {
            Invoke-WebRequest -Uri $ModelUrl -OutFile $zip -UseBasicParsing
        }
        Ok 'Распаковываю'
        $extracted = $false
        if (Get-Command tar.exe -ErrorAction SilentlyContinue) {
            $extracted = (Run 'tar.exe' @('-xf', $zip, '-C', $ModelsDir)) -eq 0
        }
        if (-not $extracted) { Expand-Archive -Path $zip -DestinationPath $ModelsDir -Force }
        Remove-Item -Force $zip
        if (-not (Test-Path (Join-Path $ModelDir 'am\final.mdl'))) { throw "Модель распакована не туда: ожидалась папка $ModelDir" }
        Ok 'Модель готова'
    }

    # ----------------------------------------------------------------------
    if (-not $SkipSelftest) {
        Step 'Проверяю распознавание на тестовой записи'
        $code = Run $VenvPy @($Main, '--selftest', (Join-Path $Root 'tests\test_ru.wav'))
        if ($code -eq 0) { Ok 'Распознавание работает' } else { Warn "Самопроверка вернула код $code — смотрите вывод выше" }
    }

    # ----------------------------------------------------------------------
    Install-Shortcuts

    Step 'Автозапуск при входе в Windows'
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    if ($NoAutostart) {
        Remove-ItemProperty -Path $runKey -Name 'VoskDictation' -ErrorAction SilentlyContinue
        Ok 'Выключен (можно включить в меню значка в трее)'
    } else {
        New-ItemProperty -Path $runKey -Name 'VoskDictation' -Value "`"$VenvPyw`" `"$Main`"" -PropertyType String -Force | Out-Null
        Ok 'Включён (выключается в меню значка в трее)'
    }

    # ----------------------------------------------------------------------
    if (-not $NoLaunch) {
        Step 'Запускаю Vosk Dictation'
        Start-Process -FilePath $VenvPyw -ArgumentList "`"$Main`"" -WorkingDirectory $Root
        Ok 'Запущено — значок микрофона появится в трее'
    }

    Write-Host ''
    Write-Host '  Готово! Кликните в любое поле ввода и нажмите Ctrl+Space.' -ForegroundColor Green
    Write-Host '  Говорите — текст печатается сам. Ещё раз Ctrl+Space — выключить.' -ForegroundColor Green
    Write-Host ''
} catch {
    Write-Host ''
    Write-Host "  ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Журнал установки: $(Join-Path $LogsDir 'install.log')" -ForegroundColor Red
    Write-Host ''
    $exitCode = 1
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}
exit $exitCode
