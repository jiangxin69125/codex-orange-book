@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "SH=%HERE%\launch-cursor-linux.sh"
set "LOG=%HERE%\cursor-linux-login.log"

echo ============================================
echo  Cursor Linux launcher + Join in login fix
echo  folder: %HERE%
echo ============================================

where wsl >nul 2>&1
if errorlevel 1 (
  echo ERROR: 找不到 wsl.exe。先在 Windows 打开 "适用于 Linux 的 Windows 子系统"。
  echo 日志: %LOG%
  pause
  exit /b 1
)

if not exist "%SH%" (
  echo ERROR: 缺少 launch-cursor-linux.sh
  echo 请把 launch-cursor-linux.sh 和本 bat 一起放到 E:\CursorDownload
  echo 日志: %LOG%
  pause
  exit /b 1
)

rem Convert this folder to a WSL path. Fallback to /mnt/e/CursorDownload.
set "WSLDIR="
for /f "usebackq delims=" %%I in (`wsl.exe wslpath -a "%HERE%" 2^>nul`) do set "WSLDIR=%%I"
if not defined WSLDIR set "WSLDIR=/mnt/e/CursorDownload"

rem Drop CR from the bash script in case it was saved as CRLF on Windows.
wsl.exe -e sed -i "s/\r$//" "%WSLDIR%/launch-cursor-linux.sh" >nul 2>&1

echo [1/2] 诊断并修复默认浏览器桥 + Linux 登录轮询...
wsl.exe -e bash "%WSLDIR%/launch-cursor-linux.sh" %*
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo 启动失败，exit=%ERR%。请看: %LOG%
  echo 常见 exit: 3=没找到 Linux Cursor，4=没有 WSLg/DISPLAY
  pause
  exit /b %ERR%
)

echo.
echo [2/2] Linux Cursor 应已弹出（窗口带企鹅标）。
echo 请只点 Cursor 窗口里的 Sign in / Log in / Join in。
echo 浏览器登录成功后停在 All set 是正常的，不要关企鹅窗口，等它自己进入。
echo 日志: %LOG%
echo.
endlocal
exit /b 0
