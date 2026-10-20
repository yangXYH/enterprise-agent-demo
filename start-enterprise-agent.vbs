' Enterprise Agent launcher - runs the start script with a completely hidden window
Set ws = CreateObject("WScript.Shell")
ws.Environment("Process")("APP_ENV") = "production"
ws.Run "cmd /c ""E:\project\enterprise-agent\start-enterprise-agent.bat""", 0, False
