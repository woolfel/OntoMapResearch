"""Ontology mapping service: look up source -> target mappings before guessing.

Loads commerce_core.ttl and commerce_binding.ttl once at start-up, then
answers mapping requests. A request carries two SQL schema scripts (a
source and a target). The service

  1. identifies which bound system each script describes (and reports
     schema drift: tables/columns that differ from what the ontology knows),
  2. maps every core concept both systems provide: table to table,
     property to property with a ready-to-run SQL transform (source format
     -> core convention -> target format), relationships (foreign keys,
     join tables, ISO-code lookups) and code values,
  3. checks every transform by running it against the submitted source
     schema, and every target column against the submitted target schema,
  4. lists everything it could NOT resolve, so an agent knows exactly what
     is left to infer (and that anything else must not be guessed).

Scripts the ontology does not know get name-similarity hints only, marked
"resolved_by": "name-similarity" - suggestions, not mappings.

Run (from the repository root):

    ontology/.venv/bin/python ontology/mapping_service.py serve [--port 8765]
    ontology/.venv/bin/python ontology/mapping_service.py map --source acme_shopping.sql --target canonical_ecommerce.sql
    ontology/.venv/bin/python ontology/mapping_service.py identify big_river.sql
    ontology/.venv/bin/python ontology/mapping_service.py sources

HTTP API (JSON in, JSON out; binds to 127.0.0.1 only):

    GET  /health                 service status
    GET  /sources                systems the ontology can resolve
    GET  /concepts               core concepts and their properties
    POST /identify  {"sql": "..."} or {"path": "..."}
    POST /map       {"source_sql" | "source_path": ..., "target_sql" | "target_path": ...,
                     "concepts": ["Order", ...]   (optional filter)}

Paths are resolved relative to the repository root and must stay inside it.
"""
import argparse
import difflib
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef
from rdflib.collection import Collection

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CC = Namespace('https://ontoresearch.example/commerce/core#')
CB = Namespace('https://ontoresearch.example/commerce/binding#')
SKOS = Namespace('http://www.w3.org/2004/02/skos/core#')
DCT = Namespace('http://purl.org/dc/terms/')
BIND_SRC = 'https://ontoresearch.example/commerce/binding/'
CORE_ONTOLOGY = URIRef('https://ontoresearch.example/commerce/core')
SERVICE_VERSION = '1.0.0'
MATCH_THRESHOLD = 0.5          # schema similarity needed to treat a script as a known system
NORMALISING_FORMATS = {'TrimmedText', 'Email', 'CountryAlpha2', 'CurrencyCode', 'RegionCode'}


def local(term):
    return str(term).split('#')[-1] if term is not None else None


def short_id(term):
    """'.../binding/acme#Order' -> 'acme:Order'."""
    s = str(term)
    if s.startswith(BIND_SRC):
        code, name = s[len(BIND_SRC):].split('#', 1)
        return f'{code}:{name}'
    if s.startswith(str(CC)):
        return 'cc:' + local(s)
    if s.startswith(str(CB)):
        return 'cb:' + local(s)
    return s


