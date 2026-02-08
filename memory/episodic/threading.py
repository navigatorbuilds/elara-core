# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Episodic threading — link related episodes, walk episode chains.
"""

from typing import List


class ThreadingMixin:
    """Mixin for narrative threading between episodes."""

    def link_episodes(self, episode_id: str, related_id: str) -> None:
        """Link two episodes as related."""
        ep1 = self.get_episode(episode_id)
        ep2 = self.get_episode(related_id)

        if ep1 and ep2:
            if related_id not in ep1.get("related_episodes", []):
                ep1["related_episodes"].append(related_id)
                self._save_episode(ep1)

            if episode_id not in ep2.get("related_episodes", []):
                ep2["related_episodes"].append(episode_id)
                self._save_episode(ep2)

    def get_episode_thread(self, episode_id: str, depth: int = 5) -> List[dict]:
        """Get the thread of episodes (previous -> current -> next)."""
        thread = []
        current_id = episode_id

        # Walk backwards
        backwards = []
        for _ in range(depth):
            ep = self.get_episode(current_id)
            if not ep:
                break
            backwards.append(ep)
            current_id = ep.get("continues_from")
            if not current_id:
                break

        thread = list(reversed(backwards))

        # Walk forwards from original
        current_id = episode_id
        for _ in range(depth):
            ep = self.get_episode(current_id)
            if not ep:
                break
            continued_by = ep.get("continued_by")
            if not continued_by:
                break
            next_ep = self.get_episode(continued_by)
            if next_ep:
                thread.append(next_ep)
            current_id = continued_by

        return thread
