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
    uv run python -m crc_data_explorer.build

# Same, then check shipped values against crc-sdk's for_assets at sampled cells
verify:
    uv run python -m crc_data_explorer.build --verify

# NOAA Storm Events: snapshot (about 400 MB, cached), Texas event table, explorer layer
storm-events:
    uv run python -m crc_lab.storm_events.build

# Same, plus the two-source comparison report (needs the Source Cooperative copy in the cache)
storm-events-compare:
    uv run python -m crc_lab.storm_events.build --compare
# Sources track: IBTrACS tracks, CO-OPS water-level stations, GHCNh station curves (network, ~10 min)
sources:
    uv run python -m crc_data_explorer.sources --verify

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
    uv run python -m crc_lab.risk_layer

# The decisions document with its charts (after all builds)
decisions:
    uv run python -m crc_lab.decisions

# Source validation project: inventory, findings and page data from the installed crc-sdk (no network)
validation:
    uv run python -m data_source_check.build

# Source validation: assess one source against its publisher (network; then rebuilds the page data)
validation-assess source:
    uv run python -m data_source_check.build {{source}} --live

# Source validation: has a publisher file or the framework changed since each assessment? (network)
validation-monitor:
    uv run python -m data_source_check.monitor

# Source validation: also re-run what is stale into a staging folder (does not publish)
validation-monitor-rerun:
    uv run python -m data_source_check.monitor --rerun

# Source validation: publish a staged re-run after reading docs/validation/monitoring.md
validation-accept source:
    uv run python -m data_source_check.monitor --accept {{source}}

# Source validation: what the inventory knows about an unassessed source, for whoever drafts its assessment
validation-brief source:
    uv run python -m data_source_check.draft brief {{source}}

# Source validation: run a drafted assessment into the draft folder (never the page); add --live by hand to download
validation-draft source:
    uv run python -m data_source_check.build {{source}} --draft

# Source validation: is a draft complete? (deterministic gate)
validation-draft-check source:
    uv run python -m data_source_check.draft check {{source}}

# Source validation: a person publishes a complete draft's records
validation-draft-accept source:
    uv run python -m data_source_check.draft accept {{source}}

# Check that the static site is complete, project by project
site: site-hail site-explorer site-validation

# Texas hail risk: page files and the layers of origin crc-lab
site-hail:
    uv run python -m crc_lab.check_site

# Texas CRC data explorer (under the validation project): page files and the layers of origin crc-sdk
site-explorer:
    uv run python -m crc_data_explorer.check_site

# Source validation: the assessments page and its records
site-validation:
    uv run python -m data_source_check.check_site

# Everything: all data, then site
all: data storm-events curves assets sources site

# Serve the site locally (http://127.0.0.1:8000)
serve:
    python3 -m http.server 8000 --bind 127.0.0.1 --directory site

# Serve the site from one container (http://127.0.0.1:8080)
up:
    docker compose up --build
