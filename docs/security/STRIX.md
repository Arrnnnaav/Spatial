# Strix checks for Spatial

Official project: https://github.com/usestrix/strix

Setup is prepared but not verified or executed: terminal process creation currently fails with Windows
Access is denied. No Strix vulnerability result has been produced.

Local prerequisites: Python 3.12+, Docker with Linux containers running, and a configured LLM. The upstream
headless workflow uses `strix -n`, a scan mode, and a maximum budget. Local targets are writable, so the
wrapper stages a source copy and excludes secrets, user data, and build output.

After terminal access is restored:

```powershell
python -m venv .security-venv
.security-venv/Scripts/python.exe -m pip install strix-agent==1.6.2
docker info
.security-venv/Scripts/strix.exe --version
# Set STRIX_LLM and LLM_API_KEY in the environment; do not put keys in this repository.
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
