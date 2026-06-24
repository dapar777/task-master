' Spuštění Task Master úplně bez konzolového okna (dvojklik)
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = scriptDir
sh.Run "pythonw.exe """ & scriptDir & "\main.py""", 0, False
