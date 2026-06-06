import flask

@flask.escape
def render():
    return "<p>"
