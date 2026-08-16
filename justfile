set shell := ["bash", "-cu"]

venv := ".venv"
python := venv + "/bin/python"

default:
    just --list

install:
    ./script/install

reinstall:
    ./script/install

setup:
    python3 -m venv {{venv}}
    {{python}} -m pip install -e ".[dev]"

test:
    {{venv}}/bin/ruff format --check src tests
    {{venv}}/bin/ruff check src tests
    {{venv}}/bin/detect-secrets scan --baseline .secrets.baseline
    PYTHONPATH=src {{python}} -m unittest discover -s tests -v

status:
    gatectl status

inspect:
    gatectl inspect
