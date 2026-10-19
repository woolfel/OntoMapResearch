# REVIEW.md

How to review a change to a data transformation, such as the dbt models in `dbt/` that load a source
schema into the canonical model. A transformation is approved only when all three steps below pass,
and the evidence for each step is recorded in the review (pull request or review notes).

The examples use the AcmeShopping models (`acme_shopping.sql` → `canonical_ecommerce.sql`). For
another source, swap in its schema script, sample database and `source_system_id`.

## Prerequisites

- **Python environment:** activate the project environment (`conda activate ontomap`, or a virtual
  environment built from `requirements.txt`). It provides `dbt-core`, `dbt-sqlite` and `rdflib`.
- **dbt project files:** dbt needs a `dbt_project.yml` and a `profiles.yml` to parse or run the
  models. They are not in the repository yet. The profile must attach the canonical database as
  `main` and the source database as `acme`, as described in `dbt/sources.yml`.
- **Disposable databases:** test against copies only. Build a fresh canonical database from
  `canonical_ecommerce.sql`, and copy the sample source database (e.g. `acme_data/acme.db`) into a
  scratch directory. Never point a review run at a database someone depends on.

## 1. The transformation SQL is syntactically valid

The models must render and compile, and the compiled SQL must be valid for the target engine
(SQLite).

1. **Parse and compile the project.** Both must finish without errors or warnings about unresolved
   `ref()` or `source()` calls:

   ```bash
   dbt parse
   ```

   ```bash
   dbt compile
   ```

2. **Check the compiled SQL against the real schemas.** `dbt compile` writes rendered SQL to
   `target/compiled/`. Run each statement with `EXPLAIN` against an empty database built from the
   canonical schema with the source schema attached. `EXPLAIN` prepares the statement without
   running it, so a misspelled column or table fails here.

3. **Check the model configuration:**
   - [ ] `materialized='incremental'` with an `incremental_strategy` and a `unique_key` that is the
     target table's key
   - [ ] `full_refresh=false`, so `--full-refresh` can never drop a canonical table and its constraints
   - [ ] `alias` matches the canonical table name (`product`, `customer_order`, `order_item`, ...)
   - [ ] every `source()` is declared in `dbt/sources.yml`, and dependencies use `ref()` or a
     `-- depends_on:` comment
   - [ ] no syntax from another dialect (`::` casts, `ILIKE`, `DATE_TRUNC`, PostgreSQL `INTERVAL`)

**Evidence to record:** `dbt compile` output, and the `EXPLAIN` result for each model.

## 2. The transformation is correct

The SQL must produce the right values. Correctness is checked against the ontology, not against
memory or column names.

1. **Get the reference mapping** from the mapping tool (see `AGENTS.md` and the `ontology-mapping` skill):

   ```bash
   python ontology/mapping_service.py map --source acme_shopping.sql --target canonical_ecommerce.sql
   ```

2. **Compare every target column the model writes** against the tool's output:
   - [ ] **Ontology mappings used as given:** for every entry with `"resolved_by": "ontology"` and
     status `mapped`, the model uses the tool's `transform` (or an equivalent expression the
     reviewer has confirmed), with the same source table, key and row filter.
   - [ ] **Value conventions:** money is converted to the target's unit (canonical: INTEGER cents),
     percentages are fractions, timestamps are ISO-8601 UTC, weights are grams.
   - [ ] **Code values** match the tool's `values` table for every status, channel or type column,
     and no source code is left unmapped.
   - [ ] **Relationships:** foreign keys are resolved through source keys (for example
     `source_key_map`), never copied from source ids. Join tables (`order_address`,
     `product_warranty`, ...) are filled as the tool's `instruction` says.
   - [ ] **Guesses are labelled:** every column set from an item under `unresolved` is labelled
     `llm-guess` with a reason, in the model comments or the review notes, and a reviewer agrees
     with each one.
   - [ ] **No unflagged problems:** nothing marked `manual_conversion_required` (for example
     BobsUncle US/Central timestamps) is loaded as if it were UTC, and any schema drift the tool
     reports has been explained.

3. **Check the load logic:**
   - [ ] **Grain:** one target row per source instance. Joins do not multiply rows, and row filters
     match the binding (e.g. BobsUncle lines with `qty > 0`).
   - [ ] **Lineage:** `source_system_id`, the source key column (`source_order_key`,
     `source_line_key`, ...) and `loaded_at` are set on transactional rows.
   - [ ] **Idempotent:** re-running updates existing rows (same surrogate ids) instead of inserting
     duplicates.
   - [ ] **Merged master data does not overwrite other sources:** brand and product columns the
     source does not have keep their existing values.

**Evidence to record:** the mapping tool's `summary`, plus a table with one row per target column
giving the source expression and its provenance (`ontology` or `llm-guess`).

## 3. A test transform was executed to validate

Run the models on sample data and prove the result with queries. Passing steps 1 and 2 on paper is
not enough.

1. **Run the load twice** against the disposable databases. Both runs must succeed:

   ```bash
   dbt run
   ```

   ```bash
   dbt run
   ```

2. **Run the validation queries** on the canonical database, with the source attached as `acme`.
   AcmeShopping is `source_system_id = 1`.

   ```sql
   -- row counts reconcile (expect equal values in each pair)
   SELECT (SELECT count(*) FROM acme."Order")                                AS source_orders,
          (SELECT count(*) FROM customer_order WHERE source_system_id = 1)  AS loaded_orders,
          (SELECT count(*) FROM acme."OrderItem")                           AS source_lines,
          (SELECT count(*) FROM order_item WHERE source_system_id = 1)      AS loaded_lines;

   -- money reconciles to the cent (expect equal)
   SELECT (SELECT sum(CAST(round("GrandTotal" * 100) AS INTEGER)) FROM acme."Order") AS source_cents,
          (SELECT sum(grand_total) FROM customer_order WHERE source_system_id = 1)  AS loaded_cents;

   -- every source status landed on the expected canonical code
   SELECT o."OrderStatus", c.order_status, count(*) AS n
   FROM acme."Order" o
   JOIN customer_order c
     ON c.source_system_id = 1 AND c.source_order_key = CAST(o."OrderId" AS TEXT)
   GROUP BY 1, 2;

   -- no required value is missing (expect 0)
   SELECT count(*) FROM order_item WHERE source_system_id = 1 AND (product_id IS NULL OR seller_id IS NULL);

   -- referential and structural integrity (expect no rows, then 'ok')
   PRAGMA foreign_key_check;
   PRAGMA integrity_check;
   ```

3. **Check the second run changed nothing.** Row counts and surrogate ids (`order_id`,
   `order_item_id`, `product_id`) are identical after it.

4. **Spot-check a few rows** end to end: one order with a discount, one cancelled order, and one gift
   line. Compare source and target values by hand.

The canonical tables' `CHECK` constraints reject inconsistent values while loading, for example
totals that don't add up or invalid status codes. A run that fails because of them is a failed
review, not something to work around.

**Evidence to record:** output of both `dbt run`s and the results of every validation query.

## Review record

Copy this into the pull request or review notes:

```markdown
- [ ] 1. SQL valid: dbt compile clean; EXPLAIN passes for every model
- [ ] 2. Correct: matches ontology mappings; guesses labelled and approved; grain, lineage, idempotency checked
- [ ] 3. Test transform: two dbt runs OK; counts, money and codes reconcile; integrity checks clean; second run changed nothing
Reviewer: ____________  Date: __________  Source / sample data used: ____________
```
