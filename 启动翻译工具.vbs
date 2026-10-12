Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
exe = root & "\dist\LocalTranslate\LocalTranslate.exe"
If fs.FileExists(exe) Then
    shell.Run Chr(34) & exe & Chr(34), 1, False
Else
    python = root & "\.venv\Scripts\pythonw.exe"
    If fs.FileExists(python) Then
        shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & root & "\main.py" & Chr(34), 0, False
    Else
        If MsgBox("This is the source code, not a ready-to-run package." & vbCrLf & "Install Python 3.11 x64 first. Run install.cmd now?" & vbCrLf & "For another PC, you can also use the complete portable ZIP.", 36, "LocalTranslate") = 6 Then
            shell.Run Chr(34) & root & "\install.cmd" & Chr(34), 1, False
        End If
    End If
End If
