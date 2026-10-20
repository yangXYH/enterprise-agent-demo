' hidden command runner - runs a command with no visible window (style 0)
If WScript.Arguments.Count < 1 Then WScript.Quit 1
Set ws = CreateObject("WScript.Shell")
ws.Run WScript.Arguments(0), 0, False