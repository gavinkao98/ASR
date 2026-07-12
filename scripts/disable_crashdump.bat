@echo off
rem 移除 enable_crashdump.bat 寫入的 LocalDumps 設定。
fltmc >nul 2>&1
if %errorlevel%==0 goto :admin
if "%~1"=="elevated" (
    echo 自動提權失敗，請關閉此視窗後，改用滑鼠右鍵點此檔案並選「以系統管理員身分執行」。
    pause
    exit /b 1
)
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
exit /b

:admin
reg delete "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\pythonw.exe" /f
echo 崩潰記錄設定已移除。
pause
