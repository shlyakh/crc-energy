# crc-lab documentation

Current work (agreed 2026-11-10; explorer first, storm sources and assets deferred):

- [Requirements](requirements.md): CRC data explorer and severe-storm sources, Texas
- [Requirements: hail impact functions v0](requirements-hail-impact-v0.md): first-approximation damage curves
  for solar plants, buildings and cars (draft; not yet scheduled as a phase)
- [Implementation plan](implementation-plan.md)
- [How hail data is processed](hail-data-processing.md): from raw reports and radar to the numbers at a plant
- [Decisions and their effect](decisions.md): each choice, its alternatives and a chart of the difference
- [Data source catalog](data-sources.md): every source in use, probed or proposed, with what was checked
- [Plan: better hail exposure](plan-hail-exposure.md): footprint, reporting bias, radar (draft for review)
- [Reports](reports/): one per phase — [0 setup](reports/0-setup.md) · [1 explorer](reports/1-explorer.md) · [2 storm events](reports/2-storm-events.md) · [2 comparison](reports/2-storm-events-comparison.md) · [3 curves](reports/3-curves.md) · [3 sensitivity](reports/3-curves-sensitivity.md) · [4 assets](reports/4-assets.md) · [4 hail exposure](reports/4-hail-exposure-sensitivity.md) · [4 real estate](reports/4-real-estate-fort-bend.md) · [4 radar](reports/4-radar-hail.md) · [5 reporting bias](reports/5-reporting-bias.md)
- [Primer: how an event source can be used in CRC](primers/event-sources-in-crc.md)

Background:

- [Explainers (D0)](explainers/README.md): [Anatomy of one CRC question](explainers/anatomy.html) ·
  [Climate risk curves, animated](explainers/primer.html)
- [Candidate nuggets](nuggets.md)
- [Research: radar hail data sources for Texas](research/radar-hail-sources.md): every radar hail record found, and what covers 2012–2020
- [Research: solar plant data sources, U.S. and Texas](research/solar-plant-data-sources.md): EIA-860/860M,
  USPVDB, ERCOT reports and others compared (background; not a requirement)
- [Archive](archive/README.md): earlier requirements and implementation plan