def norm(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def py(value):
    if value is None:
        return None
    if isinstance(value, Literal):
        return value.toPython()
    return str(value)


def sql_literal(value):
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


# ---------------------------------------------------------------------
# Ontology index (built once at start-up)
# ---------------------------------------------------------------------

class Ontology:
    def __init__(self, core_path=HERE / 'commerce_core.ttl', binding_path=HERE / 'commerce_binding.ttl'):
        started = time.time()
        g = Graph()
        g.parse(core_path)
        g.parse(binding_path)
        self.triples = len(g)
        self.files = [str(Path(core_path).relative_to(ROOT)), str(Path(binding_path).relative_to(ROOT))]
        self.version = py(g.value(CORE_ONTOLOGY, OWL.versionInfo))
        self._load_core(g)
        self._load_bindings(g)
        self.load_seconds = round(time.time() - started, 2)

    # -- core ---------------------------------------------------------
    def _load_core(self, g):
        code_classes = set(g.subjects(RDFS.subClassOf, CC.CodeList))
        self.classes, self.code_lists, self.code_by_individual = {}, {}, {}
        for c in g.subjects(RDF.type, OWL.Class):
            if not str(c).startswith(str(CC)) or c == CC.CodeList:
                continue
            parent = g.value(c, RDFS.subClassOf)
            entry = {'label': py(g.value(c, RDFS.label)), 'definition': py(g.value(c, SKOS.definition)),
                     'also_called': sorted(py(a) for a in g.objects(c, SKOS.altLabel)),
                     'parent': local(parent) if isinstance(parent, URIRef) else None}
            if c in code_classes:
                eq = g.value(c, OWL.equivalentClass)
                members = list(Collection(g, g.value(eq, OWL.oneOf))) if eq is not None else []
                self.code_lists[local(c)] = {py(g.value(m, SKOS.notation)): local(m) for m in members}
                for m in members:
                    self.code_by_individual[local(m)] = (local(c), py(g.value(m, SKOS.notation)))
            else:
                self.classes[local(c)] = entry
        self.properties = {}
        for kind, rdf_type in (('object', OWL.ObjectProperty), ('datatype', OWL.DatatypeProperty)):
            for p in g.subjects(RDF.type, rdf_type):
                if not str(p).startswith(str(CC)):
                    continue
                self.properties[local(p)] = {
                    'kind': kind, 'label': py(g.value(p, RDFS.label)),
                    'definition': py(g.value(p, SKOS.definition)),
                    'domain': local(g.value(p, RDFS.domain)), 'range': local(g.value(p, RDFS.range)),
                    'convention': py(g.value(p, CC.valueConvention)),
                    'functional': (p, RDF.type, OWL.FunctionalProperty) in g}
        self.conventions = py(g.value(CORE_ONTOLOGY, RDFS.comment))

    # -- bindings -----------------------------------------------------
    def _load_bindings(self, g):
        self.formats = {}
        for f in g.subjects(RDF.type, CB.ValueFormat):
            self.formats[local(f)] = {'label': py(g.value(f, RDFS.label)),
                                      'description': py(g.value(f, CB.formatDescription)),
                                      'to_core': py(g.value(f, CB.conversionTemplate)),
                                      'from_core': py(g.value(f, CB.fromCoreTemplate))}
        self.sources = {}
        for s in g.subjects(RDF.type, CB.SourceSystem):
            code = py(g.value(s, CB.sourceCode))
            self.sources[code] = {'code': code, 'name': py(g.value(s, RDFS.label)),
                                  'schema_file': py(g.value(s, CB.schemaFile)),
                                  'sample_database': py(g.value(s, CB.sampleDatabase)),
                                  'note': py(g.value(s, RDFS.comment)), 'tables': {}}
        for t in g.subjects(RDF.type, CB.Table):
            code = short_id(t).split(':')[0]
            self.sources[code]['tables'][py(g.value(t, CB.tableName))] = []
        for c in g.subjects(RDF.type, CB.Column):
            t = g.value(c, CB.inTable)
            code = short_id(t).split(':')[0]
            self.sources[code]['tables'][py(g.value(t, CB.tableName))].append(py(g.value(c, CB.columnName)))

        def col_name(col):
            return (py(g.value(g.value(col, CB.inTable), CB.tableName)), py(g.value(col, CB.columnName)))

        self.concept_bindings = {}
        self.by_source_class = defaultdict(list)          # (source, class) -> [binding ids]
        for b in g.subjects(RDF.type, CB.ConceptBinding):
            bid = short_id(b)
            keys = g.value(b, CB.keyExpressions)
            entry = {'binding': bid, 'source': py(g.value(g.value(b, CB.inSource), CB.sourceCode)),
                     'concept': local(g.value(b, CB.bindsClass)),
                     'table': py(g.value(g.value(b, CB.fromTable), CB.tableName)),
                     'key': [py(k) for k in Collection(g, keys)] if keys is not None else [],
                     'filter': py(g.value(b, CB.rowFilter)), 'virtual': bool(py(g.value(b, CB.isVirtual))),
                     'note': py(g.value(b, RDFS.comment)),
                     'uses_columns': sorted(col_name(c) for c in g.objects(b, CB.usesColumn))
                                     + sorted(col_name(c) for c in g.objects(b, CB.keyColumn)),
                     'properties': {}}
            # columns the concept itself needs (key + row filter), not those of its properties
            words = set(re.findall(r'\w+', ' '.join(entry['key']) + ' ' + (entry['filter'] or '')))
            table_cols = self.sources[entry['source']]['tables'].get(entry['table'], [])
            entry['own_columns'] = sorted((entry['table'], c) for c in table_cols if c in words)
            self.concept_bindings[bid] = entry
            self.by_source_class[(entry['source'], entry['concept'])].append(bid)

        kinds = {CB.AttributeBinding: 'attribute', CB.RelationBinding: 'relation', CB.ValueBinding: 'code'}
        for rdf_type, kind in kinds.items():
            for pb in g.subjects(RDF.type, rdf_type):
                owner = self.concept_bindings[short_id(g.value(pb, CB.ofConceptBinding))]
                col = g.value(pb, CB.sourceColumn)
                joins = g.value(pb, CB.joinExpressions)
                through = g.value(pb, CB.throughTable)
                const_ind = g.value(pb, CB.constantIndividual)
                maps = {}
                for m in g.objects(pb, CB.valueMap):
                    maps[py(g.value(m, CB.sourceValue))] = self.code_by_individual[local(g.value(m, CB.targetIndividual))][1]
                entry = {
                    'binding': short_id(pb), 'kind': kind, 'property': local(g.value(pb, CB.bindsProperty)),
                    'column': col_name(col)[1] if col is not None else None,
                    'expression': py(g.value(pb, CB.sourceExpression)),
                    'format': local(g.value(pb, CB.valueFormat)),
                    'to_core': py(g.value(pb, CB.toCoreExpression)),
                    'constant': py(g.value(pb, CB.constantValue)),
                    'constant_code': self.code_by_individual[local(const_ind)][1] if const_ind is not None else None,
                    'target_binding': short_id(g.value(pb, CB.targetBinding)) if g.value(pb, CB.targetBinding) else None,
                    'joins': [py(j) for j in Collection(g, joins)] if joins is not None else [],
                    'match_on': local(g.value(pb, CB.matchOnProperty)),
                    'through': {'table': py(g.value(through, CB.tableName)),
                                'subject_columns': [py(x) for x in Collection(g, g.value(pb, CB.throughSubjectColumns))],
                                'object_columns': [py(x) for x in Collection(g, g.value(pb, CB.throughObjectColumns))],
                                'filter': py(g.value(pb, CB.throughFilter))} if through is not None else None,
                    'match_on_notation': bool(py(g.value(pb, CB.matchOnNotation))),
                    'value_map': maps,
                    'uses_columns': sorted(col_name(c) for c in g.objects(pb, CB.usesColumn)),
                }
                owner['properties'][entry['property']] = entry

    # -- helpers ------------------------------------------------------
    def class_order(self):
        return sorted(self.classes)

    def expression_sql(self, pb):
        """Raw source value as SQL (columns quoted)."""
        if pb['constant'] is not None:
            return sql_literal(pb['constant'])
        if pb['column']:
            return f'"{pb["column"]}"'
        return pb['expression']

    def to_core_sql(self, pb):
        if pb['constant'] is not None:
            return sql_literal(pb['constant'])
        if pb.get('to_core'):
            return pb['to_core']
        template = self.formats.get(pb['format'] or 'Text', self.formats['Text'])['to_core']
        return template.replace('{v}', self.expression_sql(pb))

    def compose(self, src_pb, tgt_pb):
        """SQL over the source table that yields the value in the target's format."""
        same = src_pb['constant'] is None and (src_pb['format'] or 'Text') == (tgt_pb['format'] or 'Text')
        if same and src_pb['format'] in NORMALISING_FORMATS:
            return self.to_core_sql(src_pb)          # same representation, but still clean it (trim, lower-case)
        if same:
            return self.expression_sql(src_pb)       # identical representation: copy as is
        core = self.to_core_sql(src_pb)
        template = self.formats.get(tgt_pb['format'] or 'Text', self.formats['Text'])['from_core']
        return template.replace('{v}', f'({core})')


# ---------------------------------------------------------------------
# Submitted schema analysis
# ---------------------------------------------------------------------

CONSTRAINT_WORDS = {'primary', 'unique', 'check', 'foreign', 'constraint', 'key', 'index'}


def parse_schema(sql_text):
    """Tables and columns of a schema script. Executes it in in-memory SQLite
    (so transforms can be validated); falls back to a regex parse for other
    dialects."""
    con = sqlite3.connect(':memory:')
    if hasattr(sqlite3, 'SQLITE_DBCONFIG_DQS_DML'):
        # Without this, SQLite silently turns a misspelled "Column" into the string 'Column',
        # so a transform over a renamed column would look valid.
        con.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, False)
    try:
        con.executescript(sql_text)
        tables = {}
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            tables[t] = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
        return tables, con, None
    except sqlite3.Error as e:
        con.close()
        error = f'SQLite could not execute the script ({e}); parsed CREATE TABLE statements instead, so transforms are not validated.'
    tables = {}
    for m in re.finditer(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`"\[]?[\w.]+[`"\]]?)\s*\((.*?)\)\s*;',
                         sql_text, re.I | re.S):
        name = m.group(1).strip('`"[]').split('.')[-1]
        depth, part, parts = 0, '', []
        for ch in m.group(2):
            depth += ch == '('
            depth -= ch == ')'
            if ch == ',' and depth == 0:
                parts.append(part)
                part = ''
            else:
                part += ch
        parts.append(part)
        cols = []
        for p in parts:
            p = re.sub(r'--[^\n]*', '', p).strip()
            if not p:
                continue
            first = p.split()[0].strip('`"[]')
            if first.lower() not in CONSTRAINT_WORDS:
                cols.append(first)
        tables[name] = cols
    return tables, None, error


