' Starts the portfolio dashboard (http://localhost:8420) with no console window.
' Output goes to _orchestrator\logs\dashboard.log. Used by the Windows Startup shortcut.
Set fso = CreateObject("Scripting.FileSystemObject")
dash = fso.GetParentFolderName(WScript.ScriptFullName)
orch = fso.GetParentFolderName(dash)
cmd = "cmd /c """"" & orch & "\.venv\Scripts\python.exe"" -m uvicorn app:app --app-dir """ & dash & """ --host 127.0.0.1 --port 8420 >> """ & orch & "\logs\dashboard.log"" 2>&1"""
CreateObject("WScript.Shell").Run cmd, 0, False
