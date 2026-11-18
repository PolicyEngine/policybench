"""The PolicyBench household calculator, apart from the harness that tests models.

``core`` is the calculator the tool pilot gives a model: a verbatim copy of
the one in ``scripts/tool_pilot_argon.py``, kept exact by
``scripts/sync_calculator_core.py`` and ``tests/test_calculator_core.py``.
``mcp_server`` offers the same tool over the Model Context Protocol, and
``mcp_client`` calls such a server the way the pilot calls its own workers.
"""
