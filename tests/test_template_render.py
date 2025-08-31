from signal_bot import render_template


def test_render_template_basic():
    template = "Hello {{ name }}"
    result = render_template(template, {"name": "Alice"})
    assert result == "Hello Alice"
