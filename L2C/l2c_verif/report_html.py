from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from .style import (
    BORDER,
    FILL,
    GAP_STATUSES,
    STATUS_COLORS,
    STATUS_LABEL,
    STATUSES,
    TEXT,
    by_id,
    load_json,
    load_records,
    natural_key,
    sheet_key,
)

ATTR_LABEL = {
    "repere": "Repère",
    "diametre": "Diamètre",
    "quantite": "Quantité",
    "espacement": "Espacement (mm)",
    "espacement_mm": "Espacement (mm)",
    "longueur": "Longueur (mm)",
    "longueur_mm": "Longueur (mm)",
    "armature": "Armature",
    "type": "Type",
}
BAR_ATTRS = ["diametre", "quantite", "espacement_mm", "longueur_mm"]
NO_SHEET = "Sans feuillet de plan"
STYLE_TABLE = {"stroke": BORDER, "fill": None, "radius": 7, "pad": (0, 0), "full": True, "layer": 2}
STYLE_TOTAL = {"stroke": None, "fill": FILL, "radius": 5, "pad": (-1.5, -1), "full": True, "layer": 0}
STYLE_BAND = {"stroke": None, "fill": FILL, "radius": 7, "pad": (0, 0), "full": True, "layer": 1}
TAG = "report"


class Decorations:
    def __init__(self):
        self.styles: dict[str, dict] = {}

    def new(self, **style) -> str:
        group = f"deco{len(self.styles)}"
        self.styles[group] = style
        return group


def _chip_style(statut: str) -> dict:
    fill = STATUS_COLORS.get(statut, (TEXT, FILL))[1]
    return {"stroke": None, "fill": fill, "radius": 99, "pad": (4.5, 1.2), "full": False, "layer": 0}


