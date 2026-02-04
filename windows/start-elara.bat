@echo off
REM Start Elara Web Service in WSL
REM Put this in Windows Startup folder

echo Starting Elara...
wsl -d Ubuntu-24.04 -e bash -c "systemctl --user start elara-web"
echo Elara is running.