class Schema:
    def __init__(self, onto, sql_text, label):
        self.label = label
        self.tables, self.con, self.parse_note = parse_schema(sql_text)
        self.lower_tables = {t.lower(): t for t in self.tables}
        self.system, self.confidence, self.candidates, self.drift = self._identify(onto)

    def has_column(self, table, column):
        t = self.lower_tables.get(str(table).lower())
        return bool(t) and str(column).lower() in {c.lower() for c in self.tables[t]}

    def missing_columns(self, binding_table, pb, cb):
        """Columns a binding needs that the submitted script does not have."""
        needed = set(pb['uses_columns']) | set(cb['own_columns'])
        if pb['column'] and binding_table:
            needed.add((binding_table, pb['column']))
        return sorted(f'{t}.{c}' for t, c in needed if not self.has_column(t, c))

    def validate(self, table, expression, where=None):
        """None = cannot validate; True = runs; else the SQLite error text."""
        if self.con is None or table is None:
            return None
        sql = f'SELECT {expression} FROM "{table}"' + (f' WHERE {where}' if where else '') + ' LIMIT 0'
        try:
            self.con.execute(sql)
            return True
        except sqlite3.Error as e:
            return str(e)

    def _identify(self, onto):
        given = {(t.lower(), c.lower()) for t, cols in self.tables.items() for c in cols}
        scores = []
        for code, src in onto.sources.items():
            known = {(t.lower(), c.lower()) for t, cols in src['tables'].items() for c in cols}
            union = known | given
            scores.append((len(known & given) / len(union) if union else 0.0, code, known))
        scores.sort(reverse=True)
        best_score, best_code, known = scores[0]
        candidates = [{'system': c, 'similarity': round(s, 3)} for s, c, _k in scores[:3]]
        if best_score < MATCH_THRESHOLD:
            return None, round(best_score, 3), candidates, None
        src_tables = {t.lower(): t for t in onto.sources[best_code]['tables']}
        names = {(t.lower(), c.lower()): f'{t}.{c}' for t, cols in onto.sources[best_code]['tables'].items() for c in cols}
        names.update({(t.lower(), c.lower()): f'{t}.{c}' for t, cols in self.tables.items() for c in cols})
        drift = {
            'tables_missing_from_script': sorted(src_tables[t] for t in set(src_tables) - set(self.lower_tables)),
            'tables_unknown_to_ontology': sorted(self.lower_tables[t] for t in set(self.lower_tables) - set(src_tables)),
            'columns_missing_from_script': sorted(names[k] for k in known - given if k[0] in self.lower_tables),
            'columns_unknown_to_ontology': sorted(names[k] for k in given - known if k[0] in src_tables),
        }
        return best_code, round(best_score, 3), candidates, drift

    def summary(self, onto):
        out = {'identified_as': self.system, 'similarity': self.confidence,
               'system_name': onto.sources[self.system]['name'] if self.system else None,
               'candidates': self.candidates, 'tables': len(self.tables),
               'validated_with_sqlite': self.con is not None}
        if self.parse_note:
            out['parse_note'] = self.parse_note
        if self.drift is not None:
            out['schema_drift'] = self.drift
            out['exact_match'] = not any(self.drift.values())
        return out


