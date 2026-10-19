"""Draw commerce_binding.ttl as an editable SVG.

    python ontology/build_binding_diagram.py

Reads the binding ontology (and the core ontology for labels) and draws
three parts in commerce_binding_diagram.svg:

  1. Binding model   the cb: vocabulary as a UML-style class diagram, and
                     where it attaches to core classes, properties and codes
  2. Coverage matrix core concept x source: which table holds the concept,
                     how many properties are bound, and whether the rows
                     are filtered or the concept is virtual
  3. Worked example  how every property of cc:Order is obtained in each
                     source (column or expression, value format, join,
                     code mapping or constant)

Same SVG conventions as build_class_diagram.py: plain <g>/<rect>/<text>/
<path>, one <g id> per box or cell, styles in one <style> block.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from rdflib import Graph, Namespace, RDF, RDFS, OWL

sys.dont_write_bytecode = True
import build_class_diagram as cd  # noqa: E402

HERE = Path(__file__).resolve().parent
CC = Namespace('https://ontoresearch.example/commerce/core#')
CB = Namespace('https://ontoresearch.example/commerce/binding#')
SKOS = Namespace('http://www.w3.org/2004/02/skos/core#')
PREFIXES = '''PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX cc: <https://ontoresearch.example/commerce/core#>
PREFIX cb: <https://ontoresearch.example/commerce/binding#>
'''
SOURCES = ['acme', 'bigriver', 'bobsuncle', 'canonical']
SOURCE_COLOUR = {'acme': '#2e7d4f', 'bigriver': '#2b5f9e', 'bobsuncle': '#b5651d', 'canonical': '#6a4c93'}
SOURCE_TINT = {'acme': '#eef6f1', 'bigriver': '#edf2f9', 'bobsuncle': '#fbf1e8', 'canonical': '#f2eef8'}
LINE_H, HEAD_H, PAD, BOX_W = cd.LINE_H, cd.HEAD_H, cd.PAD, 250

# Part 1 layout: box -> (x, y). Core terms are drawn as grey "external" boxes.
MODEL_LAYOUT = {
    'SourceSystem': (40, 0), 'Table': (370, 0), 'Column': (700, 0), 'CoreClass': (1030, 0),
    'ConceptBinding': (370, 230), 'PropertyBinding': (700, 230), 'CoreProperty': (1030, 230),
    'CodeIndividual': (1360, 230),
    'ValueFormat': (40, 470), 'AttributeBinding': (370, 470), 'RelationBinding': (700, 470),
    'ValueBinding': (1030, 470), 'ValueMap': (1360, 470),
}
EXTERNAL = {'CoreClass': ('owl:Class', 'a core concept, e.g. cc:Order'),
            'CoreProperty': ('core property', 'e.g. cc:grandTotal, cc:countryCode'),
            'CodeIndividual': ('code-list individual', 'e.g. cc:OrderStatus_PLACED')}
RANGE_BOX = {OWL.Class: 'CoreClass', OWL.DatatypeProperty: 'CoreProperty'}
# vocabulary properties declared without a domain or range: where they are used
UNDECLARED_ENDS = {
    'inSource': [('Table', 'SourceSystem'), ('ConceptBinding', 'SourceSystem')],
    'sourceColumn': [('PropertyBinding', 'Column')],
    'usesColumn': [('PropertyBinding', 'Column')],
    'valueFormat': [('PropertyBinding', 'ValueFormat')],
    'bindsProperty': [('PropertyBinding', 'CoreProperty')],
    'targetIndividual': [('ValueMap', 'CodeIndividual')],
    'constantIndividual': [('ValueBinding', 'CodeIndividual')],
}


def local(term):
    return str(term).split('#')[-1]


def unquote(sql):
    """'"CustomerId"' -> 'CustomerId' (keep quotes inside real expressions)."""
    return re.sub(r'^"([A-Za-z_][A-Za-z0-9_]*)"$', r'\1', str(sql))


def props_text(n):
    return f'{n} prop' + ('' if int(n) == 1 else 's')


def wrap(s, width):
    """Split text into lines of at most `width` characters (hard cut for long tokens)."""
    words, lines, cur = s.split(' '), [], ''
    for w in words:
        while len(w) > width:
            if cur:
                lines.append(cur)
                cur = ''
            lines.append(w[:width])
            w = w[width:]
        if len(cur) + len(w) + (1 if cur else 0) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f'{cur} {w}' if cur else w
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------------
# Part 1: binding model
# ---------------------------------------------------------------------

def binding_model(g, top):
    attrs = defaultdict(list)
    edges = defaultdict(list)                      # (from, to) -> [labels]
    for p in g.subjects(RDF.type, OWL.DatatypeProperty):
        if not str(p).startswith(str(CB)):
            continue
        dom, rng = g.value(p, RDFS.domain), g.value(p, RDFS.range)
        if dom is not None:
            attrs[local(dom)].append(f'{local(p)} : {local(rng) if rng is not None else "literal"}')
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        if not str(p).startswith(str(CB)):
            continue
        name = local(p)
        dom, rng = g.value(p, RDFS.domain), g.value(p, RDFS.range)
        functional = (p, RDF.type, OWL.FunctionalProperty) in g
        label = f'{name} {"0..1" if functional else "*"}'
        if rng == RDF.List:
            attrs[local(dom) if dom else 'RelationBinding'].append(f'{name} : list')
        elif name in UNDECLARED_ENDS:
            for a, b in UNDECLARED_ENDS[name]:
                edges[(a, b)].append(label)
        elif dom is not None and rng is not None:
            edges[(local(dom), RANGE_BOX.get(rng, local(rng)))].append(label)
    for k in attrs:
        attrs[k].sort()
    subclasses = [local(s) for s in g.subjects(RDFS.subClassOf, CB.PropertyBinding)]

    boxes, out, labels, placed = {}, [], [], []
    for name, (x, y) in MODEL_LAYOUT.items():
        lines = attrs.get(name, []) if name not in EXTERNAL else [EXTERNAL[name][1]]
        h = cd.box_height(len(lines))
        boxes[name] = (x, top + y, BOX_W, h)
        external = name in EXTERNAL
        title = EXTERNAL[name][0] if external else f'cb:{name}'
        parts = [f'<g id="model-{name}" class="{"ext-class" if external else "uml-class"}" '
                 f'transform="translate({x},{top + y})">',
                 f'<rect width="{BOX_W}" height="{h}" rx="4" class="{"box-ext" if external else "box"}"/>',
                 f'<rect width="{BOX_W}" height="{HEAD_H}" rx="4" class="{"head-ext" if external else "head-cb"}"/>',
                 cd.text(BOX_W / 2, 16, title, 'cls-name-dark' if external else 'cls-name', 'middle')]
        for i, line in enumerate(lines):
            parts.append(cd.text(8, HEAD_H + PAD + 11 + i * LINE_H, line, 'attr-def' if external else 'attr'))
        parts.append('</g>')
        out.append('\n'.join(parts))

    # generalization: subclasses -> PropertyBinding (tree with one triangle)
    px, py, pw, ph = boxes['PropertyBinding']
    apex_x, apex_y = px + pw / 2, py + ph
    bus_y = apex_y + 40
    edge_svg = [f'<path d="M{apex_x - 8},{apex_y + 12} L{apex_x},{apex_y} L{apex_x + 8},{apex_y + 12} Z" class="gen-head"/>',
                f'<path d="M{apex_x},{apex_y + 12} V{bus_y}" class="gen"/>']
    for sub in subclasses:
        sx, sy, sw, _sh = boxes[sub]
        edge_svg.append(f'<path d="M{apex_x},{bus_y} H{sx + sw / 2} V{sy}" class="gen"/>')

    for (a, b), names in edges.items():
        if a not in boxes or b not in boxes:
            continue
        ba, bb = boxes[a], boxes[b]
        ca = (ba[0] + ba[2] / 2, ba[1] + ba[3] / 2)
        cb_ = (bb[0] + bb[2] / 2, bb[1] + bb[3] / 2)
        p1, p2 = cd.border_point(ba, cb_), cd.border_point(bb, ca)
        if (b, a) in edges:                         # both directions: spread apart
            p1, p2 = cd.offset(p1, p2, 7 if a < b else -7)
        edge_svg.append(f'<path d="M{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f}" class="assoc" '
                        f'marker-end="url(#arrow)"><title>{escape(a)} → {escape(b)}</title></path>')
        mx, my = cd.label_position(p1, p2, sorted(names), boxes, placed)
        labels.append(cd.label_lines(mx, my, sorted(names), 'edge-label'))

    bottom = max(y + h for (_x, y, _w, h) in boxes.values())
    return '\n'.join(edge_svg + out + labels), bottom


# ---------------------------------------------------------------------
# Part 2: coverage matrix
# ---------------------------------------------------------------------

def coverage(g, top, row_order):
    q = PREFIXES + '''
    SELECT ?source ?cls ?binding ?table ?filter ?virtual (COUNT(DISTINCT ?pb) AS ?props) WHERE {
      ?binding a cb:ConceptBinding ; cb:inSource/cb:sourceCode ?source ; cb:bindsClass ?cls .
      OPTIONAL { ?binding cb:fromTable/cb:tableName ?table }
      OPTIONAL { ?binding cb:rowFilter ?filter }
      OPTIONAL { ?binding cb:isVirtual ?virtual }
      OPTIONAL { ?pb cb:ofConceptBinding ?binding }
    } GROUP BY ?source ?cls ?binding ?table ?filter ?virtual'''
    cells = defaultdict(list)
    for source, cls, binding, table, flt, virtual, n in g.query(q):
        if virtual:
            line = f'(virtual) · {props_text(n)}'
        else:
            line = f'{table}{" ⊂" if flt else ""} · {props_text(n)}'
        cells[(local(cls), str(source))].append(line)
    rows = [c for c in row_order if any((c, s) in cells for s in SOURCES)]

    head_w, col_w, row_pad = 190, 270, 8
    x0 = cd.MARGIN
    out = [cd.text(x0, top - 30, '2. Coverage: which table holds each core concept in each source', 'panel-title'),
           cd.text(x0, top - 12, '⊂ = only rows matching a filter (e.g. qty < 0)   ·   (virtual) = no table, one implied '
                                 'instance   ·   — = the source cannot provide the concept', 'subtitle')]
    for j, s in enumerate(SOURCES):
        cx = x0 + head_w + j * col_w
        out.append(f'<g id="coverage-head-{s}"><rect x="{cx}" y="{top}" width="{col_w}" height="26" '
                   f'fill="{SOURCE_COLOUR[s]}"/>' + cd.text(cx + col_w / 2, top + 17, s, 'cls-name', 'middle') + '</g>')
    y = top + 26
    for i, cls in enumerate(rows):
        n_lines = max([len(cells.get((cls, s), [])) for s in SOURCES] + [1])
        h = n_lines * LINE_H + row_pad * 2
        stripe = '#f8f9fa' if i % 2 else '#ffffff'
        out.append(f'<g id="coverage-row-{cls}"><rect x="{x0}" y="{y}" width="{head_w}" height="{h}" fill="{stripe}" class="grid"/>'
                   + cd.text(x0 + 8, y + row_pad + 11, cls, 'row-head') + '</g>')
        for j, s in enumerate(SOURCES):
            cx = x0 + head_w + j * col_w
            lines = cells.get((cls, s))
            fill = SOURCE_TINT[s] if lines else '#f1f3f4'
            out.append(f'<g id="coverage-{cls}-{s}"><rect x="{cx}" y="{y}" width="{col_w}" height="{h}" '
                       f'fill="{fill}" class="grid"/>')
            for k, line in enumerate(lines or ['—']):
                out.append(cd.text(cx + 8, y + row_pad + 11 + k * LINE_H, line, 'cell' if lines else 'cell-empty'))
            out.append('</g>')
        y += h
    return '\n'.join(out), y, x0 + head_w + len(SOURCES) * col_w


# ---------------------------------------------------------------------
# Part 3: worked example (every cc:Order property in every source)
# ---------------------------------------------------------------------

def order_example(g, top, left):
    q = PREFIXES + '''
    SELECT ?source ?prop ?kind ?expr ?fmt ?const ?constInd ?target ?targetCls ?join ?matchOn ?notation ?maps ?through ?tfilter WHERE {
      ?b cb:bindsClass cc:Order ; cb:inSource/cb:sourceCode ?source .
      ?pb cb:ofConceptBinding ?b ; cb:bindsProperty ?prop ; a ?kind .
      FILTER(?kind IN (cb:AttributeBinding, cb:RelationBinding, cb:ValueBinding))
      OPTIONAL { ?pb cb:sourceExpression ?expr }
      OPTIONAL { ?pb cb:valueFormat/rdfs:label ?fmt }
      OPTIONAL { ?pb cb:constantValue ?const }
      OPTIONAL { ?pb cb:constantIndividual/skos:notation ?constInd }
      OPTIONAL { ?pb cb:targetBinding ?tb . ?tb cb:bindsClass ?targetCls . OPTIONAL { ?tb cb:fromTable/cb:tableName ?target } }
      OPTIONAL { ?pb cb:joinExpressions/rdf:first ?join }
      OPTIONAL { ?pb cb:matchOnProperty ?matchOn }
      OPTIONAL { ?pb cb:matchOnNotation ?notation }
      OPTIONAL { ?pb cb:throughTable/cb:tableName ?through }
      OPTIONAL { ?pb cb:throughFilter ?tfilter }
      OPTIONAL { SELECT ?pb (COUNT(?m) AS ?maps) WHERE { ?pb cb:valueMap ?m } GROUP BY ?pb }
    }'''
    q = q.replace('PREFIX rdfs:', 'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nPREFIX rdfs:')
    cells, kinds = {}, {}
    for (source, prop, kind, expr, fmt, const, const_ind, target, target_cls, join, match_on, notation, maps,
         through, tfilter) in g.query(q):
        p, s, k = local(prop), str(source), local(kind)
        kinds[p] = k
        if const is not None:
            text_ = f'constant {const}'
        elif const_ind is not None:
            text_ = f'always {const_ind}'
        elif k == 'ValueBinding':
            text_ = f'{expr} → code' + (' (same codes)' if notation else f' ({maps} mapped values)')
        elif through is not None:
            text_ = f'→ {local(target_cls)} via {through} where {tfilter}'
        elif target_cls is not None:
            text_ = f'{unquote(join)} → {local(target_cls)}' + (f' ({target})' if target else '')
        elif match_on is not None:
            text_ = f'{expr} → lookup by {local(match_on)}'
        else:
            text_ = f'{expr}' + (f'  [{fmt}]' if fmt and fmt not in ('Text',) else '')
        cells[(p, s)] = text_
    order_kind = {'AttributeBinding': 0, 'RelationBinding': 1, 'ValueBinding': 2}
    props = sorted({p for p, _s in cells}, key=lambda p: (order_kind[kinds[p]], p))

    head_w, col_w, row_pad, chars = 170, 340, 6, 40
    x0 = left
    out = [cd.text(x0, top - 30, '3. Worked example: how each source supplies the properties of cc:Order', 'panel-title'),
           cd.text(x0, top - 12, 'column or SQL expression [value format]  ·  join → target table  ·  '
                                 'lookup by natural key  ·  code mapping  ·  constant', 'subtitle')]
    for j, s in enumerate(SOURCES):
        cx = x0 + head_w + j * col_w
        out.append(f'<g id="order-head-{s}"><rect x="{cx}" y="{top}" width="{col_w}" height="26" '
                   f'fill="{SOURCE_COLOUR[s]}"/>' + cd.text(cx + col_w / 2, top + 17, s, 'cls-name', 'middle') + '</g>')
    y = top + 26
    kind_label = {'AttributeBinding': 'attribute', 'RelationBinding': 'relation', 'ValueBinding': 'code'}
    for i, p in enumerate(props):
        wrapped = {s: wrap(cells[(p, s)], chars) if (p, s) in cells else ['—'] for s in SOURCES}
        n_lines = max(len(v) for v in wrapped.values())
        h = n_lines * 12 + row_pad * 2 + 2
        stripe = '#f8f9fa' if i % 2 else '#ffffff'
        out.append(f'<g id="order-row-{p}"><rect x="{x0}" y="{y}" width="{head_w}" height="{h}" fill="{stripe}" class="grid"/>'
                   + cd.text(x0 + 8, y + row_pad + 10, f'cc:{p}', 'row-head')
                   + cd.text(head_w + x0 - 8, y + row_pad + 10, kind_label[kinds[p]], 'kind', 'end') + '</g>')
        for j, s in enumerate(SOURCES):
            cx = x0 + head_w + j * col_w
            present = (p, s) in cells
            out.append(f'<g id="order-{p}-{s}"><rect x="{cx}" y="{y}" width="{col_w}" height="{h}" '
                       f'fill="{SOURCE_TINT[s] if present else "#f1f3f4"}" class="grid"/>')
            for k, line in enumerate(wrapped[s]):
                out.append(cd.text(cx + 8, y + row_pad + 10 + k * 12, line, 'code-cell' if present else 'cell-empty'))
            out.append('</g>')
        y += h
    return '\n'.join(out), y, x0 + head_w + len(SOURCES) * col_w


def main():
    g = Graph()
    g.parse(HERE / 'commerce_core.ttl')
    g.parse(HERE / 'commerce_binding.ttl')

    model_top = 150
    model_svg, model_bottom = binding_model(g, model_top)

    row_order = [n for col in cd.COLUMNS for n in col if isinstance(n, str)] + ['Country', 'Currency']
    cov_top = model_bottom + 120
    cov_svg, cov_bottom, cov_right = coverage(g, cov_top, row_order)

    ex_left = cov_right + 80
    ex_svg, ex_bottom, ex_right = order_example(g, cov_top, ex_left)

    n_sources = len(set(g.objects(None, CB.sourceCode)))
    n_cb = len(set(g.subjects(RDF.type, CB.ConceptBinding)))
    n_pb = sum(len(set(g.subjects(RDF.type, t))) for t in (CB.AttributeBinding, CB.RelationBinding, CB.ValueBinding))
    width = int(max(ex_right, 1640) + cd.MARGIN)
    height = int(max(cov_bottom, ex_bottom) + cd.MARGIN)

    header = [cd.text(cd.MARGIN, 34, 'Commerce binding ontology', 'title'),
              cd.text(cd.MARGIN, 56, f'Generated from commerce_binding.ttl: {n_sources} sources, {n_cb} concept bindings, '
                                     f'{n_pb} property bindings. Core terms (grey) come from commerce_core.ttl.',
                      'subtitle'),
              cd.text(cd.MARGIN, model_top - 30, '1. Binding model: the general-purpose cb: vocabulary', 'panel-title'),
              cd.text(cd.MARGIN, model_top - 12, 'Every source is described with these classes; adding a store adds '
                                                 'instances, never new concepts. Arrows: object properties '
                                                 '(0..1 = functional, * = many). Hollow triangle = subclass.',
                      'subtitle')]

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{cd.FONT}">
<title>Commerce binding ontology diagram</title>
<style>
  .box {{ fill: #ffffff; stroke: #5f6368; stroke-width: 1.2; }}
  .box-ext {{ fill: #f8f9fa; stroke: #9aa0a6; stroke-width: 1.2; stroke-dasharray: 5 3; }}
  .head-cb {{ fill: #1a5c6b; }}
  .head-ext {{ fill: #dadce0; }}
  .cls-name {{ font-size: 13px; font-weight: bold; fill: #ffffff; }}
  .cls-name-dark {{ font-size: 13px; font-weight: bold; fill: #202124; }}
  .attr {{ font-size: 11px; fill: #202124; }}
  .attr-def {{ font-size: 10.5px; font-style: italic; fill: #5f6368; }}
  .assoc {{ fill: none; stroke: #80868b; stroke-width: 1.1; }}
  .gen {{ fill: none; stroke: #202124; stroke-width: 1.2; }}
  .gen-head {{ fill: #ffffff; stroke: #202124; stroke-width: 1.2; }}
  .edge-label {{ font-size: 10px; fill: #3c4043; paint-order: stroke; stroke: #ffffff; stroke-width: 3px; stroke-linejoin: round; }}
  .grid {{ stroke: #dadce0; stroke-width: 1; }}
  .row-head {{ font-size: 11.5px; font-weight: bold; fill: #202124; }}
  .kind {{ font-size: 10px; fill: #80868b; }}
  .cell {{ font-size: 11px; fill: #202124; }}
  .code-cell {{ font-size: 10.5px; fill: #202124; font-family: Menlo, Consolas, monospace; }}
  .cell-empty {{ font-size: 11px; fill: #9aa0a6; }}
  .title {{ font-size: 20px; font-weight: bold; fill: #202124; }}
  .subtitle {{ font-size: 12px; fill: #5f6368; }}
  .panel-title {{ font-size: 15px; font-weight: bold; fill: #202124; }}
</style>
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 Z" fill="#80868b"/>
  </marker>
</defs>
<rect width="100%" height="100%" fill="#ffffff"/>
<g id="header">
{chr(10).join(header)}
</g>
<g id="binding-model">
{model_svg}
</g>
<g id="coverage-matrix">
{cov_svg}
</g>
<g id="order-example">
{ex_svg}
</g>
</svg>
'''
    out = HERE / 'commerce_binding_diagram.svg'
    out.write_text(svg)
    print(f'{out.name}: {width}x{height}px')


if __name__ == '__main__':
    main()
