"""Build commerce_core.ttl and commerce_binding.ttl, and validate them.

    python3 ontology/build_ontologies.py

Inputs : core_spec.py (concepts), binding_spec.py (per-source bindings),
         the four schema scripts and the sample databases.
Outputs: commerce_core.ttl, commerce_binding.ttl (next to this script).

Validation (the build fails on any error):
  * core: every domain, range, parent, sub-property and code is declared
  * bindings: every table/column exists; every key, filter and SQL
    expression is executed as `SELECT <expr> FROM <table> WHERE <filter>`
    against the real schema; property kinds and domains fit the bound
    class; relation targets fit the property range and have matching key
    arity; code mappings point at real code-list members
  * data: every code value that actually occurs in a sample database has
    a mapping (so no source value is silently dropped)
"""
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import core_spec as core            # noqa: E402
import binding_spec as bs           # noqa: E402

CORE_IRI = 'https://ontoresearch.example/commerce/core'
BIND_IRI = 'https://ontoresearch.example/commerce/binding'
BIND_NS = BIND_IRI + '#'
SRC_NS = BIND_IRI + '/{}#'

PREFIXES = {
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
    'owl': 'http://www.w3.org/2002/07/owl#',
    'xsd': 'http://www.w3.org/2001/XMLSchema#',
    'skos': 'http://www.w3.org/2004/02/skos/core#',
    'dcterms': 'http://purl.org/dc/terms/',
    'cc': core.NS,
}

errors = []


def error(msg):
    errors.append(msg)


def lit(text, lang=None, dtype=None):
    s = str(text).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    if lang:
        return f'"{s}"@{lang}'
    if dtype:
        return f'"{s}"^^{dtype}'
    return f'"{s}"'


