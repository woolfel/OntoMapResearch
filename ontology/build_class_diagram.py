"""Draw a UML-style class diagram of commerce_core.ttl as an editable SVG.

    python ontology/build_class_diagram.py

Reads the ontology (not the Python spec), so the diagram always matches
commerce_core.ttl. Output: commerce_core_class_diagram.svg.

Drawing conventions
  * class box      : name, then datatype properties whose domain is the
                     class ('name : xsd type'); code-list properties are
                     shown as attributes typed by the code list
  * arrow          : object property between business classes, pointing
                     at the range; 0..1 = functional, * = many-valued;
                     inverse pairs are drawn once as 'a / b'
  * hollow triangle: subclass (defined classes Cart, PlacedOrder)
  * panels         : properties with no domain (usable on any class),
                     reference classes, and every code list with its codes

The SVG uses only <g>, <rect>, <text> and <path>, one <g id="..."> per
class, so it can be edited in Inkscape, Illustrator or by hand. Moving a
box does not move its lines; regenerate after changing the layout below.
"""
import math
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from rdflib import Graph, Namespace, RDF, RDFS, OWL
from rdflib.collection import Collection

HERE = Path(__file__).resolve().parent
CC = Namespace('https://ontoresearch.example/commerce/core#')
SKOS = Namespace('http://www.w3.org/2004/02/skos/core#')

# ---------------------------------------------------------------------
# Layout: columns of classes, top to bottom. Edit to rearrange.
# ---------------------------------------------------------------------
# A number in a column is a vertical spacer in pixels.
COLUMNS = [
    ['Manufacturer', 'Brand', 'ProductModel', 'Category'],
    ['ProductAttribute', 'Product', 'Promotion'],
    ['WarrantyPlan', 'Offer', 140, 'InventoryPosition'],
    ['Seller', 'AppliedDiscount', 'OrderLine', 'Warehouse'],
    ['Customer', 'Order'],
    ['Address', 'Shipment', 'ShipmentLine'],
    ['Payment', 'Refund', 'ReturnAuthorization', 'ReturnLine'],
]
DEFINED_PANEL = ['Cart', 'PlacedOrder']   # drawn as subclasses of an Order stub below the diagram
GROUPS = {   # header colour per area
    'catalog': ('#2e7d4f', ['Manufacturer', 'Brand', 'ProductModel', 'Category', 'Product',
                            'ProductAttribute', 'WarrantyPlan']),
    'selling': ('#2b5f9e', ['Seller', 'Offer', 'Warehouse', 'InventoryPosition', 'Promotion']),
    'ordering': ('#b5651d', ['Customer', 'Address', 'Order', 'Cart', 'PlacedOrder', 'OrderLine',
                             'AppliedDiscount']),
    'after the sale': ('#6a4c93', ['Payment', 'Shipment', 'ShipmentLine', 'ReturnAuthorization',
                                   'ReturnLine', 'Refund']),
}
BOX_W, LINE_H, HEAD_H, PAD = 250, 14, 24, 6
COL_STEP, ROW_GAP, MARGIN, TOP = 365, 56, 40, 110
FONT = 'Helvetica, Arial, sans-serif'


def local(term):
    return str(term).split('#')[-1]


