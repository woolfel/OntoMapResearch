# Competency questions

These questions define what the commerce ontologies must be able to answer. Each has a SPARQL
query over `commerce_core.ttl` + `commerce_binding.ttl` and an expected outcome:

- **rows**: the question must return at least one answer.
- **empty**: a consistency check; any answer is a defect.

`run_competency_questions.py` runs every query and fails if an outcome is not met. The queries
assume these prefixes:

```
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX cc:   <https://ontoresearch.example/commerce/core#>
PREFIX cb:   <https://ontoresearch.example/commerce/binding#>
```

## A. Core concepts (no database knowledge needed)

### CQ-01: What business concepts does commerce consist of, and what does each mean?
Expect: rows
```sparql
SELECT ?concept ?definition WHERE {
  ?class a owl:Class ; rdfs:label ?concept ; skos:definition ?definition .
  FILTER(STRSTARTS(STR(?class), STR(cc:)))
  FILTER NOT EXISTS { ?class rdfs:subClassOf* cc:CodeList }
} ORDER BY ?concept
```

### CQ-02: What statuses can an order have, and which of them mean "cart" versus "placed order"?
Expect: rows
```sparql
SELECT ?code ?status ?meaning WHERE {
  ?s a cc:OrderStatus ; skos:notation ?code ; rdfs:label ?status .
  OPTIONAL {
    ?defined owl:equivalentClass/owl:intersectionOf/rdf:rest*/rdf:first/owl:someValuesFrom/owl:oneOf/rdf:rest*/rdf:first ?s ;
             rdfs:label ?meaning .
  }
} ORDER BY ?meaning ?code
```

### CQ-03: Which properties describe an order, and what unit does each monetary value use?
Expect: rows
```sparql
SELECT ?property ?kind ?range ?convention WHERE {
  ?property rdfs:domain cc:Order ; rdfs:range ?range ; a ?kind .
  FILTER(?kind IN (owl:ObjectProperty, owl:DatatypeProperty))
  OPTIONAL { ?property cc:valueConvention ?convention }
} ORDER BY ?kind ?property
```

### CQ-04: How is a product connected to the company that manufactures it?
Expect: rows
```sparql
SELECT ?step1 ?via1 ?step2 ?via2 ?step3 WHERE {
  ?step1 a owl:ObjectProperty ; rdfs:domain cc:Product ; rdfs:range ?via1 .
  ?step2 a owl:ObjectProperty ; rdfs:domain ?via1 ; rdfs:range ?via2 .
  OPTIONAL { ?step3 a owl:ObjectProperty ; rdfs:domain ?via2 ; rdfs:range cc:Manufacturer . }
  FILTER(?via2 = cc:Manufacturer || BOUND(?step3))
}
```

### CQ-05: Which identifiers can identify a product (and so match it across stores)?
Expect: rows
```sparql
SELECT ?identifier ?definition WHERE {
  ?p rdfs:subPropertyOf cc:identifier ; rdfs:domain cc:Product ; rdfs:label ?identifier .
  OPTIONAL { ?p skos:definition ?definition }
}
```

### CQ-06: What can a promotion be targeted at?
Expect: rows
```sparql
SELECT ?property ?target WHERE {
  ?property rdfs:domain cc:Promotion ; rdfs:range ?target .
  FILTER(STRSTARTS(STR(?property), CONCAT(STR(cc:), "appliesTo"))
         || STRSTARTS(STR(?property), CONCAT(STR(cc:), "targetAttribute")))
}
```

### CQ-07: What other names do source systems use for each concept?
Expect: rows
```sparql
SELECT ?concept (GROUP_CONCAT(?alt; separator=", ") AS ?alsoCalled) WHERE {
  ?class rdfs:label ?concept ; skos:altLabel ?alt .
} GROUP BY ?concept ORDER BY ?concept
```

### CQ-08: Which value formats exist, and how is each converted to the core convention?
Expect: rows
```sparql
SELECT ?format ?description ?conversion WHERE {
  ?f a cb:ValueFormat ; rdfs:label ?format ; cb:formatDescription ?description ; cb:conversionTemplate ?conversion .
} ORDER BY ?format
```

## B. Coverage of each source

