# AI-SWE Constitution

## Core Principles

### I. Service Boundaries

The AI service MUST remain one FastAPI application with independent recommendation and
shopping agent modules. The Frontend MUST call the Backend for customer requests; the Backend
MUST own authentication, authorization, business data, order creation, inventory, and payment
processing. The AI service MUST access Backend data through agreed HTTP APIs and MUST NOT connect
to the Backend database. This keeps business decisions and data ownership in one place. The
Frontend owns the interactive mascot's presentation; AI agent behavior reaches it through
Backend-mediated APIs.

### II. Honest Contracts

Specifications, documentation, responses, and tests MUST distinguish implemented behavior from
proposals and placeholders. An unfinished feature MUST expose its unfinished status; an empty
result MUST NOT be presented as a computed recommendation. Backend paths, payloads, service
authentication, session behavior, and error mappings MUST be agreed before code depends on them.
This prevents clients from treating a draft contract as an operational capability.

### III. Simple Modular Design

Routers MUST handle HTTP concerns, schemas MUST validate API data, and feature services MUST own
feature behavior. Recommendation and agent modules MUST NOT import each other. New dependencies,
storage, queues, model frameworks, and abstraction layers MUST have a specific approved use case;
reserved directories alone do not justify implementation. This preserves the small scaffold and
keeps each feature independently understandable.

### IV. Data and Security Ownership

The AI service MUST NOT make business authorization decisions from an unverified user ID or
persist replacement copies of Backend-owned business data. Backend operations initiated by the
AI service MUST use authenticated service access and Backend-enforced authorization for the
customer and requested action. Sensitive customer information MUST be protected and processed
only when needed for an authorized purpose. Data sent to an external LLM provider MUST be limited
to what the approved task requires. Secrets and sensitive customer data MUST NOT appear in logs;
secrets MUST come from runtime configuration and MUST NOT be committed. Before a real Backend or
provider integration is released, its service authentication, allowed data, failure behavior,
and exposure path MUST be agreed and reviewed. These rules protect customer data across service
boundaries.

### V. Verifiable Changes

Changes to an implemented API contract, validation rule, or external integration MUST include
tests that exercise the changed behavior and relevant failure paths. Agent tool execution tests
MUST cover successful operations, authorization failures, invalid tool arguments, and Backend
failures. Routine unit tests MUST use deterministic substitutes and MUST NOT require live Backend
or LLM services. LLM behavior MUST be evaluated separately against defined feature criteria;
deterministic tests MUST NOT be reported as proof of model quality. Changes MUST pass the
repository's Ruff checks and pytest suite before merge. Documentation MUST reflect what those
checks establish and MUST NOT claim that an unavailable external system was tested. This makes
review evidence match the actual running service.

### VI. Grounded and Authorized Agent Actions

Product, price, inventory, and order information reported by the agent MUST be grounded in
authoritative Backend data. The agent MUST perform business actions only through explicitly
defined Backend tools with authorization enforced for the customer and action. State-changing
actions MUST have explicit user authorization; final order submission MUST also have explicit
user confirmation. The customer MUST control payment completion. The agent MUST verify Backend
results before reporting an action as successful. User requests MAY specify shopping actions, but
MUST NOT override tool permissions, Backend authorization, or confirmation requirements.
Instructions embedded in catalog content or tool responses MUST NOT be treated as authoritative
instructions or allowed to override agent security rules.

## Technical Constraints

The current service uses Python 3.12+, FastAPI, Pydantic v2, HTTPX, uv, pytest, and Ruff.
Dependency changes MUST update the uv lockfile. The service MUST retain versioned JSON API
routes and a configurable Backend HTTP base URL and timeout. A health response MUST describe
process liveness only unless dependency checks are explicitly implemented. Production deployment
MUST keep the AI service on an internal network behind the Backend; development Compose settings
MUST NOT be assumed to define the production topology.

## Development Workflow

For each feature, document the intended behavior and distinguish confirmed Backend agreements
from open decisions before planning implementation. Review changes against all Core Principles.
Run `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest` for code changes.
When external systems are unavailable, record the verification limit. Update API and architecture
documentation when their described behavior or boundaries change.

## Governance

This constitution takes precedence over other project guidance when they conflict. Amendments
MUST be made in this file, explain the changed principles and migration impact, and be reviewed
before adoption. Versioning follows semantic versioning: MAJOR for incompatible governance
changes or removed principles, MINOR for added principles or materially expanded guidance, and
PATCH for clarifications without a rule change. Each feature specification, plan, and code review
MUST check compliance; any exception MUST be explicit, justified, and approved in the review.

**Version**: 1.0.0 | **Ratified**: 2026-10-28 | **Last Amended**: 2026-10-28