def _esc(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return html.escape(str(value))


def _up(text: str) -> str:
    return html.escape(text.upper())


def _fmt_coord(value) -> str:
    return f"{value:.0f}" if isinstance(value, int | float) else "—"


def _counts_by_sheet(findings: list[dict], summary: dict) -> list[tuple[str | None, dict]]:
    counts: dict[str | None, dict] = {}
    for row in summary.get("par_feuillet") or []:
        if isinstance(row, dict) and row.get("feuillet"):
            counts.setdefault(row["feuillet"], dict.fromkeys(STATUSES, 0))
    for f in findings:
        sheet_counts = counts.setdefault(f.get("feuillet") or None, dict.fromkeys(STATUSES, 0))
        if f.get("statut") in sheet_counts:
            sheet_counts[f["statut"]] += 1
    return sorted(counts.items(), key=lambda kv: sheet_key(kv[0]))


def _sheet_titles(summary: dict) -> dict[str, str]:
    return {
        row["feuillet"]: str(row.get("titre") or "")
        for row in summary.get("par_feuillet") or []
        if isinstance(row, dict) and row.get("feuillet")
    }


def _summary_head(box: str) -> str:
    width = 55 / len(STATUSES)
    cells = "".join(
        f'<th class="num" style="width:{width:.2f}%">{_up(STATUS_LABEL[s])}</th>' for s in STATUSES
    )
    return f'<tr id="{box}-h"><th style="width:11%">FEUILLET</th><th style="width:34%">TITRE</th>{cells}</tr>'


def _summary_row(box: str, k: int, sheet: str | None, counts: dict, titles: dict[str, str]) -> str:
    name = html.escape(sheet) if sheet else NO_SHEET
    title = html.escape(titles.get(sheet, "") if sheet else "")
    cells = "".join(f'<td class="num">{counts[s]}</td>' for s in STATUSES)
    return f'<tr id="{box}-{k}"><td class="sheet">{name}</td><td>{title}</td>{cells}</tr>'


def _summary_table(rows: list[tuple[str | None, dict]], titles: dict[str, str], deco: Decorations) -> str:
    box, total = deco.new(**STYLE_TABLE), deco.new(**STYLE_TOTAL)
    body = [_summary_row(box, k, sheet, counts, titles) for k, (sheet, counts) in enumerate(rows)]
    totals = {s: sum(c[s] for _, c in rows) for s in STATUSES}
    cells = "".join(f'<td class="num tot" id="{total}-{k}">{totals[s]}</td>' for k, s in enumerate(STATUSES))
    body.append(f'<tr id="{box}-t"><td class="tot" colspan="2" id="{total}-x">TOTAL</td>{cells}</tr>')
    return f"<table>{_summary_head(box)}{''.join(body)}</table>"


def _location_line(label: str, item: dict | None, with_sheet: bool, attrs: str) -> str:
    if not item:
        return f'<p {attrs}><span class="lbl">{label} :</span> —</p>'
    parts = [f"feuillet {_esc(item.get('feuillet'))}"] if with_sheet and item.get("feuillet") else []
    parts.append(f"fichier {_esc(item.get('fichier'))}")
    parts.append(f"page {_esc(item.get('page'))}")
    parts.append(f"X {_fmt_coord(item.get('x'))}, Y {_fmt_coord(item.get('y'))}")
    return f'<p {attrs}><span class="lbl">{label} :</span> {" · ".join(parts)}</p>'


def _bar_rows(item: dict | None, side: str) -> list[dict]:
    rows = []
    for bar in (item or {}).get("armature") or []:
        for attr in BAR_ATTRS:
            value = bar.get(attr)
            if value is not None:
                rows.append(
                    {
                        "attribut": attr,
                        "repere": bar.get("repere"),
                        "plan": value if side == "plan" else "absent",
                        "atelier": value if side == "atelier" else "absent",
                    }
                )
    return rows


def _gap_row(box: str, k: int, row: dict) -> str:
    label = html.escape(ATTR_LABEL.get(str(row.get("attribut")), str(row.get("attribut") or "—")))
    values = "".join(f"<td>{_esc(row.get(key))}</td>" for key in ("repere", "plan", "atelier"))
    return f'<tr id="{box}-{k}"><td>{label}</td>{values}</tr>'


def _gap_table(rows: list[dict], deco: Decorations) -> str:
    if not rows:
        return ""
    box = deco.new(**STYLE_TABLE)
    head = (
        f'<tr id="{box}-h"><th style="width:28%">ATTRIBUT</th><th style="width:24%">REPÈRE</th>'
        '<th style="width:24%">PLAN</th><th style="width:24%">ATELIER</th></tr>'
    )
    return f"<table>{head}{''.join(_gap_row(box, k, r) for k, r in enumerate(rows))}</table>"


def _first_value(key: str, *records: dict | None):
    return next((r.get(key) for r in records if r and r.get(key)), None)


def _gap_rows(finding: dict, plan_item: dict | None, shop_item: dict | None) -> list[dict]:
    rows = list(finding.get("ecarts") or [])
    if rows:
        return rows
    if finding.get("statut") == "manquant_atelier":
        return _bar_rows(plan_item, "plan")
    if finding.get("statut") == "ajoute_atelier":
        return _bar_rows(shop_item, "atelier")
    return rows


def _finding_head(finding: dict, statut: str, band: str, chip: str) -> str:
    color = STATUS_COLORS.get(statut, (TEXT, FILL))[0]
    return (
        f'<p class="fhead" id="{band}-0">{_esc(finding.get("element"))}&#160;&#160;&#160;&#160;'
        f'<span class="chip" id="{chip}-0" style="color:{color}">'
        f"{_up(STATUS_LABEL.get(statut, statut))}</span></p>"
    )


def _finding_meta(finding: dict, plan_item: dict | None, shop_item: dict | None, band: str) -> str:
    grid = _first_value("localisation", plan_item, shop_item) or finding.get("element")
    level = finding.get("niveau") or _first_value("niveau", plan_item, shop_item)
    element_type = _esc(finding.get("type_element"))
    return (
        f'<p class="meta" id="{band}-1"><span class="lbl">Type :</span> {element_type} · '
        f'<span class="lbl">Niveau :</span> {_esc(level)} · '
        f'<span class="lbl">Grille :</span> {_esc(grid)}</p>'
    )


def _finding_block(finding: dict, plan_items: dict, shop_items: dict, deco: Decorations) -> str:
    statut = finding.get("statut", "conforme")
    plan_item = plan_items.get(finding.get("plan_item"))
    shop_item = shop_items.get(finding.get("atelier_item"))
    band, chip = deco.new(**STYLE_BAND), deco.new(**_chip_style(statut))
    rows = _gap_rows(finding, plan_item, shop_item)
    note = ""
    if finding.get("note") and not rows:
        note = f'<p class="note"><span class="lbl">Note :</span> {_esc(finding.get("note"))}</p>'
    return (
        '<div class="finding">'
        + _finding_head(finding, statut, band, chip)
        + _finding_meta(finding, plan_item, shop_item, band)
        + _location_line("Plan", plan_item, True, f'class="meta" id="{band}-2"')
        + _location_line("Atelier", shop_item, False, f'class="meta last" id="{band}-3"')
        + _gap_table(rows, deco)
        + note
        + "</div>"
    )


def _gap_sections(findings: list[dict], plan_items: dict, shop_items: dict, deco: Decorations) -> list[str]:
    order = {s: i for i, s in enumerate(GAP_STATUSES)}
    by_sheet: dict[str | None, list[dict]] = {}
    for f in findings:
        if f.get("statut") in order:
            by_sheet.setdefault(f.get("feuillet") or None, []).append(f)
    parts = []
    for sheet in sorted(by_sheet, key=sheet_key):
        parts.append(f"<h3>{_up(sheet) if sheet else _up(NO_SHEET)}</h3>")
        for f in sorted(by_sheet[sheet], key=lambda f: (order[f["statut"]], natural_key(f.get("element")))):
            parts.append(_finding_block(f, plan_items, shop_items, deco))
    return parts


def build_html(out_dir: Path, with_logo: bool) -> tuple[str, Decorations]:
    out_dir = Path(out_dir)
    summary = load_json(out_dir / "summary.json", {}, TAG)
    findings = load_records(out_dir / "findings.json", TAG)
    plan_items = by_id(load_records(out_dir / "items_plan.json", TAG))
    shop_items = by_id(load_records(out_dir / "items_atelier.json", TAG))
    deco = Decorations()
    project = str(summary.get("projet") or out_dir.name)
    date = str(summary.get("genere_le") or dt.date.today().isoformat())[:10]
    title = "Rapport de vérification des dessins d'atelier — " + project + " — " + date
    parts = [
        '<p class="logo"><img src="logo.svg" style="height:22pt"/></p>' if with_logo else "",
        f"<h1>{_up(title)}</h1>",
        f"<h2>{_up('Conformités et non-conformités par feuillet')}</h2>",
        _summary_table(_counts_by_sheet(findings, summary), _sheet_titles(summary), deco),
        f"<h2>{_up('Détail des écarts')}</h2>",
        *_gap_sections(findings, plan_items, shop_items, deco),
    ]
    return f"<html><body>{''.join(parts)}</body></html>", deco
