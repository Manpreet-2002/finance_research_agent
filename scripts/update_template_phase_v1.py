from __future__ import annotations

import copy
import re
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)


def q(tag: str) -> str:
    return f"{{{MAIN_NS}}}{tag}"


def qrel(tag: str) -> str:
    return f"{{{PKG_REL_NS}}}{tag}"


def col_to_idx(col: str) -> int:
    val = 0
    for ch in col:
        val = val * 26 + (ord(ch) - 64)
    return val


def idx_to_col(idx: int) -> str:
    out = []
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        out.append(chr(65 + rem))
    return "".join(reversed(out))


def split_ref(ref: str) -> tuple[str, int]:
    col = "".join(ch for ch in ref if ch.isalpha())
    row = int("".join(ch for ch in ref if ch.isdigit()))
    return col, row


def get_sheet_path(files: dict[str, bytes], sheet_name: str) -> str:
    wb = ET.fromstring(files["xl/workbook.xml"])
    rels = ET.fromstring(files["xl/_rels/workbook.xml.rels"])
    rel_map = {r.attrib["Id"]: r.attrib["Target"].lstrip("/") for r in rels.findall(qrel("Relationship"))}
    sheets = wb.find(q("sheets"))
    assert sheets is not None
    for s in sheets.findall(q("sheet")):
        if s.attrib.get("name") == sheet_name:
            rid = s.attrib[f"{{{REL_NS}}}id"]
            return rel_map[rid]
    raise KeyError(f"Sheet not found: {sheet_name}")


def get_row(sheet_data: ET.Element, r: int, create: bool = False) -> ET.Element | None:
    for row in sheet_data.findall(q("row")):
        if int(row.attrib.get("r", "0")) == r:
            return row
    if not create:
        return None
    row = ET.Element(q("row"), {"r": str(r)})
    sheet_data.append(row)
    return row


def get_cell(row: ET.Element, ref: str) -> ET.Element | None:
    for c in row.findall(q("c")):
        if c.attrib.get("r") == ref:
            return c
    return None


def set_inline_string(cell: ET.Element, text: str, style: str | None = None) -> None:
    cell.attrib["t"] = "inlineStr"
    if style is not None:
        cell.attrib["s"] = str(style)
    for child in list(cell):
        cell.remove(child)
    is_el = ET.SubElement(cell, q("is"))
    t_el = ET.SubElement(is_el, q("t"))
    t_el.text = text


def set_number(cell: ET.Element, value: str, style: str | None = None) -> None:
    cell.attrib["t"] = "n"
    if style is not None:
        cell.attrib["s"] = str(style)
    for child in list(cell):
        cell.remove(child)
    v_el = ET.SubElement(cell, q("v"))
    v_el.text = value


def set_formula(cell: ET.Element, formula: str, style: str | None = None) -> None:
    cell.attrib.pop("t", None)
    if style is not None:
        cell.attrib["s"] = str(style)
    for child in list(cell):
        cell.remove(child)
    f_el = ET.SubElement(cell, q("f"))
    f_el.text = formula
    v_el = ET.SubElement(cell, q("v"))
    v_el.text = ""


def ensure_cell(row: ET.Element, col: str, r: int) -> ET.Element:
    ref = f"{col}{r}"
    cell = get_cell(row, ref)
    if cell is None:
        cell = ET.Element(q("c"), {"r": ref})
        row.append(cell)
    return cell


def sort_sheet(sheet_root: ET.Element) -> None:
    sheet_data = sheet_root.find(q("sheetData"))
    if sheet_data is None:
        return
    rows = sheet_data.findall(q("row"))
    rows.sort(key=lambda x: int(x.attrib.get("r", "0")))
    for row in rows:
        cells = row.findall(q("c"))
        cells.sort(key=lambda c: col_to_idx(split_ref(c.attrib["r"])[0]))
        for c in list(row):
            row.remove(c)
        for c in cells:
            row.append(c)
    for r in list(sheet_data):
        sheet_data.remove(r)
    for r in rows:
        sheet_data.append(r)


