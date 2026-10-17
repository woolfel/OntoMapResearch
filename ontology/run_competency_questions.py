"""Run the competency questions against the two ontologies.

    python3 ontology/run_competency_questions.py [-v]

Loads commerce_core.ttl + commerce_binding.ttl with rdflib, runs every
SPARQL query in competency_questions.md and checks its expected outcome
('rows' or 'empty'). -v prints the answers.

It then proves the bindings are executable: for each source with a sample
database it assembles, purely from the binding ontology, the SQL that
extracts cc:Order instances in core form, runs it, and prints a row.
"""
import re
import sqlite3
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CC = Namespace('https://ontoresearch.example/commerce/core#')
CB = Namespace('https://ontoresearch.example/commerce/binding#')

PREFIXES = '''
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX cc:   <https://ontoresearch.example/commerce/core#>
PREFIX cb:   <https://ontoresearch.example/commerce/binding#>
'''


def load_questions():
    text = (HERE / 'competency_questions.md').read_text()
    pattern = re.compile(r'### (CQ-\d+): (.+?)\nExpect: (rows|empty)\n```sparql\n(.+?)```', re.S)
    return [(m[0], m[1], m[2], m[3]) for m in pattern.findall(text)]


def short(value):
    s = str(value)
    for ns, p in ((str(CC), 'cc:'), (str(CB), 'cb:')):
        s = s.replace(ns, p)
    return s if len(s) <= 70 else s[:67] + '...'


def extraction_sql(g, source, cls):
    """Assemble core-form extraction SQL for one class from the bindings alone."""
    q = PREFIXES + '''
    SELECT ?table ?filter ?property ?toCore WHERE {
      ?b cb:bindsClass ?cls ; cb:inSource/cb:sourceCode ?src ; cb:fromTable/cb:tableName ?table .
      OPTIONAL { ?b cb:rowFilter ?filter }
      ?pb cb:ofConceptBinding ?b ; cb:bindsProperty ?property ; cb:toCoreExpression ?toCore .
    } ORDER BY ?property'''
    rows = list(g.query(q, initBindings={'cls': cls, 'src': Literal(source)}))
    if not rows:
        return None
    table, flt = rows[0][0], rows[0][1]
    cols = ',\n       '.join(f'{r[3]} AS "{str(r[2]).split("#")[1]}"' for r in rows)
    return f'SELECT {cols}\nFROM "{table}"' + (f'\nWHERE {flt}' if flt else '')


def main():
    verbose = '-v' in sys.argv
    g = Graph()
    g.parse(HERE / 'commerce_core.ttl')
    g.parse(HERE / 'commerce_binding.ttl')
    print(f'loaded {len(g)} triples')

    failed = 0
    for cq, question, expect, query in load_questions():
        rows = list(g.query(PREFIXES + query))
        ok = (len(rows) > 0) == (expect == 'rows')
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {cq}  {len(rows):4} rows  {question}")
        if verbose or not ok:
            for r in rows[:15]:
                print('        ' + ' | '.join(short(v) for v in r))
            if len(rows) > 15:
                print(f'        ... {len(rows) - 15} more')

    print('\nExtraction SQL assembled from the bindings, run on the sample data:')
    for (source, db) in g.query(PREFIXES + 'SELECT ?code ?db WHERE { ?s cb:sourceCode ?code ; cb:sampleDatabase ?db }'):
        sql = extraction_sql(g, str(source), CC.Order)
        con = sqlite3.connect(ROOT / str(db))
        try:
            cur = con.execute(sql + ' LIMIT 1')
            row = dict(zip([d[0] for d in cur.description], cur.fetchone()))
            print(f'  {source}: OK {row}')
        except sqlite3.Error as e:
            failed += 1
            print(f'  {source}: FAIL {e}\n{sql}')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
