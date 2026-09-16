# Graph Report - api-testing-agent  (2026-09-16)

## Corpus Check
- Corpus is ~22,487 words - fits in a single context window. You may not need a graph.

## Summary
- 584 nodes · 1839 edges · 11 communities
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 222 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Workflow Builder
- Auto Mock LLM Client
- API Executor Pipeline
- HTTP Client Layer
- LLM Abstraction Core
- Test Generation Agent
- Agent Orchestrator
- Assertion Engine
- Failure Analysis Agent
- OpenAPI Parser
- API Understanding Agent

## God Nodes (most connected - your core abstractions)
1. `TestCase` - 61 edges
2. `APIEndpoint` - 46 edges
3. `APIExecutor` - 45 edges
4. `HTTPMethod` - 43 edges
5. `AgentOrchestrator` - 38 edges
6. `APIResponse` - 38 edges
7. `APISpecification` - 36 edges
8. `OpenAPIParser` - 36 edges
9. `MockLLMClient` - 33 edges
10. `DependencyDetector` - 33 edges

## Surprising Connections (you probably didn't know these)
- `APIUnderstandingAgent` --uses--> `LLMClient`  [INFERRED]
  agents/api_understanding_agent.py → ai/llm_client.py
- `APIUnderstandingAgent` --uses--> `APIEndpoint`  [INFERRED]
  agents/api_understanding_agent.py → models/api_models.py
- `APIUnderstandingAgent` --uses--> `APISpecification`  [INFERRED]
  agents/api_understanding_agent.py → models/api_models.py
- `APIUnderstandingAgent` --uses--> `EndpointUnderstanding`  [INFERRED]
  agents/api_understanding_agent.py → models/api_understanding.py
- `FailureAnalysisAgent` --uses--> `LLMClient`  [INFERRED]
  agents/failure_analysis_agent.py → ai/llm_client.py

## Import Cycles
- None detected.

## Communities (11 total, 0 thin omitted)

### Community 0 - "Workflow Builder"
Cohesion: 0.07
Nodes (61): Any, Automatic synthesis of executable workflows from OpenAPI specs and detected…, Build executable multi-step workflows from OpenAPI specifications and…, Automatically synthesize end-to-end CRUD and auth workflows., Generate a basic sample body based on schema if available., WorkflowBuilder, APIEndpoint, APIParameter (+53 more)

### Community 1 - "Auto Mock LLM Client"
Cohesion: 0.05
Nodes (56): AutoMockLLMClient, _build_sample(), Any, StructuredModel, Synthesize GeneratedTestBatch for the endpoint., Generates schema-valid, evidence-grounded data for offline CLI execution and…, Synthesize FailureAnalysis from test case and execution result., Deterministically produce schema-valid models for known agent tasks. (+48 more)

### Community 2 - "API Executor Pipeline"
Cohesion: 0.07
Nodes (55): APIExecutor, Any, Prepare, execute, capture and assert a TestCase without AI interpretation., Run one validated test case and return a complete structured outcome., Run test case and return both structured ExecutionResult and raw APIResponse., _extract_from_dict(), _extract_variable(), Any (+47 more)

### Community 3 - "HTTP Client Layer"
Cohesion: 0.05
Nodes (44): AuthBase, APIClient, APIClientError, APIResponse, mask_sensitive(), mask_sensitive_text(), Any, Logger (+36 more)

### Community 4 - "LLM Abstraction Core"
Cohesion: 0.06
Nodes (42): ABC, AI reasoning interfaces; no module in this package executes generated code., create_llm_client(), LLMClient, LLMMetrics, LLMProviderError, LLMResponse, MockLLMClient (+34 more)

### Community 5 - "Test Generation Agent"
Cohesion: 0.07
Nodes (39): ValueError, Generate validated, declarative API tests from endpoint understanding records., Raised when generated tests conflict with their requested endpoint or limits., Turn evidence-based endpoint understanding into safe structured test…, Generate and validate a bounded useful test set for exactly one endpoint., TestGenerationAgent, TestGenerationError, Deterministic offline LLM client for mock execution without external API keys. (+31 more)

### Community 6 - "Agent Orchestrator"
Cohesion: 0.10
Nodes (29): AgentOrchestrator, OrchestratorError, RuntimeError, Bounded coordinator for API understanding, generation, execution and analysis., Synthesize workflows based on dependencies detected from the API specification., Execute the next pending workflow., Raised when coordination input violates a deterministic safety invariant., Run an explicitly bounded agent loop; no decision may trigger arbitrary code. (+21 more)

### Community 7 - "Assertion Engine"
Cohesion: 0.10
Nodes (25): AssertionEngine, Any, Extensible deterministic assertions over captured HTTP responses., Evaluate declared assertions without involving an LLM., Evaluate every assertion, retaining failures instead of failing fast., Deterministic test execution and assertion evaluation., AssertionResult, Result of one deterministic assertion. (+17 more)

### Community 8 - "Failure Analysis Agent"
Cohesion: 0.11
Nodes (28): FailureAnalysisAgent, FailureAnalysisError, ValueError, Evidence-oriented AI classification of deterministic execution failures., Raised when analysis is requested for a non-failure or mismatched result., Classify failures while preserving the distinction between evidence and…, Return a validated non-conclusive classification for one failed execution., is_failure_result() (+20 more)

### Community 9 - "OpenAPI Parser"
Cohesion: 0.13
Nodes (20): OpenAPI parsing and deterministic analysis., OpenAPIParseError, OpenAPIParser, Any, Path, ValueError, Raised when a supplied OpenAPI document cannot be safely parsed., Parse OpenAPI 3.0/3.1 JSON or YAML without performing network requests. (+12 more)

### Community 10 - "API Understanding Agent"
Cohesion: 0.12
Nodes (19): APIUnderstandingAgent, ValueError, Structured API understanding agent built on parsed specification facts., Raised when an AI understanding result does not match its source endpoint., Generate validated API-understanding records from an OpenAPI endpoint., Produce one validated understanding; identical endpoint metadata is cached., Understand every endpoint in source-document order., UnderstandingError (+11 more)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TestCase` connect `API Executor Pipeline` to `Workflow Builder`, `Auto Mock LLM Client`, `HTTP Client Layer`, `LLM Abstraction Core`, `Test Generation Agent`, `Agent Orchestrator`, `Assertion Engine`, `Failure Analysis Agent`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **Why does `APIResponse` connect `HTTP Client Layer` to `Workflow Builder`, `API Executor Pipeline`, `Agent Orchestrator`, `Assertion Engine`, `Failure Analysis Agent`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Why does `OpenAPIParser` connect `OpenAPI Parser` to `Workflow Builder`, `Auto Mock LLM Client`, `API Executor Pipeline`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `TestCase` (e.g. with `FailureAnalysisAgent` and `AgentOrchestrator`) actually correct?**
  _`TestCase` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `APIEndpoint` (e.g. with `APIUnderstandingAgent` and `TestGenerationAgent`) actually correct?**
  _`APIEndpoint` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `APIExecutor` (e.g. with `AgentOrchestrator` and `APIClient`) actually correct?**
  _`APIExecutor` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `HTTPMethod` (e.g. with `WorkflowBuilder` and `APIDependency`) actually correct?**
  _`HTTPMethod` has 22 INFERRED edges - model-reasoned connections that need verification._