# Strix checks for Spatial

Official project: https://github.com/usestrix/strix

The isolated runner is in place, but no Spatial vulnerability assessment has been completed yet. Strix
1.6.2 is installed in `.security-venv`, and Docker is responding. The current Strix profile is not signed
in, and neither `STRIX_LLM` nor `LLM_API_KEY` is set in the current shell. The source snapshot can be
prepared without those credentials.

Local prerequisites: Python 3.12+, Docker with Linux containers running, and a configured LLM. The upstream
headless workflow uses `strix -n`, a scan mode, and a maximum budget. Local targets are writable, so the
wrapper stages a source copy and excludes secrets, user data, and build output.

Install and run the scoped local assessment:

```powershell
# One-time local setup (Windows x64)
python -m venv .security-venv
.security-venv/Scripts/python.exe -m pip install --only-binary=:all: strix-agent==1.6.2
docker info
.security-venv/Scripts/strix.exe --version
# Set STRIX_LLM and LLM_API_KEY in this PowerShell session; never commit the values.
# The configured model provider receives source text during a scan.
python scripts/strix_scan.py --prepare-only
python scripts/strix_scan.py --mode standard --max-budget 5
```

The preparation step prints the exact source manifest and snapshot directory. The wrapper scans only that
copy, with full-tree scope and project-specific instructions. Review findings before applying patches.
Reports are under the snapshot's `strix_runs/` directory. Inspect `run.json`, stated coverage and spend;
an exit code of zero alone does not establish a complete clean assessment. Exit 2 means vulnerabilities
were found; exit 1 means a failed run.

Source text is processed by the configured LLM provider. Choose a local model if source must remain local.
The wrapper does not read `server/.env` or reuse production tokens. No cloud upload or paid scan has been
started by this setup.
