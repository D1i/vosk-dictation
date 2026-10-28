; Установщик Vosk Dictation (NSIS 3, Unicode, x64).
; Ставит программу только для текущего пользователя — права администратора не нужны.
;
; Сборка (см. tools/build_dist.py):
;   makensis -INPUTCHARSET UTF8 -DSTAGE=<папка «Vosk Dictation»> -DOUTFILE=<setup.exe> -DVERSION=1.0.0 installer.nsi
;
; Ключи командной строки установщика (удобно вместе с /S — тихая установка):
;   /NODESKTOP     не создавать ярлык на рабочем столе
;   /NOSTARTMENU   не создавать ярлык в меню «Пуск»
;   /NOAUTOSTART   не добавлять в автозапуск
;   /D=<папка>     папка установки (последним параметром, без кавычек)

Unicode true
Target amd64-unicode
ManifestDPIAware true
ManifestSupportedOS all
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
CRCCheck on

!ifndef VERSION
  !define VERSION "1.0.0"
!endif
!ifndef STAGE
  !error "Укажите -DSTAGE=<папка с файлами программы>"
!endif
!ifndef OUTFILE
  !define OUTFILE "VoskDictation-${VERSION}-setup.exe"
!endif
!ifndef SIZE_MB
  !define SIZE_MB "200"
!endif

!define APPNAME "Vosk Dictation"
!define APPID "VoskDictation"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPID}"
!define RUN_KEY "Software\Microsoft\Windows\CurrentVersion\Run"
!define SETTINGS_KEY "Software\${APPID}"
!define LNK "${APPNAME}.lnk"
!define LNK_DESC "Голосовой ввод (Ctrl+Space)"
!define MODEL "vosk-model-small-ru-0.22"

Name "${APPNAME}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "${SETTINGS_KEY}" "InstallDir"
BrandingText "${APPNAME} ${VERSION}"
ShowInstDetails nevershow
ShowUninstDetails nevershow

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "${APPNAME}"
VIAddVersionKey /LANG=1033 "FileDescription" "${APPNAME} Setup"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "${APPNAME}"

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "Sections.nsh"
!include "StrFunc.nsh"
${StrStr}
${UnStrStr}

; ----------------------------------------------------------------- интерфейс
!define MUI_ICON "${STAGE}/app/assets/icon.ico"
!define MUI_UNICON "${STAGE}/app/assets/icon.ico"
!define MUI_ABORTWARNING
!define MUI_COMPONENTSPAGE_SMALLDESC

!define MUI_WELCOMEPAGE_TITLE "Установка ${APPNAME} ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Голосовой ввод в любое текстовое поле Windows.$\r$\n$\r$\nКликните в поле ввода, нажмите Ctrl+Space и говорите — текст появится сам. Речь распознаётся прямо на компьютере (Vosk), без интернета и учётных записей.$\r$\n$\r$\nПрограмма ставится только для текущего пользователя, права администратора не нужны.$\r$\n$\r$\n$_CLICK"

!define MUI_FINISHPAGE_TITLE "${APPNAME} установлен"
!define MUI_FINISHPAGE_TEXT "Значок микрофона появится в трее рядом с часами.$\r$\n$\r$\nКликните в любое поле ввода и нажмите Ctrl+Space — говорите. Ещё раз Ctrl+Space — выключить."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Запустить ${APPNAME}"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Открыть инструкцию"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Russian"

; ------------------------------------------------------------------ функции
!macro CLOSE_INSTALLED UN
Function ${UN}CloseInstalled
  ${If} ${FileExists} "$INSTDIR\python\python.exe"
    ; 1) штатно закрываем копию программы, запущенную из этой папки
    ${If} ${FileExists} "$INSTDIR\app\main.pyw"
      DetailPrint "Закрываю запущенную программу…"
      nsExec::Exec '"$INSTDIR\python\python.exe" "$INSTDIR\app\main.pyw" --quit --only-from "$INSTDIR"'
      Pop $0
      ${If} $0 == "0"
        Sleep 1500
      ${EndIf}
    ${EndIf}
    ; 2) завершаем оставшиеся процессы встроенного Python этой папки (иначе файлы заняты)
    System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("VD_PYDIR", "$INSTDIR\python").r0'
    nsExec::Exec `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$$d = $$env:VD_PYDIR + '\'; Get-CimInstance Win32_Process | Where-Object { $$_.ExecutablePath -and $$_.ExecutablePath.StartsWith($$d, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $$_.ProcessId -Force -ErrorAction SilentlyContinue }"`
    Pop $0
    Sleep 500
  ${EndIf}
FunctionEnd
!macroend

!macro REMOVE_PROGRAM_FILES
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\models\${MODEL}"
  RMDir "$INSTDIR\models"
  RMDir /r "$INSTDIR\tests"
  RMDir /r "$INSTDIR\logs"
  Delete "$INSTDIR\config.json"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\diagnose.bat"
  Delete "$INSTDIR\${APPNAME}.exe"
!macroend
!insertmacro CLOSE_INSTALLED ""
!insertmacro CLOSE_INSTALLED "un."

Function LaunchApp
  ; копия из другой папки помешала бы запуску («уже запущен») — закрываем её
  nsExec::Exec '"$INSTDIR\python\python.exe" "$INSTDIR\app\main.pyw" --quit'
  Pop $0
  SetOutPath "$INSTDIR"
  Exec '"$INSTDIR\python\pythonw.exe" "$INSTDIR\app\main.pyw"'
FunctionEnd

