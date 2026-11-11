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

# NOAA Storm Events: snapshot (about 400 MB, cached), Texas event table, explorer layer
storm-events:
    uv run python -m crc_lab.storm_events.build

# Same, plus the two-source comparison report (needs the Source Cooperative copy in the cache)
storm-events-compare:
    uv run python -m crc_lab.storm_events.build --compare
# Sources track: IBTrACS tracks, CO-OPS water-level stations, GHCNh station curves (network, ~10 min)
sources:
    uv run python -m crc_lab.explorer.sources --verify

# Hail-size and thunderstorm-gust curves from the Storm Events table, into CRC and the explorer
curves:
    uv run python -m crc_lab.curves.build

# Same, plus the sensitivity note (pooling ring, start year, family) at ten cities
curves-sensitivity:
    uv run python -m crc_lab.curves.build --sensitivity

# Solar plants (USPVDB), replacement value (NREL ATB), hail exposure by local report density
assets:
    uv run python -m crc_lab.assets.build

# Same, plus the exposure sensitivity note
assets-sensitivity:
    uv run python -m crc_lab.assets.build --sensitivity

# First reporting-bias correction for hail reports: population and roads (report 5)
reporting-bias:
    uv run python -m crc_lab.assets.reporting_bias

# Radar hail: MRMS daily maxima (needs the 'radar' extra), hail signatures 1995 on, plant table, source comparison
radar:
    uv run --extra radar python -m crc_lab.radar.mrms
    uv run python -m crc_lab.radar.swdi
    uv run python -m crc_lab.radar.build
    uv run python -m crc_lab.radar.compare_cells

# Phase 5: hail loss per solar plant from the v0 impact curves (after assets, reporting-bias and radar)
impacts:
    uv run python -m crc_lab.impacts.build
    uv run python -m crc_lab.explorer.risk_layer

# The decisions document with its charts (after all builds)
decisions:
    uv run python -m crc_lab.decisions

# Check that the static site is complete: every registry layer has its files
site:
    uv run python -m crc_lab.explorer.check_site

# Everything: all data, then site
all: data storm-events curves assets sources site

# Serve the site locally (http://127.0.0.1:8000)
serve:
    python3 -m http.server 8000 --bind 127.0.0.1 --directory site

# Serve the site from one container (http://127.0.0.1:8080)
up:
    docker compose up --build
