' Start Elara silently in WSL
' Put shortcut to this in: shell:startup

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "wsl -d Ubuntu-24.04 -e bash -c ""cd /home/neboo/elara-core && source venv/bin/activate && python -m interface.web""", 0, False
