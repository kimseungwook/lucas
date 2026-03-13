# Gemini Flash Dev Backend Draft

## Status

Implemented in configuration and code. A direct live Gemini backend call and one scheduled dev validation have both completed successfully. A Slack thread validation in `goyo-dev` is still optional follow-up QA rather than a blocker.

## Summary

Gemini Flash is available as a low-cost, development-only backend option for Lucas. The intended goal is to make Gemini Flash selectable in development without changing the Slack command surface, the scheduled monitoring flow, or the production backend policy.

## Why Gemini Flash

- Lower token cost for development experiments
- Strong latency and throughput characteristics for interactive analysis
- Good fit for development-time scheduled scans and Slack conversations
- Potential compatibility with the existing OpenAI-compatible code path

## Scope

### In scope

- Development-only backend option
- Configuration support for selecting Gemini Flash in non-production environments
- One scheduled validation path in development
- One interactive Slack validation path in development
- Documentation updates for configuration and validation

### Out of scope

- Production rollout of Gemini Flash
- Replacing Claude in production
- Replacing Groq/Kimi as the current validated non-Claude dev defaults
- Changing the Slack emergency-action surface

## Intended Positioning

- Claude remains the highest-capability backend
- Groq and Kimi remain the currently validated development backends
- Gemini Flash is introduced as an additional **dev-only** backend candidate

## Architecture Fit

Lucas currently supports:

- `claude-code`
- `openai-compatible`

Gemini Flash should be added in the least invasive way possible.

Preferred path:

- Reuse the existing `OpenAICompatibleBackend` if official Gemini OpenAI-compatible behavior fully matches the current request/response contract.

Fallback path:

- Introduce a dedicated `GeminiBackend` behind the existing `AgentBackend` interface if the OpenAI-compatible contract is not sufficient.

## Compatibility Assumptions

The draft assumes Gemini Flash can be used safely only if all of the following are true during validation:

- chat/completions-style request flow is supported or can be adapted with minimal logic
- response content can be normalized into the current `text`/`model`/`usage` shape
- no changes are required to Slack emergency-action logic
- non-Claude reduced-capability behavior remains acceptable

If these assumptions fail, Gemini must not be forced into the current `openai-compatible` path.

## Proposed Configuration

### Provider selection

- `LLM_BACKEND=openai-compatible` if Gemini can reuse the existing contract
- otherwise `LLM_BACKEND=gemini`

### Provider values

- `LLM_PROVIDER=gemini`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `GEMINI_BASE_URL`

### Initial default target

- model: `gemini-2.5-flash`
- environment: development only

## Validation Plan

### Local validation

- config resolution test
- provider selection test
- request/response normalization test

### Development cluster validation

- one interactive Slack question in `goyo-dev`
- one scheduled run in `goyo-dev`
- verify SQLite run record
- verify Slack output formatting

### Acceptance criteria

- Gemini Flash can be selected via config without breaking existing backends
- one interactive dev Slack thread succeeds
- one scheduled dev run succeeds
- no change is required to the Slack emergency-action command surface
- docs and tests pass

## Current implementation state

- `LLM_PROVIDER=gemini` is supported on the existing `openai-compatible` backend path.
- Default model: `gemini-2.5-flash`
- Default base URL: `https://generativelanguage.googleapis.com/v1beta/openai`
- Provider-specific auth fallback: `GEMINI_API_KEY`
- Direct live backend validation succeeded with a real Gemini response.
- One scheduled dev validation succeeded and wrote a normal run record to SQLite.
- The Slack emergency-action surface and non-Claude orchestration path were unchanged.

## Risks

- false OpenAI-compatibility assumptions
- response schema mismatch
- usage/token accounting mismatch
- unexpected formatting drift in Slack output

## Decision Rule

- If Gemini Flash cleanly fits the current OpenAI-compatible flow, implement it as a small provider addition.
- If it requires contract-specific handling, add a dedicated backend instead of overloading the existing OpenAI-compatible assumptions.

## Follow-Up Questions

- Should Gemini Flash remain dev-only permanently?
- Should Gemini Flash be allowed for scheduled scans only, or both scheduled and interactive dev paths?
- Should Gemini become the default dev backend after validation, or remain optional?
