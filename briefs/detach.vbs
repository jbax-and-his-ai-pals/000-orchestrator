' Runs a bash script hidden and fully detached, so it survives the chat (and the Claude session) that started it.
' Usage (from PowerShell):  Start-Process wscript -ArgumentList '"C:\jbax-and-his-ai-pals\_orchestrator\briefs\detach.vbs" logs/my_script.sh'
' The script path is relative to _orchestrator; its output goes to logs/<script name>.out.
Set fso = CreateObject("Scripting.FileSystemObject")
orch = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
script = WScript.Arguments(0)
name = fso.GetBaseName(script)
cmd = """C:\Program Files\Git\bin\bash.exe"" -lc ""cd '" & Replace(orch, "\", "/") & "' && ./" & script & " >> logs/" & name & ".out 2>&1"""
CreateObject("WScript.Shell").Run cmd, 0, False
