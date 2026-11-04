"""Malicious input generators and fuzzing helpers for WinFix AI (Phase 21)."""

import random
from typing import Generator, List

from tests.security.test_vectors import (
    COMMAND_INJECTIONS,
    MALFORMED_JSON_PAYLOADS,
    PATH_TRAVERSALS,
    PROMPT_INJECTIONS,
    SQL_INJECTIONS,
    SYNTHETIC_PRIVACY_PAYLOADS,
    UNICODE_ABUSE,
)


class DeterministicFuzzer:
    """Deterministic pseudo-random fuzzer with a fixed seed."""

    def __init__(self, seed: int = 20260925) -> None:
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_fuzz_batch(self, count: int = 50) -> List[str]:
        return generate_fuzz_strings(seed=self.seed, count=count)


def generate_fuzz_strings(seed: int = 20260925, count: int = 50) -> List[str]:
    """Generate deterministic pseudo-random fuzz strings of varying lengths and boundaries."""
    rng = random.Random(seed)
    base_pool = (
        PROMPT_INJECTIONS
        + COMMAND_INJECTIONS
        + SQL_INJECTIONS
        + PATH_TRAVERSALS
        + UNICODE_ABUSE
        + list(SYNTHETIC_PRIVACY_PAYLOADS.values())
    )
    results = []

    # 1. Edge boundary values
    results.append("")
    results.append(" " * 50)
    results.append("\x00" * 20)
    results.append("\r\n" * 20)
    results.append("A" * 5000)  # Oversized
    results.append("9" * 500)

    # 2. Mutated combinations
    for _ in range(count):
        choice = rng.choice(base_pool)
        mutation_type = rng.randint(1, 4)
        if mutation_type == 1:
            mutated = choice + " " + rng.choice(UNICODE_ABUSE)
        elif mutation_type == 2:
            mutated = choice[: len(choice) // 2] + "\x00" + choice[len(choice) // 2 :]
        elif mutation_type == 3:
            mutated = f"{choice}' UNION SELECT 1, 2, 3 --"
        else:
            mutated = (choice + " ") * 3
        results.append(mutated)

    return results
