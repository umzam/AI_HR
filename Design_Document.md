# AI Multi-Agent Virtual Training Platform — Product Design Document

**Artifact type:** AI product prototype / concept validation

**Document version:** v1.1

**Original prototype date:** 2026-04-11

> Truthfulness boundary: implemented behavior is separated from assumptions and targets. No business-impact number in this document is a validated production result.

## 1. Problem framing

The concept explores whether repeatable AI role-play can complement manual enterprise training for communication, sales, HR, service, and technical troubleshooting scenarios.

### Design assumptions — not validated facts

The following numbers were used to make the initial product problem concrete. This project has not independently validated them:

| Design assumption | Initial planning value |
|---|---|
| Time for a new employee to become independently capable in a complex role | 6–12 months |
| First-year sales performance relative to an experienced employee | below 60% |
| Manager time spent on unstructured coaching | 70% |

These values must not be presented as observed customer data, market research findings, or results of this prototype.

## 2. Product concept

The prototype combines four explicit LLM roles with role-based product views:

```text
Streamlit UI
├── Learner / Manager / HR / Admin views
├── Training flow
│   ├── Role call
│   ├── Coach call
│   └── Tracking call
├── Scenario Architect call or static example fallback
└── SQLite local persistence
```

The Role, Coach, and Tracking calls are sequentially orchestrated by application code. Scenario Architect is invoked separately when creating a scenario. This is not autonomous agent planning or self-organizing multi-agent collaboration.

## 3. Intended agent responsibilities

| Role | Responsibility | Current implementation |
|---|---|---|
| Role | Simulate the scenario character and maintain the dialogue | Stateful message history and one LLM call per turn |
| Coach | Give focused feedback on the latest turn | Stateless LLM call with recent context |
| Tracking | Generate the final report and scores | End-of-session LLM call plus JSON score parsing |
| Scenario Architect | Draft a scenario configuration | LLM call with structured parsing; static example fallback when unavailable |

## 4. Implemented prototype scope

- Streamlit interface and four role-oriented views.
- Built-in HR, sales, customer-recovery, and technical scenarios.
- Role-play, per-turn coaching, final report, and score extraction.
- Scenario creation and editing.
- SQLite user, capability, session, score, and custom-scenario tables.
- Synthetic seed accounts and synthetic dashboard statistics.
- Environment-based OpenAI-compatible API configuration.

Not implemented or not demonstrated:

- enterprise multi-tenancy;
- production identity, encryption, audit, or authorization controls;
- production reliability and monitoring;
- calibrated evaluation against human expert scoring;
- real-user or organizational impact validation.

## 5. Technical design choices

| Choice | Prototype rationale | Evidence status |
|---|---|---|
| Streamlit | Fast implementation of chat and role-based views in Python | Implemented in code |
| OpenAI-compatible SDK | Keeps the call layer compatible with the configured endpoint | Implemented in code |
| Explicit orchestration | Makes the order and context passed to each LLM role visible | Implemented in code |
| SQLite + WAL | Low-dependency local persistence for a demo | Implemented; production concurrency not validated |
| Weighted capability update | `new = 0.7 × previous + 0.3 × session` | Implemented product rule; effectiveness not validated |

### Implemented model-call settings

These are configuration values visible in the current code, not performance claims:

```text
Role       max_tokens = 512
Coach      max_tokens = 600
Tracking   max_tokens = 2000
Ask Coach  max_tokens = 600
```

Prompts constrain role and output format, but they should not be described as a complete prompt-injection, jailbreak, or hallucination defense.

## 6. Iteration record

| Version | Prototype change | Evidence type |
|---|---|---|
| v0.1 | Single-page Streamlit flow and scripted examples | Implemented iteration |
| v0.2 | OpenAI-compatible model calls | Implemented iteration |
| v0.3 | SQLite persistence | Implemented iteration |
| v0.4 | Scenario selection and training history | Implemented iteration |
| v0.5 | Learner / Manager / HR / Admin views | Implemented iteration |
| v0.6 | Scenario Architect | Implemented; “30-second scenario launch” remains a Target Metric, not a validated result |
| v0.7 | Ask Coach interaction | Implemented iteration |
| v0.8 | Light UI and synthetic demo accounts | Implemented iteration |

## 7. Evaluation Plan / Target Metrics

These values describe what a future validation could measure. No baseline or target below has been validated by production data.

| Classification | Metric | Planning baseline | Target | Proposed measurement |
|---|---|---:|---:|---|
| Target Metric | Learning-to-work transfer after at least three sessions | 35% | 65% | Manager assessment within 90 days |
| Target Metric | Time to independently handle complex work | 180 days | under 90 days | Quarterly cohort comparison |
| Target Metric | Share of senior staff time spent on unstructured coaching | 70% | under 30% | Monthly time study |
| Target Metric | Scenario draft creation time | not measured | 30 seconds | Timed task from job selection to editable draft |

Required future validation would need a defined cohort, comparison method, evaluator calibration, data consent, and explicit measurement period.

## 8. Value Hypotheses

The following are product hypotheses, not achieved outcomes:

- **4 hours per person per month saved:** hypothesis that structured reports could reduce manual HRBP reporting time.
- **Development cycle compressed to one fifth:** initial implementation hypothesis for choosing Streamlit; no controlled comparison was performed.
- **Marginal cost approaches zero for a new department:** directional hypothesis about scenario reuse, not an economic result. Real onboarding, review, governance, and model costs remain.
- **Reusable scenario library:** hypothesis that reviewed scenarios can reduce repeated setup work.
- **More consistent capability evidence:** hypothesis that structured sessions can complement, not replace, human evaluation.

## 9. Validation status

Validated at code/prototype level:

- the application routes among the four views;
- the LLM roles are explicitly orchestrated;
- session results can be parsed and stored;
- custom scenarios and local users can be managed;
- Python modules compile successfully.

Not validated:

- learning effectiveness;
- score validity or fairness;
- business impact;
- production reliability;
- enterprise adoption;
- any numeric assumption, target, or value hypothesis above.

This document describes an AI product prototype and an evaluation plan. It does not claim production deployment or validated business results.
