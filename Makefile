PY ?= .venv/bin/python
.PHONY: venv tools test run demo models
venv:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
tools:
	./scripts/install_tools.sh
test:
	$(PY) -m pytest -q
run:
	$(PY) -m streamlit run app.py
demo:
	$(PY) scripts/run_real.py
models:
	$(PY) scripts/run_real.py --list-models
