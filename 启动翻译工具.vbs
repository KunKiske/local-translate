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
        MsgBox "Please run setup.ps1 first.", 48, "LocalTranslate"
    End If
End If
