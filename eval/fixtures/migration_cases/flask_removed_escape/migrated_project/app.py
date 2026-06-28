from markupsafe import escape


def render_name(name: str) -> str:
    return escape(name)
