# Upstream changes watched (requirement N8)

| Date | Package | Version | What changed | Effect on crc-lab |
| --- | --- | --- | --- | --- |
| 2026-11-12 | crc-sdk | pull request [#43](https://github.com/RiskThinking/crc-sdk/pull/43), open | Ours: IBTrACS subset `active` requests NOAA's file name `ACTIVE` (finding CRC-010-IBT) | None until merged; then raise the pin and re-run the IBTrACS assessment |
| 2026-11-12 | crc-sdk | pull request [#42](https://github.com/RiskThinking/crc-sdk/pull/42), open | Ours: NEX-GDDP-CMIP6 temperature recipes accept the one-character unit `K` (finding CRC-001-NEX); mentions NASA's v2.0 files (CRC-012-NEX) | None until merged; then raise the pin, update the NEX row in `docs/sources-track/requirements.md` and re-run the NEX assessment |
| 2026-11-04 | crc-framework | 0.6.0 | Type-7 interpolated empirical law ("expectations can shift slightly"); out_of_domain error policy; GIL released; skew-normal CDF aligned with SciPy | Baseline pin. Re-run conformance tests on any later release |
| 2026-11-04 | crc-sdk | 0.11.1 | Python >=3.11 | Baseline pin |
| 2026-10-26 | crc-framework | 0.5.0 | Impact function schema v1.0.0 | Impact definitions target this schema |