# ---------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------

def side(onto, cb):
    return {'binding': cb['binding'], 'table': cb['table'], 'key': cb['key'], 'row_filter': cb['filter'],
            'virtual': cb['virtual'], 'note': cb['note']}


def describe_property(onto, prop):
    p = onto.properties.get(prop, {})
    return {k: v for k, v in (('definition', p.get('definition')), ('convention', p.get('convention')),
                              ('range', p.get('range'))) if v}


def map_attribute(onto, src, tgt, s_cb, t_cb, s_pb, t_pb):
    entry = {'property': f'cc:{s_pb["property"]}', 'resolved_by': 'ontology',
             'source': {'expression': onto.expression_sql(s_pb), 'format': s_pb['format'],
                        'constant': s_pb['constant'] is not None, 'to_core': onto.to_core_sql(s_pb)},
             'target': {'column': t_pb['column'], 'format': t_pb['format']}}
    if t_pb['column'] is None:
        # target value is derived (expression / constant), not a plain column
        entry['target']['derived_from'] = t_pb['expression'] if t_pb['constant'] is None else f'constant {t_pb["constant"]}'
        entry['status'] = 'target_derived'
        entry['instruction'] = ('The target stores this property through an expression, not a single column. '
                                'Write it where that expression reads from (e.g. a child or lookup table).')
    else:
        entry['status'] = 'mapped'
        entry['target']['column_exists'] = tgt.has_column(t_cb['table'], t_pb['column'])
        if not entry['target']['column_exists']:
            entry['status'] = 'target_column_missing'
    entry['transform'] = onto.compose(s_pb, t_pb)
    manual_conversion_check(onto, entry, s_pb, t_pb)
    if not s_cb['virtual']:
        check = src.validate(s_cb['table'], entry['transform'], s_cb['filter'])
        entry['transform_validated'] = check if check is not True else True
        if check not in (True, None):
            entry['status'] = 'source_expression_invalid'
        missing = src.missing_columns(s_cb['table'], s_pb, s_cb)
        if missing:
            entry['status'] = 'source_column_missing'
            entry['transform_validated'] = f'source script has no column(s) {", ".join(missing)} (schema drift)'
    return entry


FREE_TEXT_FORMATS = {'BrandFreeText', 'CountryFreeText', 'BrowsePath'}


def manual_conversion_check(onto, entry, s_pb, t_pb):
    """Flag formats SQL cannot convert (e.g. local time zones), in either direction,
    and free text that needs cleansing."""
    s_fmt, t_fmt = s_pb['format'] or 'Text', t_pb['format'] or 'Text'
    if s_fmt != t_fmt:
        for fmt, key, direction in ((s_fmt, 'to_core', 'source'), (t_fmt, 'from_core', 'target')):
            if (onto.formats.get(fmt, {}).get(key) or '').startswith('/*'):
                entry['status'] = 'manual_conversion_required'
                entry['instruction'] = (f'The {direction} format needs a conversion SQLite cannot do: '
                                        f'{onto.formats[fmt]["description"]} The transform copies the value '
                                        'unconverted; apply the conversion in the ETL tool.')
                return
    if s_fmt in FREE_TEXT_FORMATS:
        entry['caveat'] = onto.formats[s_fmt]['description']


def map_relation(onto, src, tgt, s_cb, t_cb, s_pb, t_pb):
    entry = {'property': f'cc:{s_pb["property"]}', 'resolved_by': 'ontology', 'status': 'mapped'}

    def describe(pb):
        if pb['through']:
            return {'via_join_table': pb['through'], 'related_binding': pb['target_binding']}
        if pb['match_on']:
            return {'lookup_by': f'cc:{pb["match_on"]}', 'value': onto.expression_sql(pb), 'format': pb['format']}
        return {'join_expressions': pb['joins'], 'related_binding': pb['target_binding'],
                'related_key': onto.concept_bindings[pb['target_binding']]['key'] if pb['target_binding'] else None}

    entry['source'], entry['target'] = describe(s_pb), describe(t_pb)
    missing = src.missing_columns(s_cb['table'], s_pb, s_cb) if not s_cb['virtual'] else []
    if missing:
        entry['status'] = 'source_column_missing'
        entry['missing_columns'] = missing
    if s_pb['match_on'] and t_pb['match_on'] == s_pb['match_on'] and t_pb['column']:
        # both sides refer to the same natural key (ISO code): copy the value
        entry['target']['column'] = t_pb['column']
        entry['transform'] = onto.compose(s_pb, t_pb)
        manual_conversion_check(onto, entry, s_pb, t_pb)
        check = src.validate(s_cb['table'], entry['transform'], s_cb['filter']) if not s_cb['virtual'] else None
        entry['transform_validated'] = check
        entry['instruction'] = f'Copy the converted {s_pb["match_on"]} value into {t_cb["table"]}.{t_pb["column"]}.'
    elif t_pb['through']:
        entry['instruction'] = (f'Insert one row per related instance into {t_pb["through"]["table"]} '
                                f'({", ".join(t_pb["through"]["subject_columns"] + t_pb["through"]["object_columns"])})'
                                + (f' with {t_pb["through"]["filter"]}' if t_pb['through']['filter'] else '')
                                + '. The related instances come from the source relation described under "source".')
    else:
        fk = [re.sub(r'^"(.*)"$', r'\1', j) for j in t_pb['joins']]
        entry['target']['foreign_key_columns'] = fk
        entry['instruction'] = (f'Set {t_cb["table"]}.{", ".join(fk)} to the target key of the related '
                                f'cc:{onto.concept_bindings[t_pb["target_binding"]]["concept"] if t_pb["target_binding"] else "?"} '
                                'instance. Find it by evaluating the source join expressions on the source row and '
                                'looking up which target row was loaded from that source key (keep a source-key '
                                'to target-key map while loading, e.g. canonical source_key_map).')
    return entry


