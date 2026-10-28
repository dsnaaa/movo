' Movo silent launcher (no console window)
' Double-click to start; put a copy in the Startup folder to run at logon.
Option Explicit

Dim fso, sh, dir, py, app, q, rc, cmd

Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
py  = dir & "\.venv\Scripts\pythonw.exe"
app = dir & "\server.py"
q   = Chr(34)

If Not fso.FileExists(py) Then
    MsgBox "Python not found: " & py, 16, "Movo"
    WScript.Quit 1
End If

If Not fso.FileExists(app) Then
    MsgBox "server.py not found: " & app, 16, "Movo"
    WScript.Quit 1
End If

Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dir

' Already running? Then do nothing (avoids port 10048).
cmd = "cmd /c netstat -ano | findstr " & q & ":5888" & q & " | findstr " & q & "LISTENING" & q & " >nul 2>&1"
rc = sh.Run(cmd, 0, True)
If rc = 0 Then WScript.Quit 0

' 0 = hidden window, False = do not wait
sh.Run q & py & q & " " & q & app & q & " --silent", 0, False
