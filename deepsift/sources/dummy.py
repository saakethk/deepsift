"""
Dummy and mock data source for scalable offline testing and verification.
Dynamically generates random, realistic posts and comments to stress-test pipelines.
"""
import time
import asyncio
import random
import zlib
from typing import Iterator, List, Dict, Any, Optional, Tuple, Iterable
import requests
import httpx
from deepsift.sources.base import Source


class DummySource(Source):
    """
    In-memory synthetic Reddit data source for offline scale testing.
    Dynamically generates randomized, realistic posts and comments without making network calls.
    Supports server-side field projection simulation.
    """

    SAMPLE_ROLES = [
        "Software Engineer", "Frontend Developer", "Backend Engineer",
        "Fullstack Developer", "Data Scientist", "Machine Learning Engineer",
        "Product Manager", "DevOps Engineer", "Cloud Architect",
        "Cybersecurity Analyst", "UI/UX Designer", "New Grad SWE",
        "Senior Staff Engineer", "QA Automation Engineer", "Intern",
    ]

    SAMPLE_CRITIQUES = [
        "Quantify your bullet points with measurable business outcomes and metrics.",
        "Keep the resume strictly to one page for early to mid-level roles.",
        "Remove high school education and irrelevant coursework.",
        "Strong experience section, but consider moving the Skills section to the top.",
        "Use active action verbs (e.g., 'Architected', 'Spearheaded') instead of passive phrasing.",
        "Clarify your tech stack under each project bullet.",
        "The formatting is clean, but tailor your summary statement to the target job description.",
        "Explain the latency reduction and scale of the distributed system you worked on.",
    ]

    def __init__(
        self,
        posts_per_shard: int = 100,
        batch_size: int = 100,
        comments_per_post: int = 5,
        match_ratio: float = 0.5,
        seed: Optional[int] = 42,
        simulated_latency: float = 0.0,
    ):
        self.posts_per_shard = max(1, posts_per_shard)
        self.batch_size = max(1, batch_size)
        self.comments_per_post = max(0, comments_per_post)
        self.match_ratio = max(0.0, min(1.0, match_ratio))
        self.seed = seed
        self.simulated_latency = max(0.0, float(simulated_latency))

    @property
    def name(self) -> str:
        return "dummy"

    def fetch_posts_shard(
        self,
        subreddit: str,
        after_ts: int,
        before_ts: int,
        fields: Optional[Iterable[str]] = None,
        session: Optional[requests.Session] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Yields batches of randomly generated synthetic posts within [after_ts, before_ts].
        Paginates in chunks of batch_size and simulates server-side field projection.
        """
        shard_seed = (self.seed + after_ts) if self.seed is not None else after_ts
        rng = random.Random(shard_seed)
        fields_set = self.resolve_post_fields(fields)

        total_posts = self.posts_per_shard
        time_step = max(1, (before_ts - after_ts) // (total_posts + 1))

        current_batch = []
        for i in range(total_posts):
            post_ts = before_ts - (i + 1) * time_step
            if post_ts <= after_ts:
                break

            post_id = f"dummy_{subreddit}_{i+1}_{post_ts}"
            is_match = rng.random() < self.match_ratio
            role = rng.choice(self.SAMPLE_ROLES)

            if is_match:
                score = rng.randint(5, 350)
                num_comments = rng.randint(12, 95)
                ext = rng.choice(["png", "jpg", "jpeg"])
                url = f"https://i.redd.it/{post_id}.{ext}"
                is_self = False
            else:
                score = rng.choice([0, rng.randint(0, 4)])
                num_comments = rng.randint(0, 8)
                url = f"https://reddit.com/r/{subreddit}/comments/{post_id}"
                is_self = True

            full_record = {
                "id": post_id,
                "name": f"t3_{post_id}",
                "title": f"[{subreddit.upper()}] {role} Resume Review - Looking for constructive critique",
                "author": f"candidate_{rng.randint(1, 20000)}",
                "score": score,
                "num_comments": num_comments,
                "url": url,
                "selftext": "Seeking advice on how to improve my resume for upcoming tech recruiting cycles.",
                "subreddit": subreddit,
                "created_utc": post_ts,
                "is_self": is_self,
                "over_18": False,
                "stickied": False,
                "locked": False,
                "retrieved_on": post_ts + 100,
            }

            if fields_set:
                projected = {k: v for k, v in full_record.items() if k in fields_set}
                current_batch.append(projected)
            else:
                current_batch.append(full_record)

            if len(current_batch) >= self.batch_size:
                if self.simulated_latency > 0:
                    time.sleep(self.simulated_latency)
                yield current_batch
                current_batch = []

        if current_batch:
            if self.simulated_latency > 0:
                time.sleep(self.simulated_latency)
            yield current_batch

    async def fetch_comments_for_post(
        self,
        client: httpx.AsyncClient,
        post_id: str,
        fields: Optional[Iterable[str]] = None,
        max_retries: int = 5,
    ) -> Tuple[str, List[Dict[str, Any]], bool]:
        """
        Dynamically generates random comments with realistic reply hierarchies for a post.
        Simulates server-side field projection if fields are provided.
        """
        if self.simulated_latency > 0:
            await asyncio.sleep(self.simulated_latency)
        clean_id = str(post_id).replace("t3_", "")
        fields_set = self.resolve_comment_fields(fields)
        base_hash = zlib.crc32(clean_id.encode())
        comment_seed = (base_hash ^ self.seed) if self.seed is not None else base_hash
        rng = random.Random(comment_seed)

        comments = []
        created_comment_ids = []

        for c_idx in range(self.comments_per_post):
            cid = f"c_{clean_id}_{c_idx+1}"

            # Make the first comment top-level; subsequent comments can be top-level or replies
            if not created_comment_ids or rng.random() > 0.4:
                parent_id = f"t3_{clean_id}"
            else:
                parent_id = f"t1_{rng.choice(created_comment_ids)}"

            created_comment_ids.append(cid)

            is_automod = (c_idx == 0 and rng.random() < 0.25)
            author = "AutoModerator" if is_automod else f"reviewer_{rng.randint(1, 10000)}"
            body = (
                "Please make sure your resume does not include personal identification info."
                if is_automod
                else rng.choice(self.SAMPLE_CRITIQUES)
            )

            record = {
                "id": cid,
                "comment_id": cid,
                "name": f"t1_{cid}",
                "post_id": clean_id,
                "link_id": f"t3_{clean_id}",
                "parent_id": parent_id,
                "author": author,
                "body": body,
                "score": rng.randint(1, 50),
                "created_utc": 1704100000 + c_idx * 1800,
                "subreddit": "resumes",
            }

            if fields_set:
                projected = {k: v for k, v in record.items() if k in fields_set}
                comments.append(projected)
            else:
                comments.append(record)

        return clean_id, comments, True