def update_dimension(sheet_root: ET.Element) -> None:
    max_row = 1
    max_col = 1
    sheet_data = sheet_root.find(q("sheetData"))
    if sheet_data is not None:
        for row in sheet_data.findall(q("row")):
            r_idx = int(row.attrib.get("r", "1"))
            max_row = max(max_row, r_idx)
            for c in row.findall(q("c")):
                col, rr = split_ref(c.attrib["r"])
                max_col = max(max_col, col_to_idx(col))
                max_row = max(max_row, rr)
    dim = sheet_root.find(q("dimension"))
    if dim is None:
        dim = ET.Element(q("dimension"))
        sheet_root.insert(0, dim)
    dim.attrib["ref"] = f"A1:{idx_to_col(max_col)}{max_row}"


LOCAL_REF_RE = re.compile(r"(?<![A-Za-z0-9_!'$.])(\$?)([A-Z]{1,3})(\$?)(\d+)")


def shift_local_formula_refs(formula: str, delta: int) -> str:
    def repl(m: re.Match[str]) -> str:
        c1, col, c2, row = m.groups()
        return f"{c1}{col}{c2}{int(row) + delta}"

    return LOCAL_REF_RE.sub(repl, formula)


def replace_scenario_inputs(formula: str, target_col: str) -> str:
    assumption_rows = [20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 37, 38, 39, 40, 41, 42, 43, 44]
    out = formula
    for r in assumption_rows:
        out = out.replace(f"Inputs!C{r}", f"Inputs!{target_col}{r}")
        out = out.replace(f"Inputs!$C${r}", f"Inputs!${target_col}${r}")
        out = out.replace(f"'Inputs'!C{r}", f"'Inputs'!{target_col}{r}")
        out = out.replace(f"'Inputs'!$C${r}", f"'Inputs'!${target_col}${r}")
    return out


def clone_dcf_block(sheet_root: ET.Element, src_start: int, src_end: int, dst_start: int, scenario_col: str) -> None:
    sheet_data = sheet_root.find(q("sheetData"))
    assert sheet_data is not None
    delta = dst_start - src_start

    src_rows: dict[int, ET.Element] = {}
    for row in sheet_data.findall(q("row")):
        r = int(row.attrib.get("r", "0"))
        if src_start <= r <= src_end:
            src_rows[r] = row

    for r in sorted(src_rows):
        if not (src_start <= r <= src_end):
            continue
        src_row = src_rows[r]
        new_row = copy.deepcopy(src_row)
        new_r = r + delta
        new_row.attrib["r"] = str(new_r)
        for cell in new_row.findall(q("c")):
            col, _old_r = split_ref(cell.attrib["r"])
            cell.attrib["r"] = f"{col}{new_r}"
            f = cell.find(q("f"))
            if f is not None and f.text:
                shifted = shift_local_formula_refs(f.text, delta)
                shifted = replace_scenario_inputs(shifted, scenario_col)
                f.text = shifted

        # Replace if destination row already exists
        existing = get_row(sheet_data, new_r, create=False)
        if existing is not None:
            sheet_data.remove(existing)
        sheet_data.append(new_row)


def upsert_defined_name(wb_root: ET.Element, name: str, ref_text: str) -> None:
    dns = wb_root.find(q("definedNames"))
    if dns is None:
        dns = ET.SubElement(wb_root, q("definedNames"))
    for dn in dns.findall(q("definedName")):
        if dn.attrib.get("name") == name:
            dn.text = ref_text
            return
    dn = ET.SubElement(dns, q("definedName"), {"name": name})
    dn.text = ref_text