### CQ-09: Which concepts does each source system provide?
Expect: rows
```sparql
SELECT ?source (COUNT(DISTINCT ?class) AS ?concepts) (GROUP_CONCAT(DISTINCT ?name; separator=", ") AS ?classes) WHERE {
  ?b a cb:ConceptBinding ; cb:inSource/cb:sourceCode ?source ; cb:bindsClass ?class .
  BIND(STRAFTER(STR(?class), "#") AS ?name)
} GROUP BY ?source ORDER BY ?source
```

### CQ-10: Which core concepts is each source unable to provide?
Expect: rows
```sparql
SELECT ?source ?missing WHERE {
  ?s a cb:SourceSystem ; cb:sourceCode ?source .
  ?missing a owl:Class .
  FILTER(STRSTARTS(STR(?missing), STR(cc:)))
  FILTER NOT EXISTS { ?missing rdfs:subClassOf* cc:CodeList }
  FILTER NOT EXISTS { ?missing owl:equivalentClass/owl:intersectionOf ?any }   # defined classes
  FILTER NOT EXISTS { ?missing owl:hasKey ?globalKey }                          # ISO reference data
  FILTER NOT EXISTS { ?b cb:inSource ?s ; cb:bindsClass ?missing }
} ORDER BY ?source ?missing
```

### CQ-11: Which order properties are available from every source, and which only from some?
Expect: rows
```sparql
SELECT ?property (COUNT(DISTINCT ?source) AS ?sources) (GROUP_CONCAT(DISTINCT ?source; separator=", ") AS ?providedBy) WHERE {
  ?pb cb:bindsProperty ?property ; cb:ofConceptBinding ?b .
  ?b cb:bindsClass cc:Order ; cb:inSource/cb:sourceCode ?source .
} GROUP BY ?property ORDER BY DESC(?sources) ?property
```

### CQ-12: Which order properties can a given source not supply?
Expect: rows
```sparql
SELECT ?source ?property WHERE {
  ?s cb:sourceCode ?source .
  ?property rdfs:domain cc:Order .
  FILTER EXISTS { ?b cb:inSource ?s ; cb:bindsClass cc:Order }
  FILTER NOT EXISTS { ?pb cb:bindsProperty ?property ; cb:ofConceptBinding [ cb:inSource ?s ; cb:bindsClass cc:Order ] }
  # derivable from the inverse property bound on the other concept
  FILTER NOT EXISTS { ?property owl:inverseOf ?inverse . ?pb2 cb:bindsProperty ?inverse ; cb:ofConceptBinding/cb:inSource ?s }
} ORDER BY ?source ?property
```

### CQ-13: Which product identifiers does each source carry (what can products be matched on)?
Expect: rows
```sparql
SELECT ?identifier (GROUP_CONCAT(DISTINCT ?source; separator=", ") AS ?sources) WHERE {
  ?pb cb:bindsProperty ?identifier ; cb:ofConceptBinding [ cb:bindsClass cc:Product ; cb:inSource/cb:sourceCode ?source ] .
  ?identifier rdfs:subPropertyOf cc:identifier .
} GROUP BY ?identifier ORDER BY ?identifier
```

### CQ-14: Which source columns are not used by any binding?
Expect: rows
```sparql
SELECT ?source ?table ?column WHERE {
  ?col a cb:Column ; cb:columnName ?column ; cb:inTable ?t .
  ?t cb:tableName ?table ; cb:inSource/cb:sourceCode ?source .
  FILTER NOT EXISTS { ?x cb:usesColumn|cb:sourceColumn|cb:keyColumn ?col }
} ORDER BY ?source ?table ?column
```

## C. Locating data for a transformation

### CQ-15: In each source, where is the order grand total stored and how is it converted?
Expect: rows
```sparql
SELECT ?source ?table ?sourceExpression ?format ?toCore WHERE {
  ?pb cb:bindsProperty cc:grandTotal ; cb:ofConceptBinding ?b ;
      cb:sourceExpression ?sourceExpression ; cb:valueFormat/rdfs:label ?format ; cb:toCoreExpression ?toCore .
  ?b cb:inSource/cb:sourceCode ?source ; cb:fromTable/cb:tableName ?table .
} ORDER BY ?source
```

