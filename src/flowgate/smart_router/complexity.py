"""Complexity scoring engine — rule-based prompt complexity evaluation.

Mirrors the LiteLLM Complexity Router approach (7 weighted dimensions).
Weights and boundaries are fully configurable from the frontend / YAML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ─── Keyword sets ────────────────────────────────────────────────────────────

_CODE_KEYWORDS = frozenset({
    "function", "class", "api", "database", "algorithm", "implement",
    "code", "debug", "refactor", "query", "sql", "regex", "async",
    "interface", "schema", "endpoint", "middleware", "deploy", "docker",
    "kubernetes", "lambda", "recursive", "complexity", "optimize",
})

_REASONING_MARKERS = [
    "step by step", "think through", "analyze", "explain why", "reason about",
    "break down", "walk me through", "critically evaluate", "compare and contrast",
    "pros and cons", "trade-off", "tradeoff", "evaluate", "assess",
    "what are the implications", "think carefully",
]

_TECHNICAL_TERMS = frozenset({
    "machine learning", "neural network", "transformer", "gradient", "backprop",
    "distributed system", "consensus", "sharding", "replication", "latency",
    "throughput", "concurrency", "mutex", "semaphore", "deadlock", "race condition",
    "microservice", "event sourcing", "cqrs", "raft", "paxos", "cap theorem",
    "blockchain", "cryptography", "oauth", "jwt", "tls", "ssl", "cipher",
    "differential privacy", "homomorphic", "vector database", "embedding",
    "tokenization", "attention mechanism", "fine-tuning",
})

_SIMPLE_INDICATORS = frozenset({
    "what is", "define", "hello", "hi ", "thanks", "thank you",
    "how do you", "what does", "what are", "list the", "name the",
    "tell me about", "describe", "summarize", "give me an example",
    "translate", "what's the", "whats the",
})

_MULTI_STEP_PATTERNS = [
    re.compile(r"\bfirst\b.{0,60}\bthen\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(1\..*?2\.|step 1.*?step 2)", re.IGNORECASE | re.DOTALL),
    re.compile(r"\band then\b", re.IGNORECASE),
    re.compile(r"\bafter that\b", re.IGNORECASE),
    re.compile(r"\bfinally\b.{0,40}\b(do|make|create|build|run)\b", re.IGNORECASE | re.DOTALL),
]

_DEFAULT_WEIGHTS = {
    "tokenCount": 0.15,
    "codePresence": 0.20,
    "reasoningMarkers": 0.25,
    "technicalTerms": 0.15,
    "simpleIndicators": 0.15,
    "multiStepPatterns": 0.05,
    "questionComplexity": 0.05,
}

_DEFAULT_BOUNDARIES = {
    "simple_medium": 0.25,
    "medium_complex": 0.50,
    "complex_reasoning": 0.75,
}


# ─── Result dataclass ────────────────────────────────────────────────────────

@dataclass
class RoutingResult:
    model: str
    tier: str           # SIMPLE / MEDIUM / COMPLEX / REASONING / DIRECT
    score: float        # 0.0 – 1.0
    original_model: str


# ─── ComplexityScorer ────────────────────────────────────────────────────────

class ComplexityScorer:
    """Score prompt complexity across 7 dimensions with configurable weights."""

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        boundaries: dict[str, float] | None = None,
    ) -> None:
        self.weights = weights or dict(_DEFAULT_WEIGHTS)
        self.boundaries = boundaries or dict(_DEFAULT_BOUNDARIES)

    def score(self, messages: list[dict]) -> float:
        user_text = extract_user_text(messages)
        if not user_text:
            return 0.0

        text_lower = user_text.lower()
        tokens = text_lower.split()
        token_count = len(tokens)
        w = self.weights
        result = 0.0

        # 1. tokenCount
        wt = w.get("tokenCount", 0.15)
        if token_count < 15:
            result += wt * 0.0
        elif token_count < 50:
            result += wt * 0.3
        elif token_count < 150:
            result += wt * 0.6
        elif token_count < 400:
            result += wt * 0.85
        else:
            result += wt * 1.0

        # 2. codePresence
        wt = w.get("codePresence", 0.20)
        code_hits = sum(1 for kw in _CODE_KEYWORDS if kw in text_lower)
        result += wt * min(code_hits / 5.0, 1.0)

        # 3. reasoningMarkers (2+ → auto score 1.0)
        wt = w.get("reasoningMarkers", 0.25)
        reasoning_count = sum(1 for m in _REASONING_MARKERS if m in text_lower)
        if reasoning_count >= 2:
            return 1.0
        result += wt * min(reasoning_count, 1)

        # 4. technicalTerms
        wt = w.get("technicalTerms", 0.15)
        tech_hits = sum(1 for term in _TECHNICAL_TERMS if term in text_lower)
        result += wt * min(tech_hits / 3.0, 1.0)

        # 5. simpleIndicators (negative)
        wt = w.get("simpleIndicators", 0.15)
        simple_hits = sum(1 for ind in _SIMPLE_INDICATORS if ind in text_lower)
        result -= wt * min(simple_hits, 1)

        # 6. multiStepPatterns
        wt = w.get("multiStepPatterns", 0.05)
        multi_hits = sum(1 for p in _MULTI_STEP_PATTERNS if p.search(user_text))
        result += wt * min(multi_hits, 1)

        # 7. questionComplexity
        wt = w.get("questionComplexity", 0.05)
        question_marks = user_text.count("?")
        if question_marks >= 3:
            result += wt * 1.0
        elif question_marks == 2:
            result += wt * 0.5

        return max(0.0, min(1.0, result))

    def score_to_tier(self, score: float) -> str:
        b = self.boundaries
        if score < b.get("simple_medium", 0.25):
            return "SIMPLE"
        if score < b.get("medium_complex", 0.50):
            return "MEDIUM"
        if score < b.get("complex_reasoning", 0.75):
            return "COMPLEX"
        return "REASONING"


def extract_user_text(messages: list[dict]) -> str:
    parts: list[str] = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
    return " ".join(parts)