def main() -> None:
    template = Path("Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx")
    backup = template.with_suffix(".xlsx.bak")
    backup.write_bytes(template.read_bytes())

    with zipfile.ZipFile(template, "r") as zin:
        files = {name: zin.read(name) for name in zin.namelist()}

    # Parse workbook root once for defined names updates.
    wb_root = ET.fromstring(files["xl/workbook.xml"])

    # Load sheets to patch.
    inputs_path = get_sheet_path(files, "Inputs")
    dcf_path = get_sheet_path(files, "DCF")
    output_path = get_sheet_path(files, "Output")
    checks_path = get_sheet_path(files, "Checks")
    story_path = get_sheet_path(files, "Story")
    log_path = get_sheet_path(files, "Agent Log")
    readme_path = get_sheet_path(files, "README")

    inputs_root = ET.fromstring(files[inputs_path])
    dcf_root = ET.fromstring(files[dcf_path])
    output_root = ET.fromstring(files[output_path])
    checks_root = ET.fromstring(files[checks_path])
    story_root = ET.fromstring(files[story_path])
    log_root = ET.fromstring(files[log_path])
    readme_root = ET.fromstring(files[readme_path])

    # ---------------- Inputs ----------------
    inputs_data = inputs_root.find(q("sheetData"))
    assert inputs_data is not None

    # Scenario headers (assumptions + risk)
    r19 = get_row(inputs_data, 19, create=True)
    set_inline_string(ensure_cell(r19, "G", 19), "Pessimistic", style="27")
    set_inline_string(ensure_cell(r19, "H", 19), "Neutral", style="27")
    set_inline_string(ensure_cell(r19, "I", 19), "Optimistic", style="27")

    r18 = get_row(inputs_data, 18, create=True)
    set_inline_string(ensure_cell(r18, "G", 18), "SCENARIO ASSUMPTIONS", style="5")

    assumption_rows = list(range(20, 33))
    for rr in assumption_rows:
        row = get_row(inputs_data, rr, create=True)
        # Pessimistic (G)
        if rr in [20, 21, 22, 23, 24]:
            g_formula = f"C{rr}-0.02"
            i_formula = f"C{rr}+0.015"
        elif rr in [25, 26]:
            g_formula = f"C{rr}-0.03"
            i_formula = f"C{rr}+0.03"
        elif rr == 27:
            g_formula = f"C{rr}+0.005"
            i_formula = f"MAX(C{rr}-0.005,0)"
        elif rr == 28:
            g_formula = f"C{rr}"
            i_formula = f"C{rr}"
        elif rr == 29:
            g_formula = f"C{rr}+0.005"
            i_formula = f"MAX(C{rr}-0.005,0)"
        elif rr == 30:
            g_formula = f"C{rr}+0.005"
            i_formula = f"C{rr}-0.005"
        elif rr == 31:
            g_formula = f"MAX(C{rr}-0.01,0)"
            i_formula = f"C{rr}+0.01"
        else:  # rr == 32
            g_formula = f"C{rr}+0.003"
            i_formula = f"MAX(C{rr}-0.003,0)"

        set_formula(ensure_cell(row, "G", rr), g_formula, style="14")
        set_formula(ensure_cell(row, "H", rr), f"C{rr}", style="14")
        set_formula(ensure_cell(row, "I", rr), i_formula, style="14")

    # Risk scenario headers
    r36 = get_row(inputs_data, 36, create=True)
    set_inline_string(ensure_cell(r36, "G", 36), "Pessimistic", style="27")
    set_inline_string(ensure_cell(r36, "H", 36), "Neutral", style="27")
    set_inline_string(ensure_cell(r36, "I", 36), "Optimistic", style="27")

    # Risk scenario calculations rows 37-44
    risk_map = {
        37: ("C37", "C37", "C37", "16"),
        38: ("C38+0.005", "C38", "MAX(C38-0.005,0)", "16"),
        39: ("C39+0.10", "C39", "MAX(C39-0.10,0)", "16"),
        40: ("G37 + G39*G38", "H37 + H39*H38", "I37 + I39*I38", "18"),
        41: ("C41+0.005", "C41", "MAX(C41-0.005,0)", "16"),
        42: ("MIN(C42+0.05,0.80)", "C42", "MAX(C42-0.05,0)", "16"),
        43: (
            "G40*(1-G42) + G41*(1-G27)*G42",
            "H40*(1-H42) + H41*(1-H27)*H42",
            "I40*(1-I42) + I41*(1-I27)*I42",
            "18",
        ),
        44: ("MAX(C44-0.0075,0.005)", "C44", "MIN(C44+0.005,I37-0.0025)", "16"),
    }
    for rr, (gf, hf, iff, style) in risk_map.items():
        row = get_row(inputs_data, rr, create=True)
        set_formula(ensure_cell(row, "G", rr), gf, style=style)
        set_formula(ensure_cell(row, "H", rr), hf, style=style)
        set_formula(ensure_cell(row, "I", rr), iff, style=style)

    # Scenario weights
    r61 = get_row(inputs_data, 61, create=True)
    set_inline_string(ensure_cell(r61, "B", 61), "SCENARIO WEIGHTS (must sum to 100%)", style="5")

    r62 = get_row(inputs_data, 62, create=True)
    set_inline_string(ensure_cell(r62, "G", 62), "Pessimistic", style="27")
    set_inline_string(ensure_cell(r62, "H", 62), "Neutral", style="27")
    set_inline_string(ensure_cell(r62, "I", 62), "Optimistic", style="27")

    r63 = get_row(inputs_data, 63, create=True)
    set_number(ensure_cell(r63, "G", 63), "0.25", style="14")
    set_number(ensure_cell(r63, "H", 63), "0.5", style="14")
    set_number(ensure_cell(r63, "I", 63), "0.25", style="14")

    r64 = get_row(inputs_data, 64, create=True)
    set_inline_string(ensure_cell(r64, "B", 64), "Weight sum", style="7")
    set_formula(ensure_cell(r64, "G", 64), "SUM(G63:I63)", style="18")
    set_inline_string(ensure_cell(r64, "H", 64), "must equal 1.00", style="7")

    # ---------------- DCF ----------------
    dcf_data = dcf_root.find(q("sheetData"))
    assert dcf_data is not None

    # Section labels
    r43_d = get_row(dcf_data, 43, create=True)
    set_inline_string(ensure_cell(r43_d, "B", 43), "SCENARIO: PESSIMISTIC CASE", style="5")
    r44_d = get_row(dcf_data, 44, create=True)
    set_inline_string(ensure_cell(r44_d, "B", 44), "Uses Inputs!G20:I44 scenario controls", style="7")

    r80_d = get_row(dcf_data, 80, create=True)
    set_inline_string(ensure_cell(r80_d, "B", 80), "SCENARIO: OPTIMISTIC CASE", style="5")
    r81_d = get_row(dcf_data, 81, create=True)
    set_inline_string(ensure_cell(r81_d, "B", 81), "Uses Inputs!I20:I44 scenario controls", style="7")

    clone_dcf_block(dcf_root, src_start=8, src_end=39, dst_start=45, scenario_col="G")
    clone_dcf_block(dcf_root, src_start=8, src_end=39, dst_start=82, scenario_col="I")

    # Weighted summary section
    r116 = get_row(dcf_data, 116, create=True)
    set_inline_string(ensure_cell(r116, "B", 116), "SCENARIO WEIGHTED SUMMARY", style="5")

    rows_summary = {
        117: ("Pessimistic value / share", "C76", "43"),
        118: ("Neutral value / share", "C39", "43"),
        119: ("Optimistic value / share", "C113", "43"),
        120: ("Weight sum", "SUM(Inputs!G63:I63)", "51"),
        121: ("Weighted value / share", "C117*Inputs!G63 + C118*Inputs!H63 + C119*Inputs!I63", "43"),
        122: ("Weighted equity value", "C74*Inputs!G63 + C37*Inputs!H63 + C111*Inputs!I63", "50"),
        123: ("Weighted enterprise value", "C72*Inputs!G63 + C35*Inputs!H63 + C109*Inputs!I63", "50"),
    }
    for rr, (label, formula, style) in rows_summary.items():
        row = get_row(dcf_data, rr, create=True)
        set_inline_string(ensure_cell(row, "B", rr), label, style="30")
        set_formula(ensure_cell(row, "C", rr), formula, style=style)

    # ---------------- Output ----------------
    out_data = output_root.find(q("sheetData"))
    assert out_data is not None

    # Weighted headline outputs
    for rr, formula in [
        (6, "C15*C24 + C16*C25 + C17*C26"),
        (7, "C18*C24 + C19*C25 + C20*C26"),
        (8, "C21*C24 + C22*C25 + C23*C26"),
    ]:
        row = get_row(out_data, rr, create=True)
        set_formula(ensure_cell(row, "C", rr), formula, style=("43" if rr == 6 else "50"))

    # Detailed scenario output contract rows
    detail_rows = {
        15: ("Pessimistic value / share", "DCF!C76", "USD/share", "43"),
        16: ("Neutral value / share", "DCF!C39", "USD/share", "43"),
        17: ("Optimistic value / share", "DCF!C113", "USD/share", "43"),
        18: ("Pessimistic equity value", "DCF!C74", "USD mm", "50"),
        19: ("Neutral equity value", "DCF!C37", "USD mm", "50"),
        20: ("Optimistic equity value", "DCF!C111", "USD mm", "50"),
        21: ("Pessimistic EV", "DCF!C72", "USD mm", "50"),
        22: ("Neutral EV", "DCF!C35", "USD mm", "50"),
        23: ("Optimistic EV", "DCF!C109", "USD mm", "50"),
        24: ("Pessimistic weight", "Inputs!G63", "", "51"),
        25: ("Neutral weight", "Inputs!H63", "", "51"),
        26: ("Optimistic weight", "Inputs!I63", "", "51"),
        27: ("Weight sum", "SUM(C24:C26)", "", "51"),
    }
    for rr, (label, formula, unit, style) in detail_rows.items():
        row = get_row(out_data, rr, create=True)
        set_inline_string(ensure_cell(row, "B", rr), label, style="10")
        set_formula(ensure_cell(row, "C", rr), formula, style=style)
        set_inline_string(ensure_cell(row, "D", rr), unit, style="7")

    # ---------------- Checks ----------------
    chk_data = checks_root.find(q("sheetData"))
    assert chk_data is not None

    checks_extra = {
        10: ("Scenario weights sum = 100%", 'IF(ABS(Inputs!G64-1)<0.0001,"PASS","FAIL")', "Required for weighted valuation."),
        11: ("Pessimistic WACC > g", 'IF(Inputs!G43>Inputs!G44,"PASS","FAIL")', "Scenario hard constraint."),
        12: ("Neutral WACC > g", 'IF(Inputs!C43>Inputs!C44,"PASS","FAIL")', "Scenario hard constraint."),
        13: ("Optimistic WACC > g", 'IF(Inputs!I43>Inputs!I44,"PASS","FAIL")', "Scenario hard constraint."),
        14: ("Pessimistic g <= rf", 'IF(Inputs!G44<=Inputs!G37,"PASS","FAIL")', "Long-run scenario constraint."),
        15: ("Neutral g <= rf", 'IF(Inputs!C44<=Inputs!C37,"PASS","FAIL")', "Long-run scenario constraint."),
        16: ("Optimistic g <= rf", 'IF(Inputs!I44<=Inputs!I37,"PASS","FAIL")', "Long-run scenario constraint."),
        17: ("Weighted output exists", 'IFERROR(IF(Output!C6>0,"PASS","REVIEW"),"FAIL")', "Must exist before memo publish."),
    }
    for rr, (label, formula, note) in checks_extra.items():
        row = get_row(chk_data, rr, create=True)
        set_inline_string(ensure_cell(row, "B", rr), label, style="7")
        set_formula(ensure_cell(row, "C", rr), formula, style="22")
        set_inline_string(ensure_cell(row, "D", rr), note, style="7")

    # ---------------- Story ----------------
    story_data = story_root.find(q("sheetData"))
    assert story_data is not None

    r22 = get_row(story_data, 22, create=True)
    set_inline_string(ensure_cell(r22, "B", 22), "SCENARIO STORY GRID (link narrative to assumptions)", style="5")

    header_vals = [
        ("B", "Scenario"),
        ("C", "Core narrative"),
        ("D", "Linked operating driver"),
        ("E", "KPI to track"),
        ("F", "Disconfirming evidence"),
        ("G", "Citation / source ID"),
    ]
    r23 = get_row(story_data, 23, create=True)
    for col, txt in header_vals:
        set_inline_string(ensure_cell(r23, col, 23), txt, style="27")

    for rr, scen in [(24, "Pessimistic"), (25, "Neutral"), (26, "Optimistic")]:
        row = get_row(story_data, rr, create=True)
        set_inline_string(ensure_cell(row, "B", rr), scen, style="48")
        for col in ["C", "D", "E", "F", "G"]:
            set_inline_string(ensure_cell(row, col, rr), "", style="49")

    r28 = get_row(story_data, 28, create=True)
    set_inline_string(ensure_cell(r28, "B", 28), "Memo hooks: tie each key claim to scenario assumption and output range.", style="7")

    # ---------------- Agent Log ----------------
    log_data = log_root.find(q("sheetData"))
    assert log_data is not None

    # Expand assumption journal header with Scenario + Reviewer columns.
    r220 = get_row(log_data, 220, create=True)
    assumption_header = [
        ("B", "Assumption"),
        ("C", "Scenario"),
        ("D", "Value"),
        ("E", "Unit"),
        ("F", "Where in model"),
        ("G", "Source"),
        ("H", "Method"),
        ("I", "Rationale (high-level)"),
        ("J", "Confidence"),
        ("K", "Reviewer"),
    ]
    for col, txt in assumption_header:
        set_inline_string(ensure_cell(r220, col, 220), txt, style="56")

    for rr in range(221, 312):
        row = get_row(log_data, rr, create=True)
        # Ensure K column exists as writable style.
        cell = ensure_cell(row, "K", rr)
        if cell.find(q("v")) is None and cell.find(q("is")) is None and cell.find(q("f")) is None:
            set_number(cell, "", style="55")
        else:
            cell.attrib["s"] = "55"
            cell.attrib["t"] = "n"

    # Add story journal block
    r249 = get_row(log_data, 249, create=True)
    set_inline_string(ensure_cell(r249, "B", 249), "STORY JOURNAL (scenario narrative -> valuation linkage)", style="5")

    r250 = get_row(log_data, 250, create=True)
    story_headers = [
        ("B", "Scenario"),
        ("C", "Story claim"),
        ("D", "Linked metric / range"),
        ("E", "Supporting evidence"),
        ("F", "Risk to claim"),
        ("G", "Catalyst"),
        ("H", "Update trigger"),
        ("I", "Confidence"),
        ("J", "Reviewer"),
    ]
    for col, txt in story_headers:
        set_inline_string(ensure_cell(r250, col, 250), txt, style="56")

    # ---------------- README ----------------
    readme_data = readme_root.find(q("sheetData"))
    assert readme_data is not None

    def set_readme_line(rr: int, text: str) -> None:
        row = get_row(readme_data, rr, create=True)
        set_inline_string(ensure_cell(row, "B", rr), text, style="7")

    set_readme_line(7, "1) Fill Inputs (TTM + neutral assumptions in column C).")
    set_readme_line(8, "2) Review scenario overrides in Inputs columns G/H/I and set scenario weights (G63:I63).")
    set_readme_line(9, "3) Populate Dilution (TSM); optionally populate R&D and Lease modules.")
    set_readme_line(10, "4) Confirm Checks has no FAIL and Output weighted fields are populated.")
    set_readme_line(11, "5) Generate memo from weighted + scenario outputs; log rationale in Agent Log.")

    # ---------------- Defined names ----------------
    upsert_defined_name(wb_root, "inp_w_pess", "'Inputs'!G63")
    upsert_defined_name(wb_root, "inp_w_base", "'Inputs'!H63")
    upsert_defined_name(wb_root, "inp_w_opt", "'Inputs'!I63")

    for suffix, col in [("pess", "G"), ("base", "C"), ("opt", "I")]:
        upsert_defined_name(wb_root, f"inp_{suffix}_g1", f"'Inputs'!{col}20")
        upsert_defined_name(wb_root, f"inp_{suffix}_g2", f"'Inputs'!{col}21")
        upsert_defined_name(wb_root, f"inp_{suffix}_g3", f"'Inputs'!{col}22")
        upsert_defined_name(wb_root, f"inp_{suffix}_g4", f"'Inputs'!{col}23")
        upsert_defined_name(wb_root, f"inp_{suffix}_g5", f"'Inputs'!{col}24")
        upsert_defined_name(wb_root, f"inp_{suffix}_m5", f"'Inputs'!{col}25")
        upsert_defined_name(wb_root, f"inp_{suffix}_m10", f"'Inputs'!{col}26")
        upsert_defined_name(wb_root, f"inp_{suffix}_tax", f"'Inputs'!{col}27")
        upsert_defined_name(wb_root, f"inp_{suffix}_wacc", f"'Inputs'!{col}43")
        upsert_defined_name(wb_root, f"inp_{suffix}_gt", f"'Inputs'!{col}44")

    upsert_defined_name(wb_root, "out_value_ps_pess", "'Output'!$C$15")
    upsert_defined_name(wb_root, "out_value_ps_base", "'Output'!$C$16")
    upsert_defined_name(wb_root, "out_value_ps_opt", "'Output'!$C$17")
    upsert_defined_name(wb_root, "out_value_ps_weighted", "'Output'!$C$6")
    upsert_defined_name(wb_root, "out_equity_value_weighted", "'Output'!$C$7")
    upsert_defined_name(wb_root, "out_enterprise_value_weighted", "'Output'!$C$8")
    upsert_defined_name(wb_root, "out_wacc_pess", "'Inputs'!G43")
    upsert_defined_name(wb_root, "out_wacc_base", "'Inputs'!C43")
    upsert_defined_name(wb_root, "out_wacc_opt", "'Inputs'!I43")
    upsert_defined_name(wb_root, "out_terminal_g_pess", "'Inputs'!G44")
    upsert_defined_name(wb_root, "out_terminal_g_base", "'Inputs'!C44")
    upsert_defined_name(wb_root, "out_terminal_g_opt", "'Inputs'!I44")

    upsert_defined_name(wb_root, "log_assumptions_header", "'Agent Log'!$B$220:$K$220")
    upsert_defined_name(wb_root, "log_assumptions_firstrow", "'Agent Log'!$B$221:$K$221")
    upsert_defined_name(wb_root, "log_story_header", "'Agent Log'!$B$250:$J$250")
    upsert_defined_name(wb_root, "log_story_firstrow", "'Agent Log'!$B$251:$J$251")

    # Sort and dimension updates
    for root in [inputs_root, dcf_root, output_root, checks_root, story_root, log_root, readme_root]:
        sort_sheet(root)
        update_dimension(root)

    # Write XML bytes back.
    files["xl/workbook.xml"] = ET.tostring(wb_root, encoding="utf-8", xml_declaration=True)
    files[inputs_path] = ET.tostring(inputs_root, encoding="utf-8", xml_declaration=True)
    files[dcf_path] = ET.tostring(dcf_root, encoding="utf-8", xml_declaration=True)
    files[output_path] = ET.tostring(output_root, encoding="utf-8", xml_declaration=True)
    files[checks_path] = ET.tostring(checks_root, encoding="utf-8", xml_declaration=True)
    files[story_path] = ET.tostring(story_root, encoding="utf-8", xml_declaration=True)
    files[log_path] = ET.tostring(log_root, encoding="utf-8", xml_declaration=True)
    files[readme_path] = ET.tostring(readme_root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(template, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, content in files.items():
            zout.writestr(name, content)

    print(f"Updated template: {template}")
    print(f"Backup written: {backup}")


if __name__ == "__main__":
    main()
