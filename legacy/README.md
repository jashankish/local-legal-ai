# Legacy scripts (superseded)

Kept for reference only — nothing in the application or the test suite uses
these files, and several no longer work against the current API (for example,
they sign in with the default `admin123` password, which must now be changed at
first sign-in).

| File(s) | Superseded by |
|---|---|
| `test_phase*.py`, `test_full_system.py`, `test_simple_setup.py`, `test_*navigation*.py` | `pytest` suite in [`tests/`](../tests) and [`scripts/ui_smoke.py`](../scripts/ui_smoke.py) |
| `debug_upload*.py`, `debug_content_type.py`, `check_documents.py` | API tests in `tests/` and the 🔌 Integrations / Document Library pages |
| `test_contract.txt`, `test_doc.txt` | Fictional sample agreements in [`samples/`](../samples) |
| `setup.py` | [`start_system.sh`](../start_system.sh) (creates `.venv` and `.env`) |
| `requirements_phase4.txt`, `frontend/requirements.txt` | [`requirements.txt`](../requirements.txt) |
| `frontend/run_frontend.py` | `start_system.sh` or `docker compose up` |
