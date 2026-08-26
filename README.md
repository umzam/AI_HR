# AI Multi-Agent Virtual Training Platform Prototype

An AI product prototype for exploring role-play training, in-session coaching, structured evaluation, and AI-assisted scenario creation.

This repository demonstrates a product concept and runnable Streamlit implementation. It is not a validated enterprise PaaS, a production deployment, or a high-autonomy multi-agent system.

## Problem

Traditional role-play training is difficult to repeat consistently, expensive to facilitate manually, and hard to evaluate with a shared structure. This prototype explores whether explicit LLM roles can make practice scenarios easier to create, run, review, and iterate.

## Product concept

A learner enters a scenario, responds to a simulated role, receives coaching feedback, and ends the session with a structured report. Managers and HR-oriented views expose scenario configuration, user administration, synthetic capability views, and training history.

## Agent roles

- **Role** — responds as the scenario character and maintains the role-play conversation.
- **Coach** — evaluates each turn and gives focused feedback.
- **Tracking** — generates the end-of-session report and structured scores.
- **Scenario Architect** — generates an editable scenario draft from a selected job type and department.

These roles are explicitly and sequentially orchestrated in Python. They do not autonomously negotiate plans, delegate work, or form a self-organizing multi-agent system.

## Main user flow

```text
Choose scenario
→ Start role-play
→ Learner response
→ Role response
→ Coach feedback
→ Repeat
→ End session
→ Tracking report
→ Save synthetic training record
```

## What is implemented

- Streamlit interface with learner, department manager, HR, and admin views.
- Built-in HR, sales, customer-recovery, and technical troubleshooting scenarios.
- Sequential Role → Coach calls for each learner turn.
- Tracking report generation with structured score extraction.
- Scenario Architect with editable output and a static fallback for scenario drafting.
- SQLite persistence for users, capability scores, sessions, and custom scenarios.
- Training history, report viewing, scenario management, and user management.
- Synthetic dashboards and operational views for demonstrating the broader product concept.
- Environment-based configuration for an OpenAI-compatible model endpoint.

## Running locally

Python 3.9+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ARK_API_KEY="your-key"
export ARK_MODEL="your-model-id"
./start.sh
```

`ARK_BASE_URL` defaults to the configured Volcengine-compatible endpoint and can be overridden with another compatible endpoint.

Without `ARK_API_KEY` and `ARK_MODEL`, the Streamlit UI and synthetic seed data can still be inspected, and Scenario Architect can return a static example. The interactive Role / Coach / Tracking training flow requires a valid model configuration; this repository does not claim a complete offline Mock training mode.

## Demo-only credentials

The seed file contains four entirely synthetic local accounts:

| Username | Password | View |
|---|---|---|
| `demo_employee` | `demo123` | Learner |
| `demo_manager` | `demo123` | Department manager |
| `demo_hr` | `demo123` | HR |
| `demo_admin` | `demo123` | Admin |

These are **demo-only credentials**. Authentication stores plaintext passwords in local SQLite for prototype convenience and is not suitable for production use.

## Prototype architecture

```text
Streamlit UI
├── Role-based views
├── Training session orchestration
│   ├── Role LLM call
│   ├── Coach LLM call
│   └── Tracking LLM call
├── Scenario Architect LLM call / static fallback
└── SQLite local persistence
```

## Evaluation status

Business metrics in [Design_Document.md](Design_Document.md) are design assumptions, target metrics, or value hypotheses. They are not validated production outcomes.

Current evidence demonstrates code-level prototype implementation only. It does not demonstrate production reliability, learning effectiveness, business ROI, or enterprise adoption.

## Limitations

- Streamlit prototype rather than a production web application.
- Local SQLite persistence; no multi-tenant data architecture.
- Demo authentication with plaintext local passwords.
- Interactive training depends on an externally configured LLM endpoint.
- Sequential LLM-role orchestration, not high-autonomy multi-agent collaboration.
- No production deployment or operational reliability evidence.
- No real-user validation study.
- No validated learning-impact or business-impact metrics.
- Generated feedback and scores have not been calibrated against expert raters.
- Synthetic dashboard statistics illustrate intended views and are not observed usage data.

## Status

Portfolio demo / concept validation prototype. The project is useful as evidence of AI product design and implementation, not as a claim of production readiness or validated enterprise impact.
