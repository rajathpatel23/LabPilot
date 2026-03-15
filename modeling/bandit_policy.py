from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple

import numpy as np


@dataclass
class UCB1Bandit:
    c: float = 1.0
    counts: Dict[int, int] = field(default_factory=dict)
    reward_sums: Dict[int, float] = field(default_factory=dict)
    total_pulls: int = 0

    def update(self, action: int, reward: float) -> None:
        self.total_pulls += 1
        self.counts[action] = self.counts.get(action, 0) + 1
        self.reward_sums[action] = self.reward_sums.get(action, 0.0) + reward

    def mean_reward(self, action: int) -> float:
        n = self.counts.get(action, 0)
        if n == 0:
            return 0.0
        return self.reward_sums[action] / n

    def score(self, action: int) -> float:
        n = self.counts.get(action, 0)
        if n == 0:
            return float("inf")
        mean = self.mean_reward(action)
        bonus = self.c * math.sqrt(math.log(max(1, self.total_pulls)) / n)
        return mean + bonus

    def select(self, candidate_actions: Iterable[int]) -> Tuple[int, float]:
        best_action = None
        best_score = -float("inf")
        for action in candidate_actions:
            s = self.score(action)
            if s > best_score:
                best_score = s
                best_action = action
        if best_action is None:
            raise ValueError("No candidate actions provided to bandit select().")
        return best_action, best_score


@dataclass
class LinearUCBBandit:
    dim: int
    alpha: float = 1.0
    lambda_reg: float = 1.0
    A: np.ndarray = field(init=False)
    b: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.A = self.lambda_reg * np.eye(self.dim)
        self.b = np.zeros(self.dim)

    def theta(self) -> np.ndarray:
        return np.linalg.solve(self.A, self.b)

    def score(self, x: np.ndarray) -> float:
        x = np.asarray(x).reshape(-1)
        A_inv_x = np.linalg.solve(self.A, x)
        exploit = float(np.dot(self.theta(), x))
        explore = float(self.alpha * math.sqrt(np.dot(x, A_inv_x)))
        return exploit + explore

    def update(self, x: np.ndarray, reward: float) -> None:
        x = np.asarray(x).reshape(-1)
        self.A += np.outer(x, x)
        self.b += reward * x

    def select(
        self, candidate_actions: Iterable[int], contexts: Dict[int, np.ndarray]
    ) -> Tuple[int, float]:
        best_action = None
        best_score = -float("inf")
        for action in candidate_actions:
            s = self.score(contexts[action])
            if s > best_score:
                best_score = s
                best_action = action
        if best_action is None:
            raise ValueError("No candidate actions provided to contextual bandit select().")
        return best_action, best_score