### CQ-16: Which monetary values need converting, and how, per source?
Expect: rows
```sparql
SELECT ?source ?property ?table ?sourceExpression ?format ?toCore WHERE {
  ?pb cb:bindsProperty ?property ; cb:ofConceptBinding ?b ; cb:valueFormat ?f ;
      cb:sourceExpression ?sourceExpression ; cb:toCoreExpression ?toCore .
  ?property rdfs:subPropertyOf cc:monetaryAmount .
  FILTER(?f != cb:MoneyMajor)
  ?f rdfs:label ?format .
  ?b cb:inSource/cb:sourceCode ?source ; cb:fromTable/cb:tableName ?table .
} ORDER BY ?source ?property
```

### CQ-17: How do each source's order status codes map to the core statuses?
Expect: rows
```sparql
SELECT ?coreStatus ?source ?sourceValue WHERE {
  ?vb cb:bindsProperty cc:orderStatus ; cb:ofConceptBinding/cb:inSource/cb:sourceCode ?source .
  { ?vb cb:valueMap [ cb:sourceValue ?sourceValue ; cb:targetIndividual ?ind ] }
  UNION
  { ?vb cb:matchOnNotation true . ?ind a cc:OrderStatus ; skos:notation ?sourceValue }
  ?ind skos:notation ?coreStatus .
} ORDER BY ?coreStatus ?source
```

### CQ-18: Which different source codes collapse into the same core code?
Expect: rows
```sparql
SELECT ?source ?property ?coreCode (GROUP_CONCAT(?sourceValue; separator=", ") AS ?sourceValues) WHERE {
  ?vb cb:bindsProperty ?property ; cb:ofConceptBinding/cb:inSource/cb:sourceCode ?source ;
      cb:valueMap [ cb:sourceValue ?sourceValue ; cb:targetIndividual ?ind ] .
  ?ind skos:notation ?coreCode .
} GROUP BY ?source ?property ?coreCode HAVING (COUNT(?sourceValue) > 1)
```

### CQ-19: How do I join an order line to its order, product and seller in BigRiver?
Expect: rows
```sparql
SELECT ?property ?fromTable ?joinExpression ?toTable ?toKey WHERE {
  ?rb cb:ofConceptBinding ?b ; cb:bindsProperty ?property ; cb:targetBinding ?t ; cb:joinExpressions/rdf:first ?joinExpression .
  ?b cb:bindsClass cc:OrderLine ; cb:inSource/cb:sourceCode "bigriver" ; cb:fromTable/cb:tableName ?fromTable .
  ?t cb:fromTable/cb:tableName ?toTable ; cb:keyExpressions/rdf:first ?toKey .
  FILTER(?property IN (cc:lineOf, cc:ofProduct, cc:soldBy))
}
```

### CQ-20: Which concepts are hidden in tables named after something else?
Expect: rows
```sparql
SELECT ?source ?table ?hiddenConcept WHERE {
  ?b cb:fromTable/cb:tableName ?table ; cb:bindsClass ?c ; cb:inSource/cb:sourceCode ?source .
  FILTER NOT EXISTS {
    ?c rdfs:label|skos:altLabel ?name .
    BIND(LCASE(REPLACE(STR(?name), "[ _]", "")) AS ?n)
    FILTER(?n = LCASE(REPLACE(?table, "_", "")) || CONCAT(?n, "s") = LCASE(REPLACE(?table, "_", "")))
  }
  BIND(STRAFTER(STR(?c), "#") AS ?hiddenConcept)
} ORDER BY ?source ?table ?hiddenConcept
```

### CQ-21: Which source tables hold several concepts at once (denormalized)?
Expect: rows
```sparql
SELECT ?source ?table (COUNT(DISTINCT ?c) AS ?count) (GROUP_CONCAT(DISTINCT ?name; separator=", ") AS ?concepts) WHERE {
  ?b cb:fromTable/cb:tableName ?table ; cb:bindsClass ?c ; cb:inSource/cb:sourceCode ?source .
  BIND(STRAFTER(STR(?c), "#") AS ?name)
} GROUP BY ?source ?table HAVING (COUNT(DISTINCT ?c) > 1) ORDER BY ?source ?table
```

### CQ-22: Which concepts exist only implicitly (no table, or a subset of another table's rows)?
Expect: rows
```sparql
SELECT ?source ?concept ?how ?note WHERE {
  ?b cb:inSource/cb:sourceCode ?source ; cb:bindsClass ?c .
  OPTIONAL { ?b cb:rowFilter ?filter }
  OPTIONAL { ?b cb:isVirtual ?virtual }
  OPTIONAL { ?b rdfs:comment ?note }
  FILTER(BOUND(?filter) || BOUND(?virtual))
  BIND(STRAFTER(STR(?c), "#") AS ?concept)
  BIND(IF(BOUND(?virtual), "virtual: no table", CONCAT("rows where ", ?filter)) AS ?how)
} ORDER BY ?source ?concept
```

