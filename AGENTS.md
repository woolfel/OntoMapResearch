# AGENTS.md

Instructions for AI agents working in this repository.

## What this repository is

Three e-commerce source schemas, a canonical integration model, and two OWL ontologies that describe
how they relate:

| Path | What it is |
|---|---|
| `acme_shopping.sql`, `big_river.sql`, `bobs_uncle.sql` | Source schemas (SQLite) |
| `canonical_ecommerce.sql` | Canonical target model (SQLite) |
| `acme_data/`, `big_river/`, `bobs_uncle/` | Sample data generators, `.sql` inserts and `.db` files |
| `dbt/` | dbt models loading AcmeShopping into the canonical model |
| `ontology/commerce_core.ttl` | Core ontology: store-independent concepts, properties, code lists, value conventions |
| `ontology/commerce_binding.ttl` | Binding ontology: where each concept/property lives in each schema, in which format |
| `ontology/mapping_service.py` | **Mapping tool.** Answers "how does schema A map to schema B?" from the ontologies |
| `ontology/competency_questions.md` | SPARQL questions the ontologies must answer |

## The rule: look mappings up, do not guess them

When a task involves mapping, transforming, migrating, comparing or loading data between two schemas
(writing ETL/ELT, dbt models, SQL `INSERT ... SELECT`, data contracts, field mappings):

1. **Call the mapping tool first** with the source and target schema scripts. Follow the
   `ontology-mapping` skill (`.claude/skills/ontology-mapping/SKILL.md`).
2. **Use every mapping the tool returns with `"resolved_by": "ontology"` exactly as given**: tables,
   keys, row filters, transforms, code tables, join instructions. Do not rewrite a transform because
   another looks more natural. The ontology's conversions are validated; your rewrite would not be.
3. **Infer only what the tool lists under `unresolved`** (and items whose `status` is not `mapped`).
   Everything else is already decided.
4. **Label every inferred mapping `"provenance": "llm-guess"`** with a one-line reason and a confidence.
   Never present a guess as an ontology mapping. If you used a name-similarity hint from the tool, say so.
5. **If the tool cannot be run, say so** and state that all mappings in your answer are guesses.

## When the ontology is wrong or incomplete

- Do not hand-edit `commerce_core.ttl` or `commerce_binding.ttl`; they are generated.
- Bindings are defined in `ontology/binding_spec.py` (per source) and concepts in `ontology/core_spec.py`.
  When a guessed mapping is confirmed by a human, propose adding it to `binding_spec.py` so it is
  resolved by the ontology next time. Then rebuild and re-run the checks (below).
- If the tool reports **schema drift** (`columns_unknown_to_ontology`, `source_column_missing`), the
  schema script changed after the bindings were written. Report it; do not silently map around it.

## Value conventions (the core ontology's, used by every transform)

- Money: decimal in major units in the core; each schema's own format (dollars, cents) is converted by
  the tool's transforms. The canonical model stores INTEGER minor units (cents).
- Percentages: fractions (0.15 = 15%). Timestamps: UTC. Weights: grams. Flags: booleans / 0-1.
- Codes (statuses, channels, ...): code-list individuals; the tool gives the full value table.
- BobsUncle timestamps are US/Central local time. SQLite cannot convert time zones: the tool marks these
  `manual_conversion_required`; convert them in the ETL tool, never by assuming UTC.

## Commands

All Python that needs rdflib runs from the project virtual environment `ontology/.venv`.

```bash
# mapping tool (one-off, JSON to stdout)
ontology/.venv/bin/python ontology/mapping_service.py map --source bobs_uncle.sql --target canonical_ecommerce.sql
# mapping tool (long-running HTTP service on 127.0.0.1:8765)
ontology/.venv/bin/python ontology/mapping_service.py serve
# rebuild + validate the ontologies after editing core_spec.py / binding_spec.py
python3 ontology/build_ontologies.py
# competency questions (must all PASS)
ontology/.venv/bin/python ontology/run_competency_questions.py
# diagrams
ontology/.venv/bin/python ontology/build_class_diagram.py
ontology/.venv/bin/python ontology/build_binding_diagram.py
```

## Data and safety

- All sample data is fictional (example.com emails, .example websites). Keep it that way.
- The mapping service only reads files inside this repository and only listens on localhost.
