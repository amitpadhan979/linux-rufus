.PHONY: help install dev test lint run-cli run-gui deb clean

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

help:
	@echo "Linux Rufus Development Commands:"
	@echo "  make install     - Install linux-rufus locally"
	@echo "  make dev         - Install in editable mode with dev dependencies"
	@echo "  make test        - Run test suite with pytest"
	@echo "  make run-cli     - Launch interactive CLI / TUI"
	@echo "  make run-gui     - Launch Rufus desktop graphical interface"
	@echo "  make deb         - Build Debian/Ubuntu .deb package"
	@echo "  make clean       - Remove cache and build artifacts"

install:
	$(PIP) install .

dev:
	$(PIP) install -e .[dev]

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py"

run-cli:
	$(PYTHON) -m linux_rufus list

run-gui:
	$(PYTHON) -m linux_rufus gui

deb:
	bash scripts/build_deb.sh

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ *.egg-info .pytest_cache/
