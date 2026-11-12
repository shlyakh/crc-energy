"""NEX-GDDP-CMIP6 as crc-sdk delivers it. The only place that calls ``nex_gddp_cmip6``.

Each request runs in its own process, so that the same code can be pointed at another copy of
crc-sdk (a clone with a fix, through ``PYTHONPATH``) without touching the installed one, and
so that several requests can run side by side. crc-sdk keeps no cache for this source; the
rows it returned are stored by the caller.

    python -m data_source_check.adapters.crc.nex '<request as JSON>' <output file>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

VALUE_COLUMNS = ("year", "latitude", "longitude", "value")


def _run(request: dict[str, Any]) -> dict[str, Any]:
    import crc_sdk
    from crc_sdk.workflows import HazardDataset

    out: dict[str, Any] = {
        "request": request,
        "crc_sdk_path": str(Path(crc_sdk.__file__).parent),
        "crc_sdk_version": getattr(crc_sdk, "__version__", ""),
        "rows": [],
        "labels": {},
        "columns": [],
        "error": "",
        "error_type": "",
        "warnings": [],
    }
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            plan = (
                HazardDataset.nex_gddp_cmip6(
                    request["recipe"],
                    model=request["model"],
                    scenario=request["scenario"],
                    member=request["member"],
                    grid_label=request["grid"],
                    version=request["version"],
                )
                .for_area(tuple(request["bounds"]))
                .years(request["year"])
            )
            for batch in plan.annual_extremes():
                out["columns"] = list(batch.schema.names)
                columns = {name: batch.column(name).to_pylist() for name in batch.schema.names}
                out["rows"] += [
                    list(row) for row in zip(*(columns[n] for n in VALUE_COLUMNS), strict=True)
                ]
                for name in batch.schema.names:
                    if name not in VALUE_COLUMNS:
                        seen = out["labels"].setdefault(name, [])
                        for value in set(columns[name]):
                            if value not in seen:
                                seen.append(value)
        out["warnings"] = sorted({f"{w.category.__name__}: {w.message}" for w in caught})
    except Exception as error:  # the error is the result: it is recorded, not hidden
        out["error"], out["error_type"] = str(error), type(error).__name__
    return out


def annual(request: dict[str, Any], output: Path, *, crc_sdk_source: Path | None = None) -> None:
    """Run one request in a new process and write crc-sdk's answer to ``output``."""
    env = dict(os.environ)
    if crc_sdk_source is not None:
        env["PYTHONPATH"] = f"{crc_sdk_source}{os.pathsep}{env.get('PYTHONPATH', '')}"
    output.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        [sys.executable, "-m", "data_source_check.adapters.crc.nex", json.dumps(request),
         str(output)],
        env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if done.returncode != 0:
        raise RuntimeError(f"crc-sdk request failed to run: {done.stderr[-2000:]}")


if __name__ == "__main__":
    result = _run(json.loads(sys.argv[1]))
    temporary = Path(sys.argv[2] + ".tmp")
    temporary.write_text(json.dumps(result), encoding="utf-8")
    os.replace(temporary, sys.argv[2])
