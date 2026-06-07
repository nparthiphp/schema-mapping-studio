"""Field coverage analysis for generated JSONata expressions."""
import re
from dataclasses import dataclass

CANONICAL_FIELDS = [
    "event_id", "source", "timestamp_utc", "channel", "raw_intent",
    "intent_category", "sentiment_score", "handle_time_seconds",
    "resolved", "escalated", "customer_id", "metadata",
]


@dataclass
class FieldResult:
    field:  str
    status: str   # mapped | null | missing


@dataclass
class ValidationResult:
    coverage_pct:   float
    mapped_fields:  int
    null_fields:    int
    missing_fields: int
    field_details:  list[FieldResult]


def analyse_expression(expression: str) -> ValidationResult:
    """Static analysis of JSONata expression against canonical schema."""
    results: list[FieldResult] = []
    for field in CANONICAL_FIELDS:
        in_expr = f'"{field}"' in expression or f"'{field}'" in expression
        is_null  = bool(re.search(rf'"{field}"\s*:\s*null', expression))
        if not in_expr:
            status = "missing"
        elif is_null:
            status = "null"
        else:
            status = "mapped"
        results.append(FieldResult(field=field, status=status))

    mapped  = sum(1 for r in results if r.status == "mapped")
    nulled  = sum(1 for r in results if r.status == "null")
    missing = sum(1 for r in results if r.status == "missing")
    cov     = round((mapped / len(CANONICAL_FIELDS)) * 100, 1)

    return ValidationResult(
        coverage_pct=cov,
        mapped_fields=mapped,
        null_fields=nulled,
        missing_fields=missing,
        field_details=results,
    )