def load():
    g = Graph()
    g.parse(HERE / 'commerce_core.ttl')
    code_lists = [c for c in g.subjects(RDFS.subClassOf, CC.CodeList)]
    classes = {local(c) for c in g.subjects(RDF.type, OWL.Class)
               if str(c).startswith(str(CC)) and c != CC.CodeList and c not in code_lists}
    code_names = {local(c) for c in code_lists}

    attrs = defaultdict(list)          # class -> [(name, type)]
    generic = []                       # properties with no domain
    edges = []                         # (from, to, label, functional)
    for p in g.subjects(RDF.type, OWL.DatatypeProperty):
        dom, rng = g.value(p, RDFS.domain), g.value(p, RDFS.range)
        entry = (local(p), local(rng))
        (attrs[local(dom)] if dom else generic).append(entry)
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        dom, rng = g.value(p, RDFS.domain), g.value(p, RDFS.range)
        functional = (p, RDF.type, OWL.FunctionalProperty) in g
        if dom is None:
            generic.append((local(p), local(rng)))
        elif local(rng) in code_names or local(rng) in ('Country', 'Currency'):
            attrs[local(dom)].append((local(p), local(rng)))
        else:
            inverse = g.value(p, OWL.inverseOf)
            edges.append((local(dom), local(rng), local(p), functional,
                          local(inverse) if inverse else None))

    codes = {}
    for c in code_lists:
        eq = g.value(c, OWL.equivalentClass)
        members = list(Collection(g, g.value(eq, OWL.oneOf))) if eq else []
        codes[local(c)] = [str(g.value(m, SKOS.notation)) for m in members]

    defined = {}
    for c in (CC.Cart, CC.PlacedOrder):
        inter = Collection(g, g.value(g.value(c, OWL.equivalentClass), OWL.intersectionOf))
        restriction = [x for x in inter if (x, RDF.type, OWL.Restriction) in g][0]
        one_of = g.value(g.value(restriction, OWL.someValuesFrom), OWL.oneOf)
        defined[local(c)] = [str(g.value(m, SKOS.notation)) for m in Collection(g, one_of)]

    for k in attrs:
        attrs[k].sort(key=lambda a: (a[1] in code_names or a[1] in ('Country', 'Currency'), a[0]))
    return classes, attrs, sorted(generic), edges, codes, defined


# ---------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------

def box_height(lines):
    return HEAD_H + PAD * 2 + max(lines, 1) * LINE_H


