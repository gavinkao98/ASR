@echo off
rem 開啟 pythonw.exe 崩潰完整記錄（WER LocalDumps）：之後語音輸入若再無故關閉，
rem 會在 data\crashdumps\ 留下 dump 檔，可直接分析崩潰當下的呼叫堆疊。
rem 查完想移除設定，雙擊 disable_crashdump.bat 即可。
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
reg add "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\pythonw.exe" /v DumpFolder /t REG_EXPAND_SZ /d "C:\Users\Kao\Desktop\ASR\data\crashdumps" /f
reg add "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\pythonw.exe" /v DumpType /t REG_DWORD /d 1 /f
reg add "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\pythonw.exe" /v DumpCount /t REG_DWORD /d 5 /f
if not exist "C:\Users\Kao\Desktop\ASR\data\crashdumps" mkdir "C:\Users\Kao\Desktop\ASR\data\crashdumps"
echo.
echo 崩潰記錄已開啟：下次 pythonw 崩潰會存到 data\crashdumps\
pause