def code_values(onto, pb, code_list):
    """{source value: core notation} for a code binding."""
    if pb['constant_code']:
        return {None: pb['constant_code']}
    if pb['match_on_notation']:
        return {n: n for n in onto.code_lists[code_list]}
    return dict(pb['value_map'])


def map_code(onto, src, s_cb, t_cb, s_pb, t_pb):
    code_list = onto.properties[s_pb['property']]['range']
    src_values = code_values(onto, s_pb, code_list)
    if t_pb['constant_code']:
        return {'property': f'cc:{s_pb["property"]}', 'resolved_by': 'ontology', 'status': 'target_constant',
                'instruction': f'The target does not store this; it is always {t_pb["constant_code"]}.'}
    if t_pb['match_on_notation']:
        core_to_target = {n: [n] for n in onto.code_lists[code_list]}
    else:
        core_to_target = defaultdict(list)
        for tv, core in t_pb['value_map'].items():
            core_to_target[core].append(tv)
    table, unmapped = [], []
    for sv, core in src_values.items():
        targets = core_to_target.get(core, [])
        row = {'source_value': sv, 'core_code': core, 'target_value': targets[0] if targets else None}
        if len(targets) > 1:
            row['ambiguous_target_values'] = targets
        if not targets:
            unmapped.append(row)
        table.append(row)
    entry = {'property': f'cc:{s_pb["property"]}', 'code_list': f'cc:{code_list}', 'resolved_by': 'ontology',
             'source': {'expression': onto.expression_sql(s_pb)} if not s_pb['constant_code'] else
             {'constant': s_pb['constant_code']},
             'target': {'column': t_pb['column'], 'expression': None if t_pb['column'] else t_pb['expression']},
             'values': table, 'status': 'mapped' if not unmapped else 'partially_mapped'}
    if s_pb['constant_code']:
        entry['transform'] = sql_literal(table[0]['target_value']) if table[0]['target_value'] else None
    else:
        cases = ' '.join(f'WHEN {sql_literal(r["source_value"])} THEN {sql_literal(r["target_value"])}'
                         for r in table if r['target_value'] is not None)
        entry['transform'] = f'CASE {onto.expression_sql(s_pb)} {cases} END'
        check = src.validate(s_cb['table'], entry['transform'], s_cb['filter'])
        entry['transform_validated'] = check
        missing = src.missing_columns(s_cb['table'], s_pb, s_cb)
        if check not in (True, None) or missing:
            entry['status'] = 'source_column_missing' if missing else 'source_expression_invalid'
            if missing:
                entry['transform_validated'] = f'source script has no column(s) {", ".join(missing)} (schema drift)'
    if unmapped:
        entry['unmapped_values'] = [r['source_value'] for r in unmapped]
    return entry


def map_concept(onto, src, tgt, s_cb, t_cb):
    out = {'concept': f'cc:{s_cb["concept"]}', 'definition': onto.classes[s_cb['concept']]['definition'],
           'source': side(onto, s_cb), 'target': side(onto, t_cb), 'resolved_by': 'ontology',
           'attributes': [], 'relations': [], 'codes': [],
           'target_properties_without_source': [], 'source_properties_without_target': []}
    if not t_cb['virtual'] and t_cb['table'] and t_cb['table'].lower() not in tgt.lower_tables:
        out['status'] = 'target_table_missing'
    s_props, t_props = s_cb['properties'], t_cb['properties']
    for prop in sorted(set(s_props) | set(t_props)):
        s_pb, t_pb = s_props.get(prop), t_props.get(prop)
        if s_pb and t_pb:
            kind = t_pb['kind']
            if kind == 'attribute' and s_pb['kind'] == 'attribute':
                out['attributes'].append(map_attribute(onto, src, tgt, s_cb, t_cb, s_pb, t_pb))
            elif kind == 'relation':
                out['relations'].append(map_relation(onto, src, tgt, s_cb, t_cb, s_pb, t_pb))
            elif kind == 'code':
                out['codes'].append(map_code(onto, src, s_cb, t_cb, s_pb, t_pb))
        elif t_pb:
            item = {'property': f'cc:{prop}', 'kind': t_pb['kind'],
                    'target_column': t_pb['column'], 'target_format': t_pb['format'], **describe_property(onto, prop)}
            out['target_properties_without_source'].append(item)
        else:
            out['source_properties_without_target'].append({'property': f'cc:{prop}', 'kind': s_pb['kind'],
                                                            'source_expression': onto.expression_sql(s_pb)})
    return out


