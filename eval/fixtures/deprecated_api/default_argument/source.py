import flask

def render(value=flask.escape("<p>")):
    return value
