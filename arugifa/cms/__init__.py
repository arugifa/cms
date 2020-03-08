import jinja2


templates = jinja2.Environment(
    loader=jinja2.PackageLoader('arugifa.cms', 'templates'),
    # Remove newlines end indentation when using templating blocks.
    trim_blocks=True, lstrip_blocks=True,
)
