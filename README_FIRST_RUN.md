# SKYFALL Desktop v0.1 — First Run

This archive adds the first PySide6 desktop shell to the existing SKYFALL project.

## Included files

- `main.py` — desktop application entry point
- `app/desktop/main_window.py` — overview, navigation, chat shell and floating assistant
- `app/desktop/theme.py` — dark desktop theme
- `app/__init__.py` and `app/desktop/__init__.py` — package markers

## Install / run

Open PowerShell in the existing project directory:

```powershell
cd C:\Users\pkara\Documents\Skyfall
.\.venv\Scripts\Activate.ps1
python -m pip check
python main.py
```

If dependencies are not yet installed, use:

```powershell
python -m pip install --use-feature=truststore -r requirements.txt
```

## Important status note

This is the first desktop UI shell. Its navigation, chat layout, quick-action prompts and floating window work locally. The Copilot SDK, MCP tools, Azure and Power Platform connectors are not yet wired into this application. The chat deliberately reports that no cloud or script operation is executed until those integrations are implemented.

The archive does not replace `requirements.txt`, `.venv`, or your existing configuration files.
