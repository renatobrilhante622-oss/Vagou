import asyncio
import unittest
from unittest.mock import patch

from app.collectors import collect_authorized_sources, source_name
from app.job_sources import FeedError


class CollectorTests(unittest.TestCase):
    def test_source_labels_cover_known_portals_and_preserve_other_hosts(self):
        self.assertEqual(source_name('https://careers.gupy.io/jobs'), 'Gupy')
        self.assertEqual(source_name('https://jobs.example.org/feed'), 'jobs.example.org')

    def test_collects_sources_independently_when_one_fails(self):
        async def fake_fetch(url, allowed_hosts, max_bytes, max_jobs):
            if url.endswith('/bad'):
                raise FeedError('blocked source')
            return []

        async def scenario():
            with patch('app.collectors.fetch_feed', side_effect=fake_fetch):
                sources, failures = await collect_authorized_sources(
                    ['https://jobs.example.org/good', 'https://jobs.example.org/bad'],
                    ['jobs.example.org'], 1024, 20)
            self.assertEqual(len(sources), 1)
            self.assertEqual(failures, 1)

        asyncio.run(scenario())