def border_point(box, toward):
    """Where the line from the box centre toward a point leaves the box."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    scale = min((w / 2) / abs(dx) if dx else math.inf, (h / 2) / abs(dy) if dy else math.inf)
    return cx + dx * scale, cy + dy * scale


def offset(p1, p2, amount):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy) or 1
    ox, oy = -dy / length * amount, dx / length * amount
    return (p1[0] + ox, p1[1] + oy), (p2[0] + ox, p2[1] + oy)


def status_lines(codes, per_line=3):
    """'orderStatus in {A, B, C,' ... wrapped for a defined class box."""
    if not codes:
        return []
    chunks = [', '.join(codes[i:i + per_line]) for i in range(0, len(codes), per_line)]
    lines = ['orderStatus in {' + chunks[0]] + ['    ' + c for c in chunks[1:]]
    return [l + (',' if i < len(lines) - 1 else '}') for i, l in enumerate(lines)]


def overlaps(r, rects):
    x, y, w, h = r
    return any(x < rx + rw and x + w > rx and y < ry + rh and y + h > ry for rx, ry, rw, rh in rects)


def label_position(p1, p2, lines, boxes, placed):
    """First point along the edge where the label clears every class box and
    every label already placed; records the label so later ones avoid it."""
    w = max(len(l) for l in lines) * 5.4 + 6
    h = len(lines) * 12 + 4
    ts = [0.5] + [0.5 + sign * k / 50 for k in range(2, 21) for sign in (-1, 1)]
    for t in ts:
        x, y = p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t
        rect = (x - w / 2, y - h / 2, w, h)
        if not overlaps(rect, list(boxes.values())) and not overlaps(rect, placed):
            placed.append(rect)
            return x, y
    x, y = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    placed.append((x - w / 2, y - h / 2, w, h))
    return x, y


def text(x, y, s, cls, anchor='start'):
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>'


def label_lines(x, y, lines, cls):
    first = y - (len(lines) - 1) * 6
    return '\n'.join(text(x, first + i * 12, s, cls, 'middle') for i, s in enumerate(lines))


# ---------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------

def main():
    classes, attrs, generic, edges, codes, defined = load()
    missing = classes - {n for col in COLUMNS for n in col if isinstance(n, str)} - {'Country', 'Currency'} - set(DEFINED_PANEL)
    if missing:
        raise SystemExit(f'add these classes to COLUMNS: {sorted(missing)}')
    colour = {c: col for col, names in GROUPS.values() for c in names}

    boxes = {}
    for ci, col in enumerate(COLUMNS):
        y = TOP
        for name in col:
            if isinstance(name, int):
                y += name
                continue
            lines = len(attrs.get(name, []))
            h = box_height(lines)
            boxes[name] = (MARGIN + ci * COL_STEP, y, BOX_W, h)
            y += h + ROW_GAP
    diagram_bottom = max(y + h for (x, y, w, h) in boxes.values())

    svg_classes, svg_edges, svg_labels = [], [], []

    # class boxes
    def class_box(name, x, y, w, h):
        head = colour.get(name, '#555')
        parts = [f'<g id="{name}" class="uml-class" transform="translate({x},{y})">',
                 f'<rect width="{w}" height="{h}" rx="4" class="box"/>',
                 f'<path d="M0,{HEAD_H} V4 Q0,0 4,0 H{w - 4} Q{w},0 {w},4 V{HEAD_H} Z" fill="{head}"/>',
                 text(w / 2, 16, name, 'cls-name', 'middle')]
        ty = HEAD_H + PAD + 11
        for line in status_lines(defined.get(name)):
            parts.append(text(8, ty, line, 'attr-def'))
            ty += LINE_H
        for attr, typ in attrs.get(name, []):
            is_code = typ not in ('string', 'decimal', 'integer', 'boolean', 'dateTime', 'date', 'anyURI')
            parts.append(f'<text x="8" y="{ty}" class="attr">{escape(attr)} : '
                         f'<tspan class="{"type-code" if is_code else "type"}">{escape(typ)}</tspan></text>')
            ty += LINE_H
        parts.append('</g>')
        return '\n'.join(parts)

    for name, (x, y, w, h) in boxes.items():
        svg_classes.append(class_box(name, x, y, w, h))

    # associations: group by unordered pair so parallel edges spread out
    pairs = defaultdict(list)
    seen_inverse = set()
    for dom, rng, prop, functional, inverse in edges:
        if inverse and (rng, dom, inverse) in seen_inverse:
            continue
        seen_inverse.add((dom, rng, prop))
        pairs[tuple(sorted((dom, rng)))].append((dom, rng, prop, functional, inverse))

    # pairs of boxes in the same column share a vertical centre line; give each its own x lane
    lane = {}
    for col in COLUMNS:
        names = [n for n in col if isinstance(n, str)]
        same = [pr for pr in pairs if pr[0] != pr[1] and pr[0] in names and pr[1] in names]
        same.sort(key=lambda pr: abs(names.index(pr[0]) - names.index(pr[1])))
        for i, pr in enumerate(same):
            lane[pr] = [0, -70, 70, -105, 105][i % 5]

    placed = []
    for (a, b), items in sorted(pairs.items(), key=lambda kv: kv[0][0] != kv[0][1]):   # loops first
        if a == b:                                   # self association: loop at the lower-right corner
            x, y, w, h = boxes[a]
            for i, (_d, _r, prop, functional, _inv) in enumerate(items):
                ly = y + h - 34 - i * 22
                label = f'{prop} {"0..1" if functional else "*"}'
                svg_edges.append(f'<path d="M{x + w},{ly} h22 v18 h-22" class="assoc" marker-end="url(#arrow)"/>')
                svg_labels.append(text(x + w + 26, ly + 13, label, 'edge-label'))
                placed.append((x + w, ly - 2, len(label) * 5.4 + 30, 22))
            continue
        directions = defaultdict(list)
        for d, r, prop, functional, inverse in items:
            directions[(d, r)].append((prop, functional, inverse))
        n = len(directions)
        for k, ((d, r), props) in enumerate(sorted(directions.items())):
            bd, br = boxes[d], boxes[r]
            dx = lane.get((a, b), 0)
            if dx:                                   # vertical lane inside the column
                top, bottom = (bd, br) if bd[1] < br[1] else (br, bd)
                x = top[0] + top[2] / 2 + dx
                p_top, p_bottom = (x, top[1] + top[3]), (x, bottom[1])
                p1, p2 = (p_top, p_bottom) if bd is top else (p_bottom, p_top)
            else:
                cd = (bd[0] + bd[2] / 2, bd[1] + bd[3] / 2)
                cr = (br[0] + br[2] / 2, br[1] + br[3] / 2)
                p1, p2 = border_point(bd, cr), border_point(br, cd)
            if n > 1:
                p1, p2 = offset(p1, p2, (k - (n - 1) / 2) * 14)
            svg_edges.append(f'<path d="M{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f}" '
                             f'class="assoc" marker-end="url(#arrow)"><title>{escape(d)} → {escape(r)}</title></path>')
            labels = [f'{prop}{" / " + inv if inv else ""} {"0..1" if functional else "*"}' for prop, functional, inv in props]
            mx, my = label_position(p1, p2, labels, boxes, placed)
            svg_labels.append(label_lines(mx, my, labels, 'edge-label'))

    # bottom panels: generic properties, reference classes, code lists
    py = diagram_bottom + 70
    panels = [text(MARGIN, py - 22, 'Properties usable on any class (no rdfs:domain)', 'panel-title')]
    gx, gy, per_col = MARGIN, py, math.ceil(len(generic) / 3)
    panels.append(f'<rect x="{gx}" y="{gy}" width="{3 * 230 + 20}" height="{per_col * LINE_H + 16}" rx="4" class="note"/>')
    for i, (prop, typ) in enumerate(generic):
        cx, cy = gx + 12 + (i // per_col) * 230, gy + 18 + (i % per_col) * LINE_H
        panels.append(f'<text x="{cx}" y="{cy}" class="attr">{escape(prop)} : <tspan class="type">{escape(typ)}</tspan></text>')
    ref_x = gx + 3 * 230 + 60
    panels.append(text(ref_x, py - 22, 'Reference data (looked up by ISO code)', 'panel-title'))
    for j, (name, items) in enumerate([('Country', ['countryCode : string', 'countryName : string']),
                                       ('Currency', ['currencyCode : string', 'currencyName : string',
                                                     'minorUnitDigits : integer'])]):
        bx = ref_x + j * 270
        h = box_height(len(items))
        panels.append(f'<g id="{name}" class="uml-class" transform="translate({bx},{gy})">'
                      f'<rect width="{BOX_W}" height="{h}" rx="4" class="box"/>'
                      f'<path d="M0,{HEAD_H} V4 Q0,0 4,0 H{BOX_W - 4} Q{BOX_W},0 {BOX_W},4 V{HEAD_H} Z" fill="#555"/>'
                      + text(BOX_W / 2, 16, name, 'cls-name', 'middle')
                      + ''.join(text(8, HEAD_H + PAD + 11 + i * LINE_H, s, 'attr') for i, s in enumerate(items))
                      + '</g>')

    cy0 = gy + per_col * LINE_H + 80
    panels.append(text(MARGIN, cy0 - 22, 'Code lists (owl:oneOf; values are skos:notation codes)', 'panel-title'))
    cw, per_row = 205, 10
    row_y, row_h = cy0, 0
    for i, (name, values) in enumerate(sorted(codes.items())):
        if i and i % per_row == 0:
            row_y += row_h + 24
            row_h = 0
        bx = MARGIN + (i % per_row) * (cw + 15)
        h = HEAD_H + PAD * 2 + len(values) * 13
        row_h = max(row_h, h)
        panels.append(f'<g id="{name}" class="uml-enum" transform="translate({bx},{row_y})">'
                      f'<rect width="{cw}" height="{h}" rx="4" class="box"/>'
                      f'<rect width="{cw}" height="{HEAD_H}" rx="4" class="enum-head"/>'
                      + text(cw / 2, 16, name, 'enum-name', 'middle')
                      + ''.join(text(8, HEAD_H + PAD + 10 + k * 13, v, 'code') for k, v in enumerate(values))
                      + '</g>')
    # defined classes: Order stub with Cart / PlacedOrder subclasses
    dy = row_y + row_h + 70
    panels.append(text(MARGIN, dy - 22, 'Defined classes (classified from cc:orderStatus)', 'panel-title'))
    stub_w, sub_w = 160, 330
    sub_h = max(box_height(len(status_lines(defined[n]))) for n in DEFINED_PANEL)
    total_sub = len(DEFINED_PANEL) * sub_w + (len(DEFINED_PANEL) - 1) * 60
    stub_x = MARGIN + total_sub / 2 - stub_w / 2
    panels.append(f'<g id="OrderStub" class="uml-class" transform="translate({stub_x},{dy})">'
                  f'<rect width="{stub_w}" height="{HEAD_H}" rx="4" fill="{colour["Order"]}" stroke="#5f6368"/>'
                  + text(stub_w / 2, 16, 'Order', 'cls-name', 'middle') + '</g>')
    bus_y = dy + HEAD_H + 30
    apex = (stub_x + stub_w / 2, dy + HEAD_H)
    panels.append(f'<path d="M{apex[0] - 8},{apex[1] + 12} L{apex[0]},{apex[1]} L{apex[0] + 8},{apex[1] + 12} Z" class="gen-head"/>')
    panels.append(f'<path d="M{apex[0]},{apex[1] + 12} V{bus_y}" class="gen"/>')
    for i, name in enumerate(DEFINED_PANEL):
        bx = MARGIN + i * (sub_w + 60)
        by = bus_y + 30
        panels.append(f'<path d="M{apex[0]},{bus_y} H{bx + sub_w / 2} V{by}" class="gen"/>')
        panels.append(class_box(name, bx, by, sub_w, sub_h))
    total_h = by + sub_h + MARGIN
    total_w = max(MARGIN * 2 + per_row * (cw + 15), MARGIN * 2 + (len(COLUMNS) - 1) * COL_STEP + BOX_W)

    legend_x = MARGIN
    legend = [text(MARGIN, 34, 'Commerce core ontology — class diagram', 'title'),
              text(MARGIN, 56, 'Generated from commerce_core.ttl. Arrows point at the range of an object property; '
                               '0..1 = functional, * = many. Hollow triangle = subclass.', 'subtitle')]
    for i, (group, (col, _names)) in enumerate(GROUPS.items()):
        lx = legend_x + i * 130
        legend.append(f'<rect x="{lx}" y="70" width="14" height="14" rx="2" fill="{col}"/>')
        legend.append(text(lx + 20, 81, group, 'legend'))

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h:.0f}" viewBox="0 0 {total_w} {total_h:.0f}" font-family="{FONT}">
<title>Commerce core ontology class diagram</title>
<style>
  .box {{ fill: #ffffff; stroke: #5f6368; stroke-width: 1.2; }}
  .note {{ fill: #fffbe6; stroke: #c9b458; stroke-width: 1; }}
  .enum-head {{ fill: #e8eaed; stroke: #5f6368; stroke-width: 1.2; }}
  .cls-name {{ font-size: 13px; font-weight: bold; fill: #ffffff; }}
  .enum-name {{ font-size: 12px; font-weight: bold; fill: #202124; }}
  .attr {{ font-size: 11px; fill: #202124; }}
  .attr-def {{ font-size: 10.5px; font-style: italic; fill: #5f6368; }}
  .type {{ fill: #5f6368; }}
  .type-code {{ fill: #8a4f00; font-style: italic; }}
  .code {{ font-size: 10.5px; fill: #3c4043; }}
  .assoc {{ fill: none; stroke: #80868b; stroke-width: 1.1; }}
  .gen {{ fill: none; stroke: #202124; stroke-width: 1.2; }}
  .gen-head {{ fill: #ffffff; stroke: #202124; stroke-width: 1.2; }}
  .edge-label {{ font-size: 10px; fill: #3c4043; paint-order: stroke; stroke: #ffffff; stroke-width: 3px; stroke-linejoin: round; }}
  .title {{ font-size: 20px; font-weight: bold; fill: #202124; }}
  .subtitle, .legend {{ font-size: 12px; fill: #5f6368; }}
  .panel-title {{ font-size: 14px; font-weight: bold; fill: #202124; }}
</style>
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 Z" fill="#80868b"/>
  </marker>
</defs>
<rect width="100%" height="100%" fill="#ffffff"/>
<g id="legend">
{chr(10).join(legend)}
</g>
<g id="associations">
{chr(10).join(svg_edges)}
</g>
<g id="classes">
{chr(10).join(svg_classes)}
</g>
<g id="association-labels">
{chr(10).join(svg_labels)}
</g>
<g id="panels">
{chr(10).join(panels)}
</g>
</svg>
'''
    out = HERE / 'commerce_core_class_diagram.svg'
    out.write_text(svg)
    print(f'{out.name}: {len(boxes)} classes, {sum(len(v) for v in pairs.values())} associations, '
          f'{len(codes)} code lists, {total_w}x{total_h:.0f}px')


if __name__ == '__main__':
    main()
