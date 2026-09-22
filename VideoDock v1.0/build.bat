@echo off
pyinstaller --noconfirm --onefile --windowed --name VideoDock --icon VDicon01.ICO --add-data "lang;lang" main.py
copy /y dist\VideoDock.exe .
pyinstaller --noconfirm --onefile --windowed --name VDSetup --icon VDicon01.ICO --add-data "lang;lang" --add-data "使用须知.txt;." --add-binary "yt-dlp.exe;." --add-binary "ffmpeg.exe;." --add-binary "VideoDock.exe;." --add-binary "VDicon01.ICO;." installer.py
echo Done: dist\VDSetup.exe
pause