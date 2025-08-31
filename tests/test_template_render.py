from signal_bot import render_template


def test_render_template_basic():
    template = "Hello {{ name }}"
    result = render_template(template, {"name": "Alice"})
    assert result == "Hello Alice"


def test_render_template_escapes_html():
    template = "Hello {{ name }}"
    result = render_template(template, {"name": "<b>Alice</b>"})
    assert result == "Hello &lt;b&gt;Alice&lt;/b&gt;"


def test_render_custom_template_sanitizes_html():
    template = "<script>{{ name }}</script>"
    result = render_template(template, {"name": "Alice"})
    assert result == "&lt;script&gt;Alice&lt;/script&gt;"


def test_render_template_file():
    result = render_template("vip.j2", {"message": "Hi"})
    assert result.strip() == "[VIP] Hi"
