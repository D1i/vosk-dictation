; Vosk Dictation — запускатель переносимой версии.
; Запускает python\pythonw.exe app\main.pyw из своей папки и сразу завершается.
; Сборка: makensis -INPUTCHARSET UTF8 -DOUTFILE=<exe> -DICON=<ico> -DVERSION=1.0.0 launcher.nsi

Unicode true
Target amd64-unicode
ManifestDPIAware true
ManifestSupportedOS all
RequestExecutionLevel user
SilentInstall silent
SetCompressor zlib
CRCCheck off

!ifndef VERSION
  !define VERSION "1.0.0"
!endif
!ifndef OUTFILE
  !define OUTFILE "Vosk Dictation.exe"
!endif

Name "Vosk Dictation"
Caption "Vosk Dictation"
OutFile "${OUTFILE}"
!ifdef ICON
  Icon "${ICON}"
!endif

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "Vosk Dictation"
VIAddVersionKey /LANG=1033 "FileDescription" "Vosk Dictation"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Vosk Dictation"
VIAddVersionKey /LANG=1033 "OriginalFilename" "Vosk Dictation.exe"

!include "FileFunc.nsh"

Section
  ${GetParameters} $R0
  IfFileExists "$EXEDIR\python\pythonw.exe" found
    MessageBox MB_OK|MB_ICONSTOP "Не найден python\pythonw.exe рядом с программой.$\r$\nРаспакуйте архив целиком и запустите снова."
    Quit
  found:
  SetOutPath "$EXEDIR"
  Exec '"$EXEDIR\python\pythonw.exe" "$EXEDIR\app\main.pyw" $R0'
SectionEnd