def literal_for(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    return lit(value)


def prefix_block(extra=None):
    p = dict(PREFIXES, **(extra or {}))
    return '\n'.join(f'@prefix {k}: <{v}> .' for k, v in p.items()) + '\n'


def triples(subject, pairs):
    """Turtle block: subject p o ; p o ."""
    pairs = [(p, o) for p, o in pairs if o is not None]
    body = ' ;\n    '.join(f'{p} {o}' for p, o in pairs)
    return f'{subject}\n    {body} .\n'


# ---------------------------------------------------------------------
# Core ontology
# ---------------------------------------------------------------------

def ancestors(cls):
    out = []
    while cls:
        out.append(cls)
        cls = core.CLASSES.get(cls, core.DEFINED_CLASSES.get(cls, (None,)))[0]
    return out


def code_iri(cls, notation):
    return f'cc:{cls}_{notation}'


def validate_core():
    classes = set(core.CLASSES) | set(core.DEFINED_CLASSES)
    for name, (parent, *_rest) in core.CLASSES.items():
        if parent and parent not in classes:
            error(f'core: class {name} has unknown parent {parent}')
    for name, (dom, rng, _l, _d, _f, inv) in core.OBJECT_PROPERTIES.items():
        for c in (dom, rng):
            if c and c not in classes:
                error(f'core: object property {name} uses unknown class {c}')
        if inv and inv not in core.OBJECT_PROPERTIES:
            error(f'core: {name} inverse {inv} undeclared')
    for name, (dom, *_rest) in core.DATA_PROPERTIES.items():
        if dom and dom not in classes:
            error(f'core: data property {name} uses unknown class {dom}')
    for sup, subs in core.SUB_PROPERTIES.items():
        for s in [sup] + subs:
            if s not in core.DATA_PROPERTIES:
                error(f'core: sub-property {s} undeclared')
    for cls in core.CODE_LISTS:
        if core.CLASSES.get(cls, (None,))[0] != 'CodeList':
            error(f'core: code list {cls} must be a subclass of CodeList')
    for name, (_p, _l, _d, members) in core.DEFINED_CLASSES.items():
        for m in members:
            cls, notation = m.split('_', 1)
            if notation not in [c[0] for c in core.CODE_LISTS[cls]]:
                error(f'core: defined class {name} uses unknown code {m}')
    overlap = set(core.OBJECT_PROPERTIES) & set(core.DATA_PROPERTIES)
    if overlap:
        error(f'core: names used as both object and data property: {overlap}')


def build_core():
    out = [prefix_block(), '']
    out.append(triples(f'<{CORE_IRI}>', [
        ('a', 'owl:Ontology'),
        ('owl:versionIRI', f'<{CORE_IRI}/{core.VERSION}>'),
        ('owl:versionInfo', lit(core.VERSION)),
        ('dcterms:title', lit('Commerce core ontology', 'en')),
        ('dcterms:description', lit(
            'Store-independent concepts of online and in-store commerce: catalog, sellers, offers, '
            'inventory, customers, orders and carts, promotions, payments, shipments and returns. '
            'It has no knowledge of any database; commerce_binding.ttl maps these concepts to the '
            'tables and columns of specific stores.', 'en')),
        ('rdfs:comment', lit(core.__doc__.split('Value conventions')[1].strip()
                             .replace('(stated once here, referenced by every binding):', '').strip(), 'en')),
    ]))
    out.append('\n# ---- annotation properties ----\n')
    out.append(triples('cc:valueConvention', [
        ('a', 'owl:AnnotationProperty'), ('rdfs:label', lit('value convention', 'en')),
        ('skos:definition', lit('The unit or representation every value of this property uses, '
                                'whatever the source. Bindings convert into it.', 'en'))]))

    out.append('\n# ---- classes ----\n')
    for name, (parent, label, definition, alts) in core.CLASSES.items():
        pairs = [('a', 'owl:Class'), ('rdfs:label', lit(label, 'en')),
                 ('skos:definition', lit(definition, 'en'))]
        pairs += [('skos:altLabel', lit(a, 'en')) for a in alts]
        if parent:
            pairs.append(('rdfs:subClassOf', f'cc:{parent}'))
        if name in core.KEYS:
            pairs.append(('owl:hasKey', '( ' + ' '.join(f'cc:{k}' for k in core.KEYS[name]) + ' )'))
        out.append(triples(f'cc:{name}', pairs))
    out.append(f"[] a owl:AllDisjointClasses ;\n    owl:members ( {' '.join('cc:' + c for c in core.DISJOINT)} ) .\n")

    out.append('\n# ---- defined classes (classify orders by status) ----\n')
    for name, (parent, label, definition, members) in core.DEFINED_CLASSES.items():
        one_of = ' '.join(f'cc:{m}' for m in members)
        out.append(triples(f'cc:{name}', [
            ('a', 'owl:Class'), ('rdfs:label', lit(label, 'en')), ('skos:definition', lit(definition, 'en')),
            ('rdfs:subClassOf', f'cc:{parent}'),
            ('owl:equivalentClass', f'[ a owl:Class ; owl:intersectionOf ( cc:{parent} [ a owl:Restriction ; '
                                    f'owl:onProperty cc:orderStatus ; owl:someValuesFrom [ a owl:Class ; '
                                    f'owl:oneOf ( {one_of} ) ] ] ) ]')]))

    out.append('\n# ---- object properties ----\n')
    for name, (dom, rng, label, definition, functional, inv) in core.OBJECT_PROPERTIES.items():
        types = 'owl:ObjectProperty' + (' , owl:FunctionalProperty' if functional else '')
        out.append(triples(f'cc:{name}', [
            ('a', types), ('rdfs:label', lit(label, 'en')),
            ('skos:definition', lit(definition, 'en') if definition else None),
            ('rdfs:domain', f'cc:{dom}' if dom else None), ('rdfs:range', f'cc:{rng}'),
            ('owl:inverseOf', f'cc:{inv}' if inv else None)]))

    out.append('\n# ---- datatype properties ----\n')
    parent_of = {s: sup for sup, subs in core.SUB_PROPERTIES.items() for s in subs}
    for name, (dom, rng, label, definition, convention) in core.DATA_PROPERTIES.items():
        out.append(triples(f'cc:{name}', [
            ('a', 'owl:DatatypeProperty'), ('rdfs:label', lit(label, 'en')),
            ('skos:definition', lit(definition, 'en') if definition else None),
            ('rdfs:domain', f'cc:{dom}' if dom else None), ('rdfs:range', f'xsd:{rng}'),
            ('rdfs:subPropertyOf', f'cc:{parent_of[name]}' if name in parent_of else None),
            ('cc:valueConvention', lit(convention, 'en') if convention else None)]))

    out.append('\n# ---- code lists ----\n')
    for cls, codes in core.CODE_LISTS.items():
        members = ' '.join(code_iri(cls, c[0]) for c in codes)
        out.append(f'cc:{cls} owl:equivalentClass [ a owl:Class ; owl:oneOf ( {members} ) ] .\n')
        out.append(f'[] a owl:AllDifferent ;\n    owl:distinctMembers ( {members} ) .\n')
        for notation, label, definition in codes:
            out.append(triples(code_iri(cls, notation), [
                ('a', f'owl:NamedIndividual , cc:{cls}'), ('rdfs:label', lit(label, 'en')),
                ('skos:notation', lit(notation)),
                ('skos:definition', lit(definition, 'en') if definition else None)]))
    return '\n'.join(out)


# ---------------------------------------------------------------------
# Binding ontology
# ---------------------------------------------------------------------

BINDING_VOCAB = '''
<{iri}>
    a owl:Ontology ;
    owl:imports <{core}> ;
    owl:versionInfo "1.0.0" ;
    dcterms:title "Commerce binding ontology"@en ;
    dcterms:description """Maps the store-independent concepts of the commerce core ontology onto the
tables and columns of specific source databases. The vocabulary (cb:) is general purpose; each
source system is described by instances in its own namespace, so adding a store means adding
bindings, never changing the core concepts. Every SQL expression is SQLite, written relative to
the binding's table: SELECT <expression> FROM <table> WHERE <rowFilter>."""@en .

cb:SourceSystem a owl:Class ; rdfs:label "Source system"@en ;
    skos:definition "A database whose data is described by bindings."@en .
cb:Table a owl:Class ; rdfs:label "Table"@en .
cb:Column a owl:Class ; rdfs:label "Column"@en .
cb:ValueFormat a owl:Class ; rdfs:label "Value format"@en ;
    skos:definition "How a source stores a kind of value, and how to convert it to the core convention."@en .
cb:ConceptBinding a owl:Class ; rdfs:label "Concept binding"@en ;
    skos:definition "Rows of a table (identified by key expressions and an optional row filter) that are instances of a core class."@en .
cb:PropertyBinding a owl:Class ; rdfs:label "Property binding"@en ;
    skos:definition "How one core property is obtained for the instances of a concept binding."@en .
cb:AttributeBinding a owl:Class ; rdfs:subClassOf cb:PropertyBinding ; rdfs:label "Attribute binding"@en ;
    skos:definition "Binds a datatype property to a column, expression or constant."@en .
cb:RelationBinding a owl:Class ; rdfs:subClassOf cb:PropertyBinding ; rdfs:label "Relation binding"@en ;
    skos:definition "Binds an object property to another concept binding (join), a many-to-many table, or a lookup by natural key."@en .
cb:ValueBinding a owl:Class ; rdfs:subClassOf cb:PropertyBinding ; rdfs:label "Value binding"@en ;
    skos:definition "Binds an object property whose range is a code list, mapping source codes to code-list individuals."@en .
cb:ValueMap a owl:Class ; rdfs:label "Value map"@en ;
    skos:definition "One source code and the code-list individual it means."@en .

cb:inSource a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:range cb:SourceSystem ; rdfs:label "in source"@en .
cb:inTable a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:Column ; rdfs:range cb:Table ; rdfs:label "in table"@en .
cb:bindsClass a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:ConceptBinding ; rdfs:range owl:Class ; rdfs:label "binds class"@en .
cb:fromTable a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:ConceptBinding ; rdfs:range cb:Table ; rdfs:label "from table"@en .
cb:keyColumn a owl:ObjectProperty ; rdfs:domain cb:ConceptBinding ; rdfs:range cb:Column ; rdfs:label "key column"@en .
cb:ofConceptBinding a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:PropertyBinding ; rdfs:range cb:ConceptBinding ; rdfs:label "of concept binding"@en .
cb:bindsProperty a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:PropertyBinding ; rdfs:label "binds property"@en .
cb:sourceColumn a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:range cb:Column ; rdfs:label "source column"@en ;
    skos:definition "The single column a value is read from (absent when an expression or constant is used)."@en .
cb:usesColumn a owl:ObjectProperty ; rdfs:range cb:Column ; rdfs:label "uses column"@en ;
    skos:definition "Every column a binding reads, including inside expressions, filters and keys."@en .
cb:valueFormat a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:range cb:ValueFormat ; rdfs:label "value format"@en .
cb:targetBinding a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:RelationBinding ; rdfs:range cb:ConceptBinding ; rdfs:label "target binding"@en .
cb:throughTable a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:RelationBinding ; rdfs:range cb:Table ; rdfs:label "through table"@en .
cb:matchOnProperty a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:RelationBinding ; rdfs:range owl:DatatypeProperty ; rdfs:label "match on property"@en ;
    skos:definition "The target is the instance of the property's range whose value of this property equals the source value (lookup by natural key)."@en .
cb:valueMap a owl:ObjectProperty ; rdfs:domain cb:ValueBinding ; rdfs:range cb:ValueMap ; rdfs:label "value map"@en .
cb:targetIndividual a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:ValueMap ; rdfs:label "target individual"@en .
cb:constantIndividual a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain cb:ValueBinding ; rdfs:label "constant individual"@en ;
    skos:definition "Every instance has this code (the source does not store it)."@en .

cb:sourceCode a owl:DatatypeProperty ; rdfs:domain cb:SourceSystem ; rdfs:range xsd:string ; rdfs:label "source code"@en .
cb:dialect a owl:DatatypeProperty ; rdfs:domain cb:SourceSystem ; rdfs:range xsd:string ; rdfs:label "SQL dialect"@en .
cb:schemaFile a owl:DatatypeProperty ; rdfs:domain cb:SourceSystem ; rdfs:range xsd:string ; rdfs:label "schema file"@en .
cb:sampleDatabase a owl:DatatypeProperty ; rdfs:domain cb:SourceSystem ; rdfs:range xsd:string ; rdfs:label "sample database"@en .
cb:tableName a owl:DatatypeProperty ; rdfs:domain cb:Table ; rdfs:range xsd:string ; rdfs:label "table name"@en .
cb:columnName a owl:DatatypeProperty ; rdfs:domain cb:Column ; rdfs:range xsd:string ; rdfs:label "column name"@en .
cb:declaredType a owl:DatatypeProperty ; rdfs:domain cb:Column ; rdfs:range xsd:string ; rdfs:label "declared type"@en .
cb:isNullable a owl:DatatypeProperty ; rdfs:domain cb:Column ; rdfs:range xsd:boolean ; rdfs:label "is nullable"@en .
cb:isPrimaryKey a owl:DatatypeProperty ; rdfs:domain cb:Column ; rdfs:range xsd:boolean ; rdfs:label "is primary key"@en .
cb:keyExpressions a owl:ObjectProperty ; rdfs:domain cb:ConceptBinding ; rdfs:range rdf:List ; rdfs:label "key expressions"@en ;
    skos:definition "Ordered list of SQL expressions that together identify one instance. Relations match these positionally."@en .
cb:rowFilter a owl:DatatypeProperty ; rdfs:domain cb:ConceptBinding ; rdfs:range xsd:string ; rdfs:label "row filter"@en ;
    skos:definition "SQL condition selecting which rows are instances (absent = every row)."@en .
cb:isVirtual a owl:DatatypeProperty ; rdfs:domain cb:ConceptBinding ; rdfs:range xsd:boolean ; rdfs:label "is virtual"@en ;
    skos:definition "True when the source has no table for the concept and the binding describes one implied instance."@en .
cb:sourceExpression a owl:DatatypeProperty ; rdfs:domain cb:PropertyBinding ; rdfs:range xsd:string ; rdfs:label "source expression"@en ;
    skos:definition "SQL expression that produces the raw source value (a column name when a single column is read)."@en .
cb:constantValue a owl:DatatypeProperty ; rdfs:domain cb:PropertyBinding ; rdfs:range rdfs:Literal ; rdfs:label "constant value"@en .
cb:toCoreExpression a owl:DatatypeProperty ; rdfs:domain cb:AttributeBinding ; rdfs:range xsd:string ; rdfs:label "to-core expression"@en ;
    skos:definition "SQL expression that yields the value already converted to the core value convention."@en .
cb:joinExpressions a owl:ObjectProperty ; rdfs:domain cb:RelationBinding ; rdfs:range rdf:List ; rdfs:label "join expressions"@en ;
    skos:definition "Ordered SQL expressions on this binding's table, matched positionally to the target binding's key expressions."@en .
cb:throughSubjectColumns a owl:ObjectProperty ; rdfs:range rdf:List ; rdfs:label "through-table subject columns"@en .
cb:throughObjectColumns a owl:ObjectProperty ; rdfs:range rdf:List ; rdfs:label "through-table object columns"@en .
cb:throughFilter a owl:DatatypeProperty ; rdfs:range xsd:string ; rdfs:label "through-table filter"@en .
cb:matchOnNotation a owl:DatatypeProperty ; rdfs:domain cb:ValueBinding ; rdfs:range xsd:boolean ; rdfs:label "match on notation"@en ;
    skos:definition "Source codes equal the skos:notation of the code-list individuals."@en .
cb:sourceValue a owl:DatatypeProperty ; rdfs:domain cb:ValueMap ; rdfs:range xsd:string ; rdfs:label "source value"@en .
cb:formatDescription a owl:DatatypeProperty ; rdfs:domain cb:ValueFormat ; rdfs:range xsd:string ; rdfs:label "format description"@en .
cb:conversionTemplate a owl:DatatypeProperty ; rdfs:domain cb:ValueFormat ; rdfs:range xsd:string ; rdfs:label "conversion template"@en ;
    skos:definition "SQLite expression converting {{v}} into the core convention."@en .
cb:fromCoreTemplate a owl:DatatypeProperty ; rdfs:domain cb:ValueFormat ; rdfs:range xsd:string ; rdfs:label "from-core template"@en ;
    skos:definition "SQLite expression converting a core-convention value {{v}} into this format (the inverse of cb:conversionTemplate). Composing a source format's conversionTemplate with a target format's fromCoreTemplate maps a value between two stores."@en .
'''


class SchemaInfo:
    def __init__(self, schema_path):
        self.con = sqlite3.connect(':memory:')
        self.con.executescript(Path(schema_path).read_text())
        self.tables = {}
        for (t,) in self.con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                     "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            self.tables[t] = [dict(name=r[1], type=r[2], notnull=bool(r[3]), pk=bool(r[5]))
                              for r in self.con.execute(f'PRAGMA table_info("{t}")')]

    def columns(self, table):
        return [c['name'] for c in self.tables[table]]

    def check_sql(self, table, expr, where=None, what=''):
        sql = f'SELECT {expr} FROM "{table}"' + (f' WHERE {where}' if where else '') + ' LIMIT 0'
        try:
            self.con.execute(sql)
        except sqlite3.Error as e:
            error(f'{what}: {e} in: {sql}')


