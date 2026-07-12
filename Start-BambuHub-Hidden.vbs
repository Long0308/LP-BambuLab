' Chay Start-BambuHub.bat AN cua so (Task Scheduler goi file nay luc logon).
' 0 = hidden window, False = khong cho doi (server chay nen).
Dim shell, fso, dir
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = dir
shell.Run """" & dir & "\Start-BambuHub.bat""", 0, False