def used_columns(onto, system):
    used = set()
    for cb in onto.concept_bindings.values():
        if cb['source'] != system:
            continue
        used.update((t.lower(), c.lower()) for t, c in cb['uses_columns'])
        for pb in cb['properties'].values():
            used.update((t.lower(), c.lower()) for t, c in pb['uses_columns'])
            if pb['column'] and cb['table']:
                used.add((cb['table'].lower(), pb['column'].lower()))
            if pb['through']:
                for c in pb['through']['subject_columns'] + pb['through']['object_columns']:
                    used.add((pb['through']['table'].lower(), c.lower()))
            for j in pb['joins']:
                m = re.fullmatch(r'"?(\w+)"?', j)
                if m and cb['table']:
                    used.add((cb['table'].lower(), m.group(1).lower()))
    return used


def unmapped_columns(onto, schema, written):
    """Columns of the submitted script that no mapping reads (source) or writes (target)."""
    out = []
    for t, cols in schema.tables.items():
        for c in cols:
            if (t.lower(), c.lower()) not in written:
                out.append(f'{t}.{c}')
    return sorted(out)


ABBREVIATIONS = {'qty': 'quantity', 'amt': 'amount', 'no': 'number', 'num': 'number', 'nbr': 'number',
                 'nm': 'name', 'desc': 'description', 'cd': 'code', 'cust': 'customer', 'ccy': 'currency',
                 'prd': 'product', 'mfr': 'manufacturer', 'wt': 'weight', 'pct': 'percent', 'addr': 'address',
                 'qty_on_hand': 'quantityonhand', 'whse': 'warehouse', 'promo': 'promotion', 'disc': 'discount',
                 'cntry': 'country', 'stat': 'status', 'ts': 'at', 'dt': 'date'}
UNIT_SUFFIXES = {'cents': 'MoneyMinor', 'lbs': 'WeightPounds', 'lb': 'WeightPounds', 'grams': 'WeightGrams',
                 'kg': 'weight in kilograms (convert to grams)', 'flg': 'FlagYN or Flag01',
                 'flag': 'FlagYN or Flag01', 'ms': 'epoch milliseconds (convert to UTC timestamp)',
                 'epoch': 'epoch seconds (convert to UTC timestamp)'}
NAME_FORMATS = [(r'(_|^)(ts|at|time|timestamp)$', 'timestamp (check the time zone)'),
                (r'(_|^)(dt|date)$', 'DateISO or DateYYYYMMDD'), (r'(pct|percent)', 'PercentWhole or PercentFraction'),
                (r'(ccy|currency)', 'CurrencyCode'), (r'(cntry|country)', 'CountryAlpha2 or CountryFreeText'),
                (r'email', 'Email')]


def name_hints(onto, schema):
    """Suggest core concepts/properties for an unknown schema by name similarity.
    Column suggestions also vote for the concept their property belongs to."""
    concept_names = []
    for name, c in onto.classes.items():
        for label in [name, c['label']] + c['also_called']:
            concept_names.append((norm(re.sub(r'\(.*?\)', '', label)), name))
    prop_names = [(norm(p), p) for p in onto.properties] + \
                 [(norm(v['label']), p) for p, v in onto.properties.items() if v['label']]

    def score(name, cand):
        r = difflib.SequenceMatcher(None, name, cand).ratio()
        if len(name) >= 3 and (name in cand or cand in name):
            r = max(r, 0.75 if name != cand else 1.0)
        return r

    def best(name, choices, threshold):
        scores = defaultdict(float)
        for cand, target in choices:
            scores[target] = max(scores[target], score(name, cand))
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return [(t, round(s, 2)) for t, s in ranked[:3] if s >= threshold]

    hints = []
    for t, cols in schema.tables.items():
        prefixes = [c.lower().split('_')[0] + '_' for c in cols if '_' in c]
        common = max(set(prefixes), key=prefixes.count) if prefixes else None
        strip_prefix = common if common and prefixes.count(common) >= 0.6 * len(cols) and len(common) <= 5 else None
        votes, cols_out = defaultdict(float), []
        for c in cols:
            name = c.lower()
            if strip_prefix and name.startswith(strip_prefix):
                name = name[len(strip_prefix):]
            tokens = [tok for tok in re.split(r'[^a-z0-9]+', name) if tok]
            fmt = next((UNIT_SUFFIXES[tok] for tok in tokens[-1:] if tok in UNIT_SUFFIXES), None) \
                or next((f for pat, f in NAME_FORMATS if re.search(pat, c.lower())), None)
            tokens = [ABBREVIATIONS.get(tok, tok) for tok in tokens if tok not in UNIT_SUFFIXES] or tokens
            candidates = best(norm(''.join(tokens)), prop_names, 0.6)
            entry = {'column': c, 'candidate_properties': [{'core': f'cc:{p}', 'similarity': sc} for p, sc in candidates]}
            if fmt:
                entry['format_hint'] = fmt
            cols_out.append(entry)
            if candidates:
                domain = onto.properties[candidates[0][0]]['domain']
                if domain:
                    votes[domain] += candidates[0][1]
        table_name = norm(re.sub(r'^(tbl|t)_', '', t.lower()))
        name_scores = dict(best(table_name, concept_names, 0.0))
        top_vote = max(votes.values(), default=0) or 1     # columns are stronger evidence than the table name
        ranked = sorted(((0.3 * name_scores.get(cls, 0) + 0.7 * votes.get(cls, 0) / top_vote, cls)
                         for cls in set(name_scores) | set(votes)), reverse=True)
        hints.append({'table': t,
                      'candidate_concepts': [{'core': f'cc:{cls}', 'score': round(sc, 2),
                                              'name_similarity': name_scores.get(cls, 0),
                                              'column_votes': round(votes.get(cls, 0), 2)}
                                             for sc, cls in ranked[:3] if sc >= 0.2],
                      'columns': cols_out})
    return {'resolved_by': 'name-similarity',
            'warning': 'Suggestions only. The ontology does not know this schema; confirm each hint before use '
                       'and label anything you adopt as an LLM guess.',
            'tables': hints}


