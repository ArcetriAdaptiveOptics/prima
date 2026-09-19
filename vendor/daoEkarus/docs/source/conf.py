# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'daoEkarus'
copyright = '2026, David Barr'
author = 'David Barr'
release = '0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = []

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ['_static']
html_logo = '_static/Ekarus_Logo_light.png'
html_theme_options = {
    # Customizing colors to match image_3ddd8d.png
    "light_css_variables": {
        "color-brand-primary": "#00a896",  # Teal accent for links/sidebar
        "color-brand-content": "#0b3c5d",  # Deep blue for main titles
    },
    "dark_css_variables": {
        "color-brand-primary": "#cbd937",  # Chartreuse accent for dark mode links
        "color-brand-content": "#4cc9f0",  # Bright cyan for content links
    },
}