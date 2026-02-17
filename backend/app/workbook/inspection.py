"""Inspect local XLSX workbook structure (tabs + defined names)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


@dataclass(frozen=True)
class WorkbookInspection:
    """Parsed workbook structure used by contract validators."""

    sheet_names: tuple[str, ...]
    named_ranges: tuple[str, ...]


def inspect_local_workbook(workbook_path: str | Path) -> WorkbookInspection:
    """Read workbook.xml from an XLSX file and return structural metadata."""
    path = Path(workbook_path)
    if not path.exists():
        raise FileNotFoundError(f"Workbook not found: {path}")

    with ZipFile(path) as zip_file:
        workbook_xml = zip_file.read("xl/workbook.xml")

    root = ET.fromstring(workbook_xml)
    ns = {"m": MAIN_NS}

    sheets = root.find("m:sheets", ns)
    if sheets is None:
        sheet_names: tuple[str, ...] = ()
    else:
        sheet_names = tuple(
            node.attrib.get("name", "").strip()
            for node in sheets.findall("m:sheet", ns)
            if node.attrib.get("name")
        )

    defined_names_parent = root.find("m:definedNames", ns)
    if defined_names_parent is None:
        named_ranges: tuple[str, ...] = ()
    else:
        named_ranges = tuple(
            node.attrib.get("name", "").strip()
            for node in defined_names_parent.findall("m:definedName", ns)
            if node.attrib.get("name")
        )

    return WorkbookInspection(sheet_names=sheet_names, named_ranges=named_ranges)
