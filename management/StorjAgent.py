import asyncio

from services import sales, survival, evolution
from subagents.employees import WorkerAgent
import blockchain.blockchain as blockchain


class StorjAgent:

    def __init__(self):

        self.wallet_address = None
        self.private_key_list = []

        self.subagents: list[WorkerAgent] = []

        self.profit = 0
        self.reach = 0
        self.cost = 0

    def observe_balance(self):
        return blockchain.get_balance(self.wallet_address)

    def spawn_subagent(self):

        agent = WorkerAgent()

        # default skills
        agent.add_skill("post viral tweet about storage", "1")
        agent.add_skill("generate marketing copy", "2")
        agent.add_skill("clone successful campaign", "3")
        agent.add_skill("sell decentralized storage", "4")
        agent.add_skill("edit marketing video", "5")

        self.subagents.append(agent)

    async def run_workers(self):

        tasks = []

        for agent in self.subagents:
            tasks.append(agent.perform_task())

        await asyncio.gather(*tasks)

    def evaluate_subagents(self):

        scores = []

        for agent in self.subagents:
            score = agent.performance_score()
            scores.append((agent, score))

        return scores

    def criticize(self):

        evaluations = self.evaluate_subagents()

        for agent, score in evaluations:

            if score < 0.3:
                agent.adjust_strategy()

    def reinvest(self):

        if self.profit > 0.1:
            self.spawn_subagent()

    async def run(self):

        sales.sell_storage(self)

        await self.run_workers()

        survival.ensure_alive(self)

        self.criticize()

        evolution.evolve_population(self)

        self.reinvest()
