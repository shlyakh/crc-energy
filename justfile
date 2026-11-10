# crc-lab task runner. `just` lists targets. G5: `just all` rebuilds every data file and the site.

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

# Rebuild every explorer data file from CRC Open and the Census boundary (needs the network)
data:
    uv run python -m crc_lab.explorer.build

# Same, then check shipped values against crc-sdk's for_assets at sampled cells
verify:
    uv run python -m crc_lab.explorer.build --verify

# Sources track: IBTrACS tracks, CO-OPS water-level stations, GHCNh station curves (network, ~10 min)
sources:
    uv run python -m crc_lab.explorer.sources --verify

# Check that the static site is complete: every registry layer has its files
site:
    uv run python -m crc_lab.explorer.check_site

# Everything: data, sources, then site
all: data sources site

# Serve the site locally (http://127.0.0.1:8000)
serve:
    python3 -m http.server 8000 --bind 127.0.0.1 --directory site

# Serve the site from one container (http://127.0.0.1:8080)
up:
    docker compose up --build
