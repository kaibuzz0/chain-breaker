; Chain-Breaker Scripture Vault NSIS Installer
; Build this with NSIS (Nullsoft Scriptable Install System)
; Download NSIS from: https://nsis.sourceforge.io/

!define PRODUCT_NAME "Chain-Breaker Scripture Vault"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "Chain-Breaker Project"
!define PRODUCT_WEB_SITE "https://github.com/kaibuzz0/chain-breaker"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\vault_cli.py"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

SetCompressor lzma

; MUI Settings
!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; Welcome page
!insertmacro MUI_PAGE_WELCOME

; License page (optional)
; !insertmacro MUI_PAGE_LICENSE "LICENSE.txt"

; Directory page
!insertmacro MUI_PAGE_DIRECTORY

; Instfiles page
!insertmacro MUI_PAGE_INSTFILES

; Finish page
!define MUI_FINISHPAGE_RUN "python.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "vault_cli.py --list"
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES

; Language files
!insertmacro MUI_LANGUAGE "English"

; MUI end ----

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "ChainBreaker-Setup.exe"
InstallDir "$PROGRAMFILES64\Chain-Breaker"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show

Section "MainSection" SEC01
    SetOutPath "$INSTDIR"
    SetOverwrite ifnewer
    
    ; Add files here (after building with pyinstaller or including source)
    ; File /r "dist\*.*"
    
    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\Chain-Breaker"
    CreateShortcut "$SMPROGRAMS\Chain-Breaker\View Vault.lnk" "$INSTDIR\vault_cli.py" "--list"
    CreateShortcut "$SMPROGRAMS\Chain-Breaker\Uninstall.lnk" "$INSTDIR\uninst.exe"
    CreateShortcut "$DESKTOP\Chain-Breaker Vault.lnk" "$INSTDIR\vault_cli.py" "--list"
    
    ; Write uninstaller
    WriteUninstaller "$INSTDIR\uninst.exe"
    
    ; Write registry
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\vault_cli.py"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\vault_cli.py"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\uninst.exe"
    Delete "$DESKTOP\Chain-Breaker Vault.lnk"
    Delete "$SMPROGRAMS\Chain-Breaker\*.lnk"
    RMDir "$SMPROGRAMS\Chain-Breaker"
    RMDir /r "$INSTDIR"
    DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
SectionEnd