def expr_of(value):
    """(sql text, format, column name or None) for a C / E / str source."""
    if isinstance(value, bs.C):
        return f'"{value.column}"', value.fmt, value.column
    if isinstance(value, bs.E):
        return value.sql, value.fmt, None
    if isinstance(value, str):
        return f'"{value}"', 'Text', value
    raise TypeError(value)


def is_subclass(cls, of):
    return of in ancestors(cls)


def used_columns(sql, schema, table):
    """Columns referenced in an expression (binding table + tables named in it)."""
    found = set()
    words = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', sql))
    for t, cols in schema.tables.items():
        if t != table and t not in words:
            continue
        for c in cols:
            if c['name'] in words:
                found.add((t, c['name']))
    return found


def iri_local(text):
    return re.sub(r'[^A-Za-z0-9_]', '_', text)


def build_binding():
    out = [prefix_block({'cb': BIND_NS, **{s.code: SRC_NS.format(s.code) for s in bs.SOURCES}}),
           BINDING_VOCAB.format(iri=BIND_IRI, core=CORE_IRI)]

    out.append('\n# ---- value formats ----\n')
    for name, (label, desc, template, from_core) in bs.FORMATS.items():
        out.append(triples(f'cb:{name}', [('a', 'owl:NamedIndividual , cb:ValueFormat'),
                                          ('rdfs:label', lit(label, 'en')),
                                          ('cb:formatDescription', lit(desc, 'en')),
                                          ('cb:conversionTemplate', lit(template)),
                                          ('cb:fromCoreTemplate', lit(from_core))]))

    stats = []
    for src in bs.SOURCES:
        p = src.code
        schema = SchemaInfo(ROOT / src.schema)
        sample = sqlite3.connect(ROOT / src.sample_db) if src.sample_db and (ROOT / src.sample_db).exists() else None
        out.append(f'\n# =====================================================================\n'
                   f'# Source: {src.name}\n'
                   f'# =====================================================================\n')
        out.append(triples(f'{p}:source', [
            ('a', 'owl:NamedIndividual , cb:SourceSystem'), ('rdfs:label', lit(src.name, 'en')),
            ('cb:sourceCode', lit(p)), ('cb:dialect', lit('SQLite 3')), ('cb:schemaFile', lit(src.schema)),
            ('cb:sampleDatabase', lit(src.sample_db) if src.sample_db else None),
            ('rdfs:comment', lit(src.note, 'en'))]))

        def col_iri(t, c):
            return f'{p}:column_{iri_local(t)}__{iri_local(c)}'

        for t, cols in schema.tables.items():
            out.append(triples(f'{p}:table_{iri_local(t)}', [
                ('a', 'owl:NamedIndividual , cb:Table'), ('cb:tableName', lit(t)), ('cb:inSource', f'{p}:source')]))
            for c in cols:
                out.append(triples(col_iri(t, c['name']), [
                    ('a', 'owl:NamedIndividual , cb:Column'), ('cb:columnName', lit(c['name'])),
                    ('cb:inTable', f'{p}:table_{iri_local(t)}'), ('cb:declaredType', lit(c['type'])),
                    ('cb:isNullable', literal_for(not c['notnull'] and not c['pk'])),
                    ('cb:isPrimaryKey', literal_for(c['pk']))]))

        by_id = {}
        for cb in src.concepts:
            if cb.id in by_id:
                error(f'{p}: duplicate concept binding id {cb.id}')
            by_id[cb.id] = cb

        for cb in src.concepts:
            where = f'{p}:{cb.cls if cb.id == cb.cls else cb.id}'
            subj = f'{p}:{iri_local(cb.id)}'
            if cb.cls not in core.CLASSES:
                error(f'{where}: unknown class {cb.cls}')
                continue
            table = cb.table
            if table is not None and table not in schema.tables:
                error(f'{where}: unknown table {table}')
                continue
            uses = set()

            def track(sql_text):
                if table:
                    uses.update(used_columns(sql_text, schema, table))

            def check(sql_text, what):
                if table:
                    schema.check_sql(table, sql_text, cb.filter, f'{where} {what}')
                    track(sql_text)

            def check_column(col, what):
                if table and col not in schema.columns(table):
                    error(f'{where} {what}: column {table}.{col} does not exist')

            key_exprs = []
            for k in cb.key:
                if isinstance(k, bs.K):
                    key_exprs.append(lit(k.value) if not isinstance(k.value, str) else f"'{k.value}'")
                    continue
                sql_text, _f, col = expr_of(k)
                if col:
                    check_column(col, 'key')
                check(sql_text, 'key')
                key_exprs.append(sql_text)
            if cb.filter:
                check('1', 'row filter')
                track(cb.filter)

            pairs = [('a', 'owl:NamedIndividual , cb:ConceptBinding'), ('cb:inSource', f'{p}:source'),
                     ('cb:bindsClass', f'cc:{cb.cls}'),
                     ('rdfs:label', lit(f'{src.name} {cb.id}', 'en')),
                     ('cb:keyExpressions', '( ' + ' '.join(lit(k) for k in key_exprs) + ' )')]
            if table:
                pairs.append(('cb:fromTable', f'{p}:table_{iri_local(table)}'))
                for k in cb.key:
                    if isinstance(k, (str, bs.C)):
                        pairs.append(('cb:keyColumn', col_iri(table, k if isinstance(k, str) else k.column)))
            else:
                pairs.append(('cb:isVirtual', 'true'))
            pairs.append(('cb:rowFilter', lit(cb.filter) if cb.filter else None))
            pairs.append(('rdfs:comment', lit(cb.note, 'en') if cb.note else None))
            concept_block_index = len(out)
            out.append(None)  # placeholder, filled once uses are known

            # attributes
            for prop, value in cb.attrs.items():
                b = f'{p}:{iri_local(cb.id)}__{prop}'
                spec = core.DATA_PROPERTIES.get(prop)
                if not spec:
                    error(f'{where}: {prop} is not a core datatype property')
                    continue
                if spec[0] and not is_subclass(cb.cls, spec[0]):
                    error(f'{where}: {prop} has domain {spec[0]}, not {cb.cls}')
                bp = [('a', 'owl:NamedIndividual , cb:AttributeBinding'), ('cb:ofConceptBinding', subj),
                      ('cb:bindsProperty', f'cc:{prop}')]
                if isinstance(value, bs.K):
                    bp.append(('cb:constantValue', literal_for(value.value)))
                else:
                    sql_text, fmt, col = expr_of(value)
                    if fmt not in bs.FORMATS:
                        error(f'{where}.{prop}: unknown format {fmt}')
                        continue
                    if col:
                        check_column(col, prop)
                        bp.append(('cb:sourceColumn', col_iri(table, col)))
                    check(sql_text, prop)
                    core_expr = bs.FORMATS[fmt][2].replace('{v}', sql_text)
                    check(core_expr if not core_expr.startswith('/*') else sql_text, f'{prop} conversion')
                    bp += [('cb:sourceExpression', lit(col or sql_text)), ('cb:valueFormat', f'cb:{fmt}'),
                           ('cb:toCoreExpression', lit(core_expr))]
                    for t, c in sorted(used_columns(sql_text, schema, table)):
                        bp.append(('cb:usesColumn', col_iri(t, c)))
                out.append(triples(b, bp))

            # relations
            for prop, value in cb.rels.items():
                b = f'{p}:{iri_local(cb.id)}__{prop}'
                spec = core.OBJECT_PROPERTIES.get(prop)
                if not spec:
                    error(f'{where}: {prop} is not a core object property')
                    continue
                dom, rng = spec[0], spec[1]
                if dom and not is_subclass(cb.cls, dom):
                    error(f'{where}: {prop} has domain {dom}, not {cb.cls}')
                bp = [('a', 'owl:NamedIndividual , cb:RelationBinding'), ('cb:ofConceptBinding', subj),
                      ('cb:bindsProperty', f'cc:{prop}')]
                if isinstance(value, bs.Rel):
                    target = by_id.get(value.target)
                    if not target:
                        error(f'{where}.{prop}: unknown target binding {value.target}')
                        continue
                    if not is_subclass(target.cls, rng):
                        error(f'{where}.{prop}: target {target.cls} is not a {rng}')
                    if len(value.via) != len(target.key):
                        error(f'{where}.{prop}: {len(value.via)} join expressions for a '
                              f'{len(target.key)}-part key of {target.id}')
                    joins = []
                    for v in value.via:
                        if isinstance(v, bs.K):
                            joins.append(f"'{v.value}'")
                            continue
                        sql_text, _f, col = expr_of(v)
                        if col:
                            check_column(col, prop)
                        check(sql_text, prop)
                        joins.append(sql_text)
                        for t, c in (sorted(used_columns(sql_text, schema, table)) if table else []):
                            bp.append(('cb:usesColumn', col_iri(t, c)))
                    bp += [('cb:targetBinding', f'{p}:{iri_local(target.id)}'),
                           ('cb:joinExpressions', '( ' + ' '.join(lit(j) for j in joins) + ' )')]
                elif isinstance(value, bs.Ref):
                    mspec = core.DATA_PROPERTIES.get(value.match_on)
                    if not mspec or mspec[0] != rng:
                        error(f'{where}.{prop}: {value.match_on} is not a key property of {rng}')
                    bp.append(('cb:matchOnProperty', f'cc:{value.match_on}'))
                    if isinstance(value.value, bs.K):
                        bp.append(('cb:constantValue', literal_for(value.value.value)))
                    else:
                        sql_text, fmt, col = expr_of(value.value)
                        if col:
                            check_column(col, prop)
                            bp.append(('cb:sourceColumn', col_iri(table, col)))
                        check(sql_text, prop)
                        bp += [('cb:sourceExpression', lit(col or sql_text)), ('cb:valueFormat', f'cb:{fmt}')]
                        for t, c in sorted(used_columns(sql_text, schema, table)):
                            bp.append(('cb:usesColumn', col_iri(t, c)))
                elif isinstance(value, bs.Through):
                    target = by_id.get(value.target)
                    if value.table not in schema.tables:
                        error(f'{where}.{prop}: unknown through table {value.table}')
                        continue
                    if not target or not is_subclass(target.cls, rng):
                        error(f'{where}.{prop}: bad through target {value.target}')
                        continue
                    for c in value.subject_columns + value.object_columns:
                        if c not in schema.columns(value.table):
                            error(f'{where}.{prop}: column {value.table}.{c} does not exist')
                    if value.filter:
                        schema.check_sql(value.table, '1', value.filter, f'{where}.{prop} through filter')
                    if len(value.subject_columns) != len(cb.key) or len(value.object_columns) != len(target.key):
                        error(f'{where}.{prop}: through-table key arity mismatch')
                    bp += [('cb:targetBinding', f'{p}:{iri_local(target.id)}'),
                           ('cb:throughTable', f'{p}:table_{iri_local(value.table)}'),
                           ('cb:throughSubjectColumns', '( ' + ' '.join(lit(c) for c in value.subject_columns) + ' )'),
                           ('cb:throughObjectColumns', '( ' + ' '.join(lit(c) for c in value.object_columns) + ' )'),
                           ('cb:throughFilter', lit(value.filter) if value.filter else None)]
                    bp += [('cb:usesColumn', col_iri(value.table, c))
                           for c in value.subject_columns + value.object_columns]
                else:
                    error(f'{where}.{prop}: unsupported relation {value!r}')
                    continue
                out.append(triples(b, bp))

            # code values
            for prop, value in cb.values.items():
                b = f'{p}:{iri_local(cb.id)}__{prop}'
                spec = core.OBJECT_PROPERTIES.get(prop)
                if not spec or spec[1] not in core.CODE_LISTS:
                    error(f'{where}: {prop} is not a code-list property')
                    continue
                if spec[0] and not is_subclass(cb.cls, spec[0]):
                    error(f'{where}: {prop} has domain {spec[0]}, not {cb.cls}')
                code_cls = spec[1]
                notations = [c[0] for c in core.CODE_LISTS[code_cls]]
                bp = [('a', 'owl:NamedIndividual , cb:ValueBinding'), ('cb:ofConceptBinding', subj),
                      ('cb:bindsProperty', f'cc:{prop}')]
                if isinstance(value.value, bs.K):
                    if value.value.value not in notations:
                        error(f'{where}.{prop}: {value.value.value} is not a {code_cls}')
                    bp.append(('cb:constantIndividual', code_iri(code_cls, value.value.value)))
                    out.append(triples(b, bp))
                    continue
                sql_text, fmt, col = expr_of(value.value)
                if col:
                    check_column(col, prop)
                    bp.append(('cb:sourceColumn', col_iri(table, col)))
                check(sql_text, prop)
                bp += [('cb:sourceExpression', lit(col or sql_text)), ('cb:valueFormat', 'cb:Code')]
                for t, c in sorted(used_columns(sql_text, schema, table)):
                    bp.append(('cb:usesColumn', col_iri(t, c)))
                if value.mapping == 'notation':
                    bp.append(('cb:matchOnNotation', 'true'))
                    allowed = set(notations)
                else:
                    for sv, notation in value.mapping.items():
                        if notation not in notations:
                            error(f'{where}.{prop}: {notation} is not a {code_cls}')
                    maps = ' , '.join(f'[ a cb:ValueMap ; cb:sourceValue {lit(sv)} ; '
                                      f'cb:targetIndividual {code_iri(code_cls, n)} ]'
                                      for sv, n in value.mapping.items())
                    bp.append(('cb:valueMap', maps))
                    allowed = set(value.mapping)
                if sample:                                 # every value in the data must map
                    sql = f'SELECT DISTINCT {sql_text} FROM "{table}"' + (f' WHERE {cb.filter}' if cb.filter else '')
                    seen = {r[0] for r in sample.execute(sql) if r[0] is not None}
                    unmapped = seen - allowed
                    if unmapped:
                        error(f'{where}.{prop}: sample data has unmapped codes {sorted(unmapped)}')
                out.append(triples(b, bp))

            pairs += [('cb:usesColumn', col_iri(t, c)) for t, c in sorted(uses)]
            out[concept_block_index] = triples(subj, pairs)

            if sample and table:
                n = sample.execute(f'SELECT count(*) FROM (SELECT DISTINCT {", ".join(key_exprs)} FROM "{table}"'
                                   + (f' WHERE {cb.filter}' if cb.filter else '') + ')').fetchone()[0]
                stats.append((p, cb.id, cb.cls, n))
    return '\n'.join(out), stats


def main():
    validate_core()
    core_ttl = build_core()
    binding_ttl, stats = build_binding()
    if errors:
        print(f'{len(errors)} validation error(s):')
        for e in errors:
            print('  -', e)
        sys.exit(1)
    (HERE / 'commerce_core.ttl').write_text(core_ttl)
    (HERE / 'commerce_binding.ttl').write_text(binding_ttl)
    n_bind = sum(len(c.attrs) + len(c.rels) + len(c.values) for s in bs.SOURCES for c in s.concepts)
    print(f'commerce_core.ttl: {len(core.CLASSES) + len(core.DEFINED_CLASSES)} classes, '
          f'{len(core.OBJECT_PROPERTIES)} object properties, {len(core.DATA_PROPERTIES)} datatype properties, '
          f'{sum(len(v) for v in core.CODE_LISTS.values())} code-list members')
    print(f'commerce_binding.ttl: {len(bs.SOURCES)} sources, '
          f'{sum(len(s.concepts) for s in bs.SOURCES)} concept bindings, {n_bind} property bindings')
    print('instances per concept binding in the sample data:')
    for p, cid, cls, n in stats:
        print(f'  {p:10} {cid:22} {cls:22} {n:6}')


if __name__ == '__main__':
    main()
