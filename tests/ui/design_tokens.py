"""The look the app's stylesheet (the <style> block in app/templates/base.html) defines, as
computed values, in one place. Browsers report computed colours as rgb(), lengths in px (rem
resolved against the 16 px root), so hex and rem from the CSS are converted here once.

When the design changes on purpose, change the CSS and this file together; a test failing on one
of them alone is the point.
"""

# body { font: 15px/1.4 Inter, system-ui, sans-serif; max-width: 56rem }
BODY = {
    "font-family": "Inter, system-ui, sans-serif",
    "font-size": "15px",
    "line-height": "21px",  # 15px * 1.4
    "max-width": "896px",  # 56rem
    "color": "rgb(0, 0, 0)",  # not set by the CSS: the browser default, which is a contract too
}
BODY_TEXT = {key: BODY[key] for key in ("font-family", "font-size", "line-height")}

# h1 has no rule of its own: the user-agent default, twice the body size, bold.
HEADING_1 = {"font-size": "30px", "font-weight": "700", "font-family": BODY["font-family"]}

# header { border-bottom: 1px solid #ccc }
HEADER_RULE = {
    "border-bottom-width": "1px",
    "border-bottom-style": "solid",
    "border-bottom-color": "rgb(204, 204, 204)",
}

# th, td { padding: .25rem .5rem; border-bottom: 1px solid #eee }
TABLE_CELL = {
    "padding-top": "4px",
    "padding-left": "8px",
    "border-bottom-width": "1px",
    "border-bottom-color": "rgb(238, 238, 238)",
    "text-align": "left",
}

# label { display: block }
LABEL = {"display": "block"}

# .flash { padding: .5rem; border: 1px solid } with a colour per level
FLASH = {"padding-top": "8px", "border-top-width": "1px", "border-top-style": "solid"}
FLASH_SUCCESS_BORDER = {**FLASH, "border-top-color": "rgb(34, 170, 119)"}  # #2a7
FLASH_ERROR_BORDER = {**FLASH, "border-top-color": "rgb(204, 51, 51)"}  # #c33

# @font-face "Inter" -> /static/fonts/inter-latin-400-normal.woff2. The tests image has no app/,
# so the file's SHA-256 is a constant. Regenerate after replacing the file:
#   shasum -a 256 app/static/fonts/inter-latin-400-normal.woff2
WEB_FONT_PATH = "/static/fonts/inter-latin-400-normal.woff2"
WEB_FONT_SHA256 = "dd05e326cf8eac3b55acecf29c842ed73e6e6dd06491cf47f7e8800680ab3e33"
EXPECTED_FONTS = {WEB_FONT_PATH: WEB_FONT_SHA256}
