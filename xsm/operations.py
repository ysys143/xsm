"""Shared operation boundary for MCP and protocol hosts.

The host binds a caller before entry; operation arguments cannot select one.
The existing policy, decision and inbox lifecycle remains in the dispatcher.
"""


def invoke(host, name, arguments):
    return host._invoke_operation(name, arguments)
