# crc-lab task runner. `just` lists targets. G5: `just all` must rebuild every data file and the site.

set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

# Install the pinned environment
setup:
    uv sync --all-extras --group dev

# Offline tests, including the version-pin guard
test:
    uv run pytest -q

# Lint and format check
lint:
    uv run ruff check src tests
    uv run ruff format --check src tests

# Fix lint and formatting in place
fix:
    uv run ruff check --fix src tests
    uv run ruff format src tests

# Rebuild every data file (targets arrive with Phase 1)
data:
    @echo "no data targets yet (Phase 1)"

# Rebuild the static site (targets arrive with Phase 1)
site:
    @echo "no site targets yet (Phase 1)"

# Everything: data, then site
all: data site