### CQ-23: How does each source record returns?
Expect: rows
```sparql
SELECT ?source ?table ?filter ?note WHERE {
  ?b cb:bindsClass cc:ReturnLine ; cb:inSource/cb:sourceCode ?source ; cb:fromTable/cb:tableName ?table .
  OPTIONAL { ?b cb:rowFilter ?filter }
  OPTIONAL { ?b rdfs:comment ?note }
}
```

### CQ-24: Which bound values need cleansing or context before they can be trusted?
Expect: rows
```sparql
SELECT ?source ?concept ?property ?sourceExpression ?format WHERE {
  ?pb cb:valueFormat ?f ; cb:bindsProperty ?property ; cb:sourceExpression ?sourceExpression ; cb:ofConceptBinding ?b .
  FILTER(?f IN (cb:BrandFreeText, cb:CountryFreeText, cb:TimestampLocalUSCentral, cb:BrowsePath))
  ?f rdfs:label ?format .
  ?b cb:inSource/cb:sourceCode ?source ; cb:bindsClass ?c .
  BIND(STRAFTER(STR(?c), "#") AS ?concept)
} ORDER BY ?source ?concept ?property
```

### CQ-25: Which values does a source not store, so the binding assumes a constant?
Expect: rows
```sparql
SELECT ?source ?concept ?property ?assumed WHERE {
  ?pb cb:bindsProperty ?property ; cb:ofConceptBinding ?b .
  { ?pb cb:constantValue ?assumed } UNION { ?pb cb:constantIndividual/skos:notation ?assumed }
  ?b cb:inSource/cb:sourceCode ?source ; cb:bindsClass ?c .
  BIND(STRAFTER(STR(?c), "#") AS ?concept)
} ORDER BY ?source ?concept ?property
```

### CQ-26: What do I select, from where, to extract orders from BobsUncle in core form?
Expect: rows
```sparql
SELECT ?table ?filter ?property ?toCore WHERE {
  ?b cb:bindsClass cc:Order ; cb:inSource/cb:sourceCode "bobsuncle" ; cb:fromTable/cb:tableName ?table .
  OPTIONAL { ?b cb:rowFilter ?filter }
  ?pb cb:ofConceptBinding ?b ; cb:bindsProperty ?property ; cb:toCoreExpression ?toCore .
} ORDER BY ?property
```

## D. Consistency (any answer is a defect)

### CQ-27: Is any property bound on a class outside its domain?
Expect: empty
```sparql
SELECT ?binding ?property ?domain ?class WHERE {
  ?binding cb:bindsProperty ?property ; cb:ofConceptBinding/cb:bindsClass ?class .
  ?property rdfs:domain ?domain .
  FILTER NOT EXISTS { ?class rdfs:subClassOf* ?domain }
}
```

### CQ-28: Does any relation point at a binding whose class is outside the property's range?
Expect: empty
```sparql
SELECT ?binding ?property ?range ?targetClass WHERE {
  ?binding cb:bindsProperty ?property ; cb:targetBinding/cb:bindsClass ?targetClass .
  ?property rdfs:range ?range .
  FILTER NOT EXISTS { ?targetClass rdfs:subClassOf* ?range }
}
```

### CQ-29: Does any code mapping point at an individual that is not in the property's code list?
Expect: empty
```sparql
SELECT ?binding ?property ?individual WHERE {
  ?binding cb:bindsProperty ?property .
  { ?binding cb:valueMap/cb:targetIndividual ?individual } UNION { ?binding cb:constantIndividual ?individual }
  ?property rdfs:range ?codeList .
  FILTER NOT EXISTS { ?individual a ?codeList }
}
```

### CQ-30: Does any binding name a core term that the core ontology does not define?
Expect: empty
```sparql
SELECT DISTINCT ?term WHERE {
  { ?b cb:bindsClass ?term } UNION { ?b cb:bindsProperty ?term } UNION { ?b cb:matchOnProperty ?term }
  FILTER NOT EXISTS { ?term a ?type . FILTER(?type IN (owl:Class, owl:ObjectProperty, owl:DatatypeProperty)) }
}
```
