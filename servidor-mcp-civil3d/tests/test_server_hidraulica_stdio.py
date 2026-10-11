"""Hydraulics contract in the shared server, over real stdio; no CAD tools called."""
import test_hidraulica_stdio


class SharedServerTests(test_hidraulica_stdio.StdioTests):
    server_entry = 'server.py'