; ------------------------------------------------------------------- секции
Section "!${APPNAME}" SecMain
  SectionIn RO
  Call CloseInstalled

  ; файлы прошлой версии убираем, настройки (config.json) и журналы остаются
  ${If} ${FileExists} "$INSTDIR\app\main.pyw"
    RMDir /r "$INSTDIR\python"
    RMDir /r "$INSTDIR\app"
  ${EndIf}

  SetOutPath "$INSTDIR"
  File /r "${STAGE}/*"
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "${SETTINGS_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${APPNAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\app\assets\icon.ico"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" $0
SectionEnd

Section "Ярлык в меню «Пуск»" SecStartMenu
  SetOutPath "$INSTDIR"
  CreateShortcut "$SMPROGRAMS\${LNK}" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\main.pyw"' \
    "$INSTDIR\app\assets\icon.ico" 0 SW_SHOWNORMAL "" "${LNK_DESC}"
SectionEnd

Section "Ярлык на рабочем столе" SecDesktop
  SetOutPath "$INSTDIR"
  CreateShortcut "$DESKTOP\${LNK}" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\main.pyw"' \
    "$INSTDIR\app\assets\icon.ico" 0 SW_SHOWNORMAL "" "${LNK_DESC}"
SectionEnd

Section "Запускать при входе в Windows" SecAutostart
  WriteRegStr HKCU "${RUN_KEY}" "${APPID}" '"$INSTDIR\python\pythonw.exe" "$INSTDIR\app\main.pyw"'
SectionEnd

Section "-Finish"
  ; что создано этой установкой — удаляется при удалении программы только это
  ReadINIStr $R1 "$INSTDIR\install.ini" "created" "startmenu"
  ReadINIStr $R2 "$INSTDIR\install.ini" "created" "desktop"

  ${If} ${SectionIsSelected} ${SecStartMenu}
    WriteINIStr "$INSTDIR\install.ini" "created" "startmenu" "1"
  ${Else}
    ${If} $R1 == "1"
      Delete "$SMPROGRAMS\${LNK}"
    ${EndIf}
    WriteINIStr "$INSTDIR\install.ini" "created" "startmenu" "0"
  ${EndIf}

  ${If} ${SectionIsSelected} ${SecDesktop}
    WriteINIStr "$INSTDIR\install.ini" "created" "desktop" "1"
  ${Else}
    ${If} $R2 == "1"
      Delete "$DESKTOP\${LNK}"
    ${EndIf}
    WriteINIStr "$INSTDIR\install.ini" "created" "desktop" "0"
  ${EndIf}

  ${IfNot} ${SectionIsSelected} ${SecAutostart}
    ReadRegStr $0 HKCU "${RUN_KEY}" "${APPID}"
    ${StrStr} $1 $0 "$INSTDIR\"
    ${If} $1 != ""
      DeleteRegValue HKCU "${RUN_KEY}" "${APPID}"
    ${EndIf}
  ${EndIf}
  WriteINIStr "$INSTDIR\install.ini" "install" "version" "${VERSION}"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "Программа, встроенный Python и русская модель распознавания (~${SIZE_MB} МБ на диске)."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} "Ярлык «${APPNAME}» в меню «Пуск»."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Ярлык «${APPNAME}» на рабочем столе."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAutostart} "Запускать программу при входе в Windows (можно выключить в меню значка в трее)."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function .onInit
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} $R0 "/NODESKTOP" $R1
  ${IfNot} ${Errors}
    !insertmacro UnselectSection ${SecDesktop}
  ${EndIf}
  ClearErrors
  ${GetOptions} $R0 "/NOSTARTMENU" $R1
  ${IfNot} ${Errors}
    !insertmacro UnselectSection ${SecStartMenu}
  ${EndIf}
  ClearErrors
  ${GetOptions} $R0 "/NOAUTOSTART" $R1
  ${IfNot} ${Errors}
    !insertmacro UnselectSection ${SecAutostart}
  ${EndIf}
FunctionEnd

; ----------------------------------------------------------------- удаление
Section "Uninstall"
  Call un.CloseInstalled

  ; ярлыки — только созданные этим установщиком
  ReadINIStr $0 "$INSTDIR\install.ini" "created" "desktop"
  ${If} $0 == "1"
    Delete "$DESKTOP\${LNK}"
  ${EndIf}
  ReadINIStr $0 "$INSTDIR\install.ini" "created" "startmenu"
  ${If} $0 == "1"
    Delete "$SMPROGRAMS\${LNK}"
  ${EndIf}

  ; автозапуск — только если он указывает на эту папку
  ReadRegStr $0 HKCU "${RUN_KEY}" "${APPID}"
  ${UnStrStr} $1 $0 "$INSTDIR\"
  ${If} $1 != ""
    DeleteRegValue HKCU "${RUN_KEY}" "${APPID}"
  ${EndIf}

  ; только файлы программы — чужое в папке не трогаем
  !insertmacro REMOVE_PROGRAM_FILES
  ${If} ${FileExists} "$INSTDIR\python\*.*"
  ${OrIf} ${FileExists} "$INSTDIR\app\*.*"
    ; что-то было занято — ещё раз через пару секунд
    Sleep 2500
    Call un.CloseInstalled
    !insertmacro REMOVE_PROGRAM_FILES
  ${EndIf}
  Delete "$INSTDIR\install.ini"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  ReadRegStr $0 HKCU "${UNINST_KEY}" "InstallLocation"
  ${If} $0 == "$INSTDIR"
    DeleteRegKey HKCU "${UNINST_KEY}"
  ${EndIf}
  ReadRegStr $0 HKCU "${SETTINGS_KEY}" "InstallDir"
  ${If} $0 == "$INSTDIR"
    DeleteRegKey HKCU "${SETTINGS_KEY}"
  ${EndIf}
SectionEnd