def known_side_bindings(onto, schema, concepts):
    """For the one known side: how each concept and property reads to/from the core convention."""
    out = []
    for cls in onto.class_order():
        if concepts and cls not in concepts:
            continue
        for bid in onto.by_source_class.get((schema.system, cls), []):
            cb = onto.concept_bindings[bid]
            out.append({'concept': f'cc:{cls}', **side(onto, cb),
                        'properties': [{'property': f'cc:{p}', 'kind': pb['kind'],
                                        'expression': onto.expression_sql(pb), 'format': pb['format'],
                                        'to_core': onto.to_core_sql(pb) if pb['kind'] == 'attribute' else None,
                                        'from_core_template': onto.formats.get(pb['format'] or 'Text', {}).get('from_core')}
                                       for p, pb in sorted(cb['properties'].items())]})
    return out


def map_schemas(onto, source_sql, target_sql, concepts=None):
    concepts = {c.replace('cc:', '') for c in concepts} if concepts else None
    src, tgt = Schema(onto, source_sql, 'source'), Schema(onto, target_sql, 'target')
    result = {'service': {'version': SERVICE_VERSION, 'ontology_files': onto.files, 'triples': onto.triples},
              'source': src.summary(onto), 'target': tgt.summary(onto),
              'core_conventions': onto.conventions}
    unresolved = {}

    if src.system and tgt.system:
        mappings = []
        for cls in onto.class_order():
            if concepts and cls not in concepts:
                continue
            s_ids = onto.by_source_class.get((src.system, cls), [])
            t_ids = onto.by_source_class.get((tgt.system, cls), [])
            if s_ids and t_ids:
                for sid in s_ids:
                    for tid in t_ids:
                        mappings.append(map_concept(onto, src, tgt, onto.concept_bindings[sid],
                                                    onto.concept_bindings[tid]))
            elif t_ids:
                unresolved.setdefault('target_concepts_without_source', []).append(
                    {'concept': f'cc:{cls}', 'target_tables': [onto.concept_bindings[t]['table'] for t in t_ids],
                     'definition': onto.classes[cls]['definition']})
            elif s_ids:
                unresolved.setdefault('source_concepts_without_target', []).append(
                    {'concept': f'cc:{cls}', 'source_tables': [onto.concept_bindings[s]['table'] for s in s_ids]})
        result['mappings'] = mappings

        written = used_columns(onto, tgt.system)
        read = used_columns(onto, src.system)
        if not concepts:
            unresolved['unmapped_source_columns'] = unmapped_columns(onto, src, read)
            unresolved['unmapped_target_columns'] = unmapped_columns(onto, tgt, written)
        for label, sch in (('source', src), ('target', tgt)):
            if sch.drift and (sch.drift['columns_unknown_to_ontology'] or sch.drift['tables_unknown_to_ontology']):
                unresolved[f'{label}_schema_drift'] = {
                    'tables_unknown_to_ontology': sch.drift['tables_unknown_to_ontology'],
                    'columns_unknown_to_ontology': sch.drift['columns_unknown_to_ontology']}
        problems = []
        for m in mappings:
            for group in ('attributes', 'relations', 'codes'):
                for e in m[group]:
                    if e.get('status') not in ('mapped', 'target_constant'):
                        problems.append({'concept': m['concept'], 'property': e['property'], 'status': e['status'],
                                         'detail': e.get('transform_validated') if isinstance(e.get('transform_validated'), str)
                                         else e.get('missing_columns') or e.get('unmapped_values') or e.get('instruction')})
            if m['target_properties_without_source']:
                unresolved.setdefault('target_properties_without_source', []).extend(
                    {'concept': m['concept'], 'target_table': m['target']['table'], **p}
                    for p in m['target_properties_without_source'])
        if problems:
            unresolved['mappings_needing_attention'] = problems
    else:
        for label, sch in (('source', src), ('target', tgt)):
            if sch.system:
                result[f'{label}_bindings'] = known_side_bindings(onto, sch, concepts)
            else:
                unresolved[f'{label}_schema_unknown'] = name_hints(onto, sch)

    counts = defaultdict(int)
    for m in result.get('mappings', []):
        for group in ('attributes', 'relations', 'codes'):
            for e in m[group]:
                counts['ontology_resolved' if e.get('status') in ('mapped', 'target_constant') else 'needs_attention'] += 1
        counts['target_properties_without_source'] += len(m['target_properties_without_source'])
    gaps = [k for k in ('mappings_needing_attention', 'source_schema_drift', 'target_schema_drift') if unresolved.get(k)]
    result['summary'] = {
        # resolved: the ontology knows both systems; partial: only one; unresolved: neither
        'status': 'resolved' if src.system and tgt.system else 'partial' if src.system or tgt.system else 'unresolved',
        # complete: every mapping the two systems share was resolved cleanly and neither script drifted
        'complete': bool(src.system and tgt.system) and not gaps,
        'concept_mappings': len(result.get('mappings', [])),
        **counts,
        'unresolved_items': {k: len(v) if isinstance(v, (list, dict)) else 1 for k, v in unresolved.items()},
        'how_to_use': ('Use every entry with resolved_by "ontology" as given; do not re-derive it. Only items under '
                       '"unresolved" may be inferred, and every inferred mapping must be labelled "llm-guess" with '
                       'its reasoning.')}
    result['unresolved'] = unresolved
    return result


