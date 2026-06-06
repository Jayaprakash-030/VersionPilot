class LocalObject:
    escape = staticmethod(str)


flask = LocalObject()
escaped = flask.escape("<p>")
