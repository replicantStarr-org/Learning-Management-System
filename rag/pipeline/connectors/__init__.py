"""One module per service. Each defines `connector = Connector(name, base_url)`
and decorates one function per entity with @connector.entity; every module in
this package is picked up automatically. See AGENTS.md for how to write one.
"""
