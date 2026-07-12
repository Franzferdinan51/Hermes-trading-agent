# Agent-Teams Integration for Trading MoA

The private `Agent-Teams` repository provides a useful orchestration model for this project. Its `DESIGN-MOA-INTEGRATION.md` defines MoA as parallel reference models producing advisory text, followed by one aggregator model that is allowed to act. Reference agents have no tools; the aggregator is the only tool-using actor.

## Adopted architecture

```text
Hermes collectors
        ↓
Parallel advisory agents
  market / portfolio / protocol / execution
        ↓
Risk vote and disagreement check
        ↓
Single Hermes aggregator
        ↓
Global policy gate
        ↓
Platform-local dry-run
        ↓
Platform-local executor
```

## Patterns adopted from Agent-Teams

- **MoA:** advisory references run in parallel; aggregator synthesizes.
- **Council:** use adversarial debate and confidence scoring for material or ambiguous decisions.
- **Swarm:** use parallel task decomposition for research, simulation, and verification.
- **Budget caps:** trading MoA presets use 4 reference agents by default, 5 maximum for cross-platform review, bounded concurrency, and explicit reference/aggregator token budgets. Do not import the Agent-Teams 49-council pattern into trading execution.
- **Non-fatal references:** one failed model must not kill the review; record the failure and lower confidence.
- **Tool boundary:** reference agents are read-only; only the aggregator can call tools, and only the platform adapter can sign.
- **Auditability:** preserve reference outputs, votes, consensus score, aggregator decision, policy result, and final verification.

## Agent Mesh API integration

The `agent-mesh-api` repository provides REST, WebSocket, and MCP communication patterns for agent-to-agent messages, capabilities, health, groups, and shared resources. Use it as an optional transport layer for advisory reports and health events—not as a signer or execution authority.

Recommended mesh messages:

- `candidate.created`
- `reference.vote.completed`
- `moa.synthesis.completed`
- `risk.gate.completed`
- `platform.snapshot.updated`
- `execution.verification.completed`
- `platform.health.changed`

The mesh must carry normalized, non-secret evidence only. Do not send wallet secrets, private keys, CDP credentials, raw OTPs, or unrestricted transaction payloads through the mesh. Require authenticated agents, group/channel scoping, message TTLs, and health checks before relying on remote reports.

## Hermes implementation

- Use `delegate_task` for bounded parallel advisory reviews.
- Use `cronjob` with `context_from` for durable collector-to-supervisor handoff.
- Use Hermes Kanban for candidate lifecycle and ownership.
- Use platform-specific adapters from `state/platforms.json`.
- Keep reference prompts free of credentials, signing tools, and transaction permissions.
- Keep the aggregator subject to the global policy gate and platform-local executor.

## Candidate decision schema

Every candidate should carry:

```text
candidate_id
platform_id
chain
exact_asset_identity
current_balance
thesis
entry
target
invalidation
maximum_loss
notional
exit_path
market_vote
portfolio_vote
protocol_vote
execution_vote
consensus_score
confidence
hard_stops
simulation
backtest
aggregator_decision
policy_decision
execution_status
verification_status
```

## Preset guidance

- `default`: balanced market, portfolio, protocol, and execution review.
- `security`: heavier contract, custody, token-extension, oracle, bridge, and incident analysis.
- `execution-review`: quote freshness, route, fees, slippage, simulation, finality, and recovery analysis.
- `cross-platform`: compare opportunities and costs across platforms, but never treat a bridge or transfer as implicit.

## Security warning

Do not copy provider keys, wallet secrets, private keys, local endpoints, or personal network addresses from Agent-Teams configuration into this repository. Use environment variables, Hermes credential management, or protected secret stores. The Agent-Teams source is a design reference, not a credential source.
