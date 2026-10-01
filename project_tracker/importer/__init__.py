"""Spreadsheet import: parse an uploaded file, preview every row, then save.

``parsers`` turns a .csv, .xlsx or .ods upload into a header row plus data rows.
Everything after that works on those rows and never knows which format they came
from.
"""
