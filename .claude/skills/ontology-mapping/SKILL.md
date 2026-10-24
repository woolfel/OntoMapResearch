---
name: ontology-mapping
description: Look up how one database schema maps to another (tables, columns, value conversions, code values, joins) from the commerce ontologies before guessing. Use whenever a task maps, transforms, migrates, loads or compares data between two SQL schemas, e.g. writing ETL/ELT or dbt models, INSERT ... SELECT statements, field-mapping documents or data contracts between AcmeShopping, BigRiver, BobsUncle, the canonical model, or a new store's schema.
---

# Ontology mapping

The commerce ontologies already record how each known schema expresses each business concept. This
skill gets those mappings from `ontology/mapping_service.py` so you never re-derive what is already
decided, and tells you exactly which parts are left for you to infer.

## Contents

1. [Step 1: Get the mappings](#step-1-get-the-mappings): call the mapping tool from the command line or over HTTP
2. [Step 2: Read the result](#step-2-read-the-result): what each field and status in the JSON means
3. [Step 3: Apply the rules](#step-3-apply-the-rules): what you may use as given and what you may infer
4. [Step 4: When a schema is unknown](#step-4-when-a-schema-is-unknown): how to treat name-similarity hints
5. [Step 5: Report](#step-5-report): how to present the mapping plan with provenance
6. [Example (real output, abridged)](#example-real-output-abridged): a real response to learn the shape from

## Step 1: Get the mappings

Pass the **source** and **target** schema scripts (the `CREATE TABLE` SQL). Use whichever interface is
available:

**Command line** (from the repository root; prints JSON):

```bash
python ontology/mapping_service.py map --source big_river.sql --target canonical_ecommerce.sql
```

Add `--concept Order --concept OrderLine` to limit the answer to some core concepts (names without `cc:`).

**HTTP** (if the service is running: `python ontology/mapping_service.py serve`):

```
POST http://127.0.0.1:8765/map
{"source_path": "big_river.sql", "target_path": "canonical_ecommerce.sql", "concepts": ["Order"]}
```

Use `source_sql` / `target_sql` instead of `*_path` to send script text (e.g. a schema that is not a
file in the repository). Other endpoints: `POST /identify {"path": ...}` (which system is this
script?), `GET /sources`, `GET /concepts` (core concepts, properties and code lists), `GET /health`.

If neither interface works, stop and tell the user. Do not continue as if you had the mappings.

## Step 2: Read the result

| Field | Meaning | What you do |
|---|---|---|
| `source.identified_as`, `target.identified_as` | The known system each script matches (`similarity` 0-1), or `null` | `null` means the ontology does not know that schema; see step 4 |
| `source.schema_drift`, `exact_match` | Tables/columns that differ from what the ontology knows | Report any drift to the user |
| `summary.status` | `resolved` (both systems known), `partial` (one known), `unresolved` (neither) | Decides how much you may infer |
| `summary.complete` | `true` when nothing needs attention and nothing drifted | If `false`, read `unresolved` |
| `mappings[]` | One per core concept both systems provide: `source` / `target` table, `key`, `row_filter` | Rows matching `row_filter` are the instances; `key` identifies them |
| `mappings[].attributes[]` | Property-to-column mapping. `transform` is SQL over the **source** table that yields the value already in the **target** column's format | Use `transform` verbatim as the select expression for `target.column` |
| `mappings[].codes[]` | Code values (statuses, channels, ...). `values` is the full source to core to target table; `transform` is the `CASE` expression | Use `transform`; `unmapped_values` have no target code |
| `mappings[].relations[]` | Foreign keys (`foreign_key_columns`), join tables (`via_join_table`) or ISO-code lookups (`lookup_by`), each with an `instruction` | Follow `instruction`. Surrogate keys must be translated through a source-key to target-key map |
| `status` on an entry | `mapped`, `target_constant`, or a problem: `manual_conversion_required`, `target_derived`, `source_column_missing`, `target_column_missing`, `source_expression_invalid`, `partially_mapped` | Only `mapped` / `target_constant` are finished; for the rest, follow `instruction` |
| `caveat` on an entry | Free text (brands, countries, browse paths) that needs cleansing | Apply cleansing; the mapping itself is correct |
| `transform_validated` | `true` = the transform ran against the submitted source schema | A string is the error, so treat that entry as unresolved |
| `unresolved` | Everything the ontology could not decide (see below) | **Only these items may be inferred** |

`unresolved` can contain:

- `target_properties_without_source`: target fields with no source; decide a value, a default or NULL.
- `target_concepts_without_source` / `source_concepts_without_target`: whole concepts on one side only.
- `mappings_needing_attention`: entries whose `status` is not `mapped` (time zones, child tables, drift, unmapped codes).
- `unmapped_source_columns` / `unmapped_target_columns`: columns no binding uses.
- `source_schema_drift` / `target_schema_drift`: columns or tables the ontology has never seen.
- `source_schema_unknown` / `target_schema_unknown`: name-similarity **hints** for a schema the ontology does not know.

## Step 3: Apply the rules

1. Every entry with `"resolved_by": "ontology"` and status `mapped` is final. Copy its table, key,
   row filter and transform exactly. Do not "improve" it.
2. Infer only items in `unresolved` (and entries whose status is not `mapped`).
3. For each inferred item, record `"provenance": "llm-guess"`, a `reason`, and a `confidence`
   (`high` / `medium` / `low`). If it came from a name-similarity hint, cite the hint.
4. Never let a guess override an ontology mapping. If you believe the ontology is wrong, say so
   separately and propose a change to `ontology/binding_spec.py`.
5. `manual_conversion_required` (e.g. BobsUncle US/Central timestamps) must be converted outside
   SQLite. Never label local time as UTC.
6. `target_derived` means the target keeps that value somewhere else, e.g. canonical `product.upc` lives
   in the `product_identifier` table. Write it there (see the entry's `target.derived_from`).

## Step 4: When a schema is unknown

If `identified_as` is `null`, the result has `source_schema_unknown` or `target_schema_unknown`. It
contains `candidate_concepts` per table and `candidate_properties` / `format_hint` per column. For the
known side it also has `source_bindings` / `target_bindings`, which give how each property converts
to and from the core convention (`to_core`, `from_core_template`). Treat every hint as a guess:
confirm it from column names, comments and sample data, and label it `llm-guess`.

## Step 5: Report

When you present a mapping plan, keep provenance visible, for example:

```json
{
  "target": "customer_order.grand_total",
  "expression": "\"total_cents\"",
  "provenance": "ontology",
  "binding": "bobsuncle:Order__grandTotal"
}
```

```json
{
  "target": "customer_order.billing address",
  "expression": null,
  "provenance": "llm-guess",
  "confidence": "low",
  "reason": "BobsUncle carts record no billing address; left empty."
}
```

Tell the user how many mappings came from the ontology and how many are guesses, and list any schema
drift and `manual_conversion_required` items.

## Example (real output, abridged)

`map --source bobs_uncle.sql --target canonical_ecommerce.sql --concept Order`

```json
{
  "source": {"identified_as": "bobsuncle", "similarity": 1.0, "exact_match": true},
  "summary": {"status": "resolved", "complete": false, "ontology_resolved": 12, "needs_attention": 2},
  "mappings": [{
    "concept": "cc:Order",
    "source": {"table": "cart", "key": ["\"cart_no\""]},
    "target": {"table": "customer_order", "key": ["\"order_id\""]},
    "attributes": [
      {"property": "cc:grandTotal", "status": "mapped", "resolved_by": "ontology",
       "target": {"column": "grand_total", "format": "MoneyMinor"}, "transform": "\"total_cents\""},
      {"property": "cc:createdAt", "status": "manual_conversion_required",
       "target": {"column": "created_at"},
       "instruction": "... Convert from America/Chicago to UTC in the ETL tool ..."}
    ],
    "codes": [
      {"property": "cc:orderStatus", "target": {"column": "order_status"},
       "transform": "CASE \"cart_stat\" WHEN 'O' THEN 'CART' WHEN 'C' THEN 'PLACED' WHEN 'A' THEN 'ABANDONED' WHEN 'X' THEN 'CANCELLED' END"}
    ],
    "relations": [
      {"property": "cc:placedBy", "target": {"foreign_key_columns": ["customer_id"]},
       "instruction": "Set customer_order.customer_id to the target key of the related cc:Customer instance ..."}
    ]
  }],
  "unresolved": {
    "target_properties_without_source": [{"property": "cc:billingAddress", "target_table": "customer_order"}],
    "mappings_needing_attention": [{"property": "cc:createdAt", "status": "manual_conversion_required"}]
  }
}
```
