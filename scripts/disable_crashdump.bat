@echo off
rem 移除 enable_crashdump.bat 寫入的 LocalDumps 設定。
net session >nul 2>&1 || (powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs" & exit /b)
reg delete "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\pythonw.exe" /f
echo 崩潰記錄設定已移除。
pause
