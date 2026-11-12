"""data_source_check: exploration, verification and validation of climate-risk data sources.

Framework-neutral core (``core``), independent readers of the publishers' files (``reference``,
which must not import the framework under test) and one adapter per framework (``adapters``).
The first framework is crc-sdk. Method: ``docs/validation/method.md``.
"""

__version__ = "0.0.1"
