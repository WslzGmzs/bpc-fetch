.PHONY: install-local build-win clean

install-local:
	uv pip install -e .
	@echo "Installed. Run: bpc-fetch --help"

build-win:
	uv pip install pyinstaller
	python packaging/build_win.py

clean:
	rm -rf dist/ build/__pycache__/ *.egg-info/
