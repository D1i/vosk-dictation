#Requires -Version 5.1
<#
  Скачивает встраиваемый Python для Windows (python.org) в build\ —
  он нужен tools\build_dist.py для переносимой версии и установщика.
  Проверки: MD5 с python.org и цифровые подписи всех .exe/.dll/.pyd
  (Python Software Foundation; у vcruntime — Microsoft).
  Журнал: build\fetch_python.log
#>
param(
    [string]$Version = '3.12.10',
    [string]$Md5 = 'fe8ef205f2e9c3ba44d0cf9954e1abd3'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Root  = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Build = Join-Path $Root 'build'
New-Item -ItemType Directory -Force $Build | Out-Null
$Name = "python-$Version-embed-amd64.zip"
$Url  = "https://www.python.org/ftp/python/$Version/$Name"
$Zip  = Join-Path $Build $Name
$Part = "$Zip.part"
$Log  = Join-Path $Build 'fetch_python.log'
try { Start-Transcript -Path $Log -Force | Out-Null } catch {}

$code = 0
try {
    Write-Host "Скачиваю $Url"
    $ErrorActionPreference = 'Continue'
    & curl.exe -L --fail --retry 3 --silent --show-error -o $Part $Url | Out-Host
    $curlCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($curlCode -ne 0) { throw "curl завершился с кодом $curlCode" }

    $size = (Get-Item $Part).Length
    $md5  = (Get-FileHash $Part -Algorithm MD5).Hash.ToLower()
    $sha  = (Get-FileHash $Part -Algorithm SHA256).Hash.ToLower()
    Write-Host "Размер: $size байт"
    Write-Host "MD5:    $md5"
    Write-Host "SHA256: $sha"
    if ($Md5 -and $md5 -ne $Md5.ToLower()) {
        throw "MD5 $md5 не совпадает с опубликованным на python.org ($Md5)"
    }
    Write-Host 'MD5 совпадает с python.org'

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('vd-python-check-' + [guid]::NewGuid().ToString('N'))
    [IO.Compression.ZipFile]::ExtractToDirectory($Part, $tmp)
    try {
        $pe = @(Get-ChildItem $tmp -Recurse -File | Where-Object { $_.Extension -in '.exe', '.dll', '.pyd' })
        if ($pe.Count -lt 5 -or -not (Test-Path (Join-Path $tmp 'pythonw.exe'))) { throw 'в архиве нет pythonw.exe — это не встраиваемый Python' }
        $bad = 0
        foreach ($f in $pe) {
            $sig = Get-AuthenticodeSignature $f.FullName
            $subject = if ($sig.SignerCertificate) { $sig.SignerCertificate.Subject } else { '-' }
            $ok = ($sig.Status -eq 'Valid') -and ($subject -match 'O=Python Software Foundation|O=Microsoft Corporation')
            if (-not $ok) { $bad++ }
            Write-Host ("  {0,-28} {1,-6} {2}" -f $f.Name, $sig.Status, ($subject -replace ',.*$', ''))
        }
        if ($bad -gt 0) { throw "у $bad файлов нет действительной подписи PSF/Microsoft" }
        Write-Host "Подписи проверены: $($pe.Count) файлов"
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
    Move-Item -Force $Part $Zip
    Write-Host "OK: $Zip"
} catch {
    Write-Host "ОШИБКА: $($_.Exception.Message)"
    $code = 1
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}
exit $code