def identify(onto, sql_text):
    sch = Schema(onto, sql_text, 'script')
    out = sch.summary(onto)
    if not sch.system:
        out['hints'] = name_hints(onto, sch)
    return out


def concepts_overview(onto):
    by_domain = defaultdict(list)
    for p, v in onto.properties.items():
        by_domain[v['domain']].append({'property': f'cc:{p}', 'kind': v['kind'], 'range': v['range'],
                                       **({'convention': v['convention']} if v['convention'] else {})})
    return {'conventions': onto.conventions,
            'concepts': [{'concept': f'cc:{c}', **v, 'properties': sorted(by_domain.get(c, []), key=lambda x: x['property'])}
                         for c, v in sorted(onto.classes.items())],
            'properties_without_domain': sorted(by_domain.get(None, []), key=lambda x: x['property']),
            'code_lists': {f'cc:{k}': list(v) for k, v in sorted(onto.code_lists.items())}}


def sources_overview(onto):
    return [{'system': s['code'], 'name': s['name'], 'schema_file': s['schema_file'], 'note': s['note'],
             'tables': {t: sorted(c) for t, c in sorted(s['tables'].items())},
             'concepts': sorted({cb['concept'] for cb in onto.concept_bindings.values() if cb['source'] == s['code']})}
            for s in onto.sources.values()]


# ---------------------------------------------------------------------
# Interfaces: HTTP server and command line
# ---------------------------------------------------------------------

def read_path(path):
    p = (ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if ROOT not in p.parents and p != ROOT:
        raise ValueError(f'path must be inside the repository: {path}')
    return p.read_text()


def sql_from(body, prefix):
    if body.get(f'{prefix}_sql'):
        return body[f'{prefix}_sql']
    if body.get(f'{prefix}_path'):
        return read_path(body[f'{prefix}_path'])
    raise ValueError(f'provide "{prefix}_sql" (script text) or "{prefix}_path" (file in the repository)')


def make_handler(onto):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, payload):
            data = json.dumps(payload, indent=2).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/health':
                self._send(200, {'status': 'ok', 'version': SERVICE_VERSION, 'triples': onto.triples,
                                 'sources': sorted(onto.sources), 'loaded_in_seconds': onto.load_seconds})
            elif self.path == '/sources':
                self._send(200, sources_overview(onto))
            elif self.path == '/concepts':
                self._send(200, concepts_overview(onto))
            else:
                self._send(404, {'error': f'unknown path {self.path}'})

        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length) or b'{}')
                if self.path == '/map':
                    self._send(200, map_schemas(onto, sql_from(body, 'source'), sql_from(body, 'target'),
                                                body.get('concepts')))
                elif self.path == '/identify':
                    sql = body.get('sql') or (read_path(body['path']) if body.get('path') else None)
                    if not sql:
                        raise ValueError('provide "sql" or "path"')
                    self._send(200, identify(onto, sql))
                else:
                    self._send(404, {'error': f'unknown path {self.path}'})
            except (ValueError, KeyError, OSError, json.JSONDecodeError) as e:
                self._send(400, {'error': str(e)})

        def log_message(self, fmt, *args):
            sys.stderr.write('[mapping-service] ' + fmt % args + '\n')
    return Handler


def main():
    ap = argparse.ArgumentParser(description='Ontology mapping service')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('serve', help='run the HTTP service')
    s.add_argument('--host', default='127.0.0.1')
    s.add_argument('--port', type=int, default=8765)
    m = sub.add_parser('map', help='map a source schema script to a target schema script')
    m.add_argument('--source', required=True)
    m.add_argument('--target', required=True)
    m.add_argument('--concept', action='append', help='limit to a core concept (repeatable), e.g. Order')
    i = sub.add_parser('identify', help='identify which bound system a schema script describes')
    i.add_argument('script')
    sub.add_parser('sources', help='list systems the ontology can resolve')
    sub.add_parser('concepts', help='list core concepts and properties')
    args = ap.parse_args()

    onto = Ontology()
    print(f'[mapping-service] loaded {onto.triples} triples in {onto.load_seconds}s', file=sys.stderr)
    if args.cmd == 'serve':
        if args.host not in ('127.0.0.1', 'localhost', '::1'):
            raise SystemExit('refusing to listen on a non-local address')
        server = ThreadingHTTPServer((args.host, args.port), make_handler(onto))
        print(f'[mapping-service] listening on http://{args.host}:{args.port}', file=sys.stderr)
        server.serve_forever()
    elif args.cmd == 'map':
        out = map_schemas(onto, read_path(args.source), read_path(args.target), args.concept)
    elif args.cmd == 'identify':
        out = identify(onto, read_path(args.script))
    elif args.cmd == 'sources':
        out = sources_overview(onto)
    else:
        out = concepts_overview(onto)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
