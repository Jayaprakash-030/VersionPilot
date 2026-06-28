import flask


def render_name(name: str) -> str:
    return flask.escape(name)
