import random
import asyncio

from services.sales import work, evaluate_task
from services.skill_registry import SKILL_REGISTRY


class WorkerAgent:

    # Skill IDs
    # 1 = Twitter
    # 2 = Openrouter
    # 3 = cloning_ct
    # 4 = Storage
    # 5 = video_handling

    def __init__(self):
        self.skills: dict[str, str] = {}  # id -> prompt
        self.score_history: dict[str, int] = {}
        self.strategy: str | None = None

        self.revenue = 0
        self.cost = 0
        self.reach = 0
        self.score = 0

    async def perform_task(self):

        if not self.strategy:
            return

        task_id = self.strategy
        prompt = self.skills.get(task_id)

        if prompt is None:
            return

        skill_name = SKILL_REGISTRY.get(task_id)

        completion = work(skill_name, prompt)

        if completion == 0:
            print(f"Task {task_id} failed", flush=True)
            return

        job_id = completion["id"]
        task_data = completion["link"]

        # simulate waiting for results
        await asyncio.sleep(3600)

        task_result = evaluate_task(job_id, task_data)

        self.revenue += float(task_result["rev"])
        self.reach += int(task_result["reach"])

    def add_skill(self, skill_prompt: str, id: str):
        self.skills[id] = skill_prompt

        if self.strategy is None:
            self.adjust_strategy()

    def remove_skill(self, id: str):

        if id in self.skills:
            del self.skills[id]

            if self.strategy == id:
                self.adjust_strategy()

    def add_cost(self, amount: float):
        self.cost += amount

    def performance_score(self):

        if self.cost == 0:
            return self.revenue

        return self.reach + (self.revenue * 100) - self.cost

    def set_score(self, number: int):

        self.score = number
        self.set_score_history()

    def set_score_history(self):

        if self.strategy:
            self.score_history[self.strategy] = self.score

    def adjust_strategy(self):

        if not self.skills:
            self.strategy = None
            return

        # choose best performing skill if available
        if self.score_history:

            best = max(self.score_history, key=self.score_history.get)

            if best in self.skills:
                self.strategy = best
                return

        # fallback random
        self.strategy = random.choice(list(self.skills.keys()))
