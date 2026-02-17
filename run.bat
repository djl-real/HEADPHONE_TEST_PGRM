@echo off
REM Activate the virtual environment
call venv\Scripts\activate.bat

REM Run the Python application
REM Optional: set the path to Python 3 explicitly if needed
REM set PYTHON_PATH=C:\Python310\python.exe

REM Run the main window script
python .\main_window.py

REM Pause to see any output/errors after the program exits
pause