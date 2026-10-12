# OpenRole Coding Agent Instructions

## Purpose

You are assisting with OpenRole Observatory, a data-engineering and FastAPI learning project.

The developer is intentionally learning the architecture and implementation.

Your goal is NOT to complete the project as quickly as possible.

Your goal is to help implement the system incrementally while keeping every change understandable, testable, and reviewable.

Before making architectural decisions, read:

- `README.md`
- `docs/product-spec.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/phase-1.md`

These documents are the current source of truth.

If implementation requirements conflict with the documentation, STOP and explain the conflict instead of silently changing the architecture.

---

## Development Model

Work in small implementation tasks.

Never implement an entire phase unless explicitly requested.

Never automatically continue to the next task after completing the current task.

Each task must have:

1. a narrow objective;
2. explicit files affected;
3. acceptance criteria;
4. tests;
5. an explanation after implementation.

Do not introduce features from future phases.

---

## Before Writing Code

For every task:

1. Inspect the current repository.
2. Read the relevant documentation.
3. Summarize the existing implementation relevant to the task.
4. Propose the smallest implementation plan.
5. List the files that will be created or modified.
6. Explain important technical decisions.
7. Identify anything ambiguous.

Do not modify files until this planning step has been completed.

If the requested work is already implemented, explain the current implementation rather than replacing it unnecessarily.

---

## Scope Control

Do not implement work outside the current task.

In particular, do not proactively add:

- frontend code;
- authentication;
- user accounts;
- billing;
- AI features;
- Lever;
- Ashby;
- Workable;
- Redis;
- Celery;
- Kafka;
- Spark;
- Airflow;
- Prefect;
- dbt;
- Elasticsearch;
- Kubernetes;
- n8n;

unless explicitly requested in the current task.

Do not add an abstraction merely because it may be useful someday.

Prefer the simplest design that satisfies the documented current requirement.

---

## Learning Requirements

When implementing an important pattern for the first time, keep the implementation explicit and readable.

Do not hide important behavior behind unnecessary frameworks or generated code.

The developer must be able to understand:

- data flow;
- dependency direction;
- transaction boundaries;
- validation;
- error handling;
- database constraints;
- idempotency;
- lineage;
- testing strategy.

When possible, prefer code that makes these concepts visible.

---

## Architecture Rules

OpenRole currently uses:

- Python
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- PostgreSQL
- Alembic
- Cloudflare R2 through an object-storage abstraction
- httpx
- pytest
- Ruff

The initial application is a modular monolith.

Maintain separation between:

- source connectors;
- source validation;
- canonical mapping;
- ingestion orchestration;
- persistence;
- object storage;
- FastAPI routes.

Provider-specific Greenhouse structures must not leak into the generic jobs domain.

FastAPI route handlers must not contain pipeline implementation logic.

R2-specific code must remain behind the object-storage interface.

---

## Data Engineering Rules

Preserve these invariants:

1. Raw source responses are preserved before canonical transformation.
2. Source-specific records are converted into canonical models.
3. Re-ingesting unchanged data does not create duplicate jobs.
4. Re-ingesting unchanged data does not create unnecessary job versions.
5. Changed canonical content creates a new immutable version.
6. Historical versions are never overwritten.
7. Source failures must never be interpreted as job removals.
8. Invalid individual records must be observable rather than silently discarded.
9. Every canonical job version must remain traceable to its source observation.
10. Important source observations must remain traceable to the pipeline run and raw snapshot.

---

## Testing Rules

Every task that introduces behavior must introduce or update tests.

Prefer:

- unit tests for pure transformation/domain logic;
- PostgreSQL integration tests for persistence;
- stored fixtures for Greenhouse data;
- end-to-end fixture tests for pipeline behavior.

Do not call the live Greenhouse API from the normal automated test suite.

Do not use SQLite as a substitute for PostgreSQL integration tests when testing PostgreSQL-specific behavior.

Tests should verify behavior, not implementation details.

---

## Code Quality

Use:

- explicit types;
- Pydantic models at system boundaries;
- SQLAlchemy 2-style APIs;
- clear names;
- small functions;
- deterministic transformations.

Avoid:

- broad untyped dictionaries across layers;
- giant service classes;
- business logic in API routes;
- deeply nested conditionals when clearer decomposition is possible;
- `except Exception: pass`;
- silent data loss;
- premature generic frameworks.

Do not add comments that merely restate obvious code.

Use comments to explain non-obvious reasoning or constraints.

---

## Migrations

All PostgreSQL schema changes must use Alembic.

Do not manually mutate the schema outside migrations.

For every schema task:

- generate or write the migration;
- inspect the migration;
- test upgrade;
- test downgrade where practical;
- explain constraints and indexes.

---

## After Implementation

Stop after completing the requested task.

Then provide:

### Changed Files

List each created or modified file and its purpose.

### How It Works

Explain the implementation from input to output.

### Important Concepts

Explain the FastAPI, Python, SQLAlchemy, PostgreSQL, or data-engineering concepts demonstrated by this task.

### Tests

Report:

- tests added;
- commands executed;
- results.

### Things I Should Review

Identify the 3–5 most important pieces of code the developer should personally read.

### Questions for Me

Give the developer 3 short questions that test whether they understand the implementation.

Do not begin the next task.

---

## Failure Handling

If tests fail:

Do not hide the failure.

Report:

- failing test;
- likely cause;
- changes attempted;
- remaining problem.

If the current architecture prevents a clean implementation, explain the problem before changing architecture.

---

## Documentation

Update documentation only when implementation changes documented behavior.

Do not rewrite large documentation files unnecessarily.

If a design decision materially changes the architecture, recommend an ADR before making the change.

---

## Core Principle

Optimize for:

understandable + correct + testable

before:

clever + generic + highly abstracted

The developer should finish each task understanding what was built and why.
