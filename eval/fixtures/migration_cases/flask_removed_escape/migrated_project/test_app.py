from app import render_name


def test_render_name_escapes_html():
    assert str(render_name("<b>Ada</b>")) == "&lt;b&gt;Ada&lt;/b&gt;"
