@echo off
powershell -Command "Register-ScheduledTask -TaskName 'LojaItaDigital_Ideias3D_06h' -Action (New-ScheduledTaskAction -Execute '%~dp0EXECUTAR-ROBO-06H.bat' -WorkingDirectory '%~dp0') -Trigger (New-ScheduledTaskTrigger -Daily -At 06:00) -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries) -Force"
pause
