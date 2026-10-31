import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from app.job_sources import FeedError, approved_source, fetch_feed, parse_feed, public_https_url


class JobSourcesTests(unittest.TestCase):
    def fixture(self, **changes):
        return {**{'id': 12, 'title': 'Python Developer', 'company_name': 'Example',
            'description': '<p>Develop reliable Python services with a collaborative team.</p>',
            'url': 'https://jobs.example.com/jobs/12', 'tags': ['Python', 'SQL'],
            'salary': '$90,000 USD per year', 'candidate_required_location': 'Brasil'}, **changes}

    def test_official_json_shape_and_html_removed(self):
        result = parse_feed({'jobs': [self.fixture()]})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].keywords, ['python', 'sql'])
        self.assertNotIn('<p>', result[0].description)
        self.assertEqual(result[0].salary_max, 0)
        self.assertEqual(result[0].modality, 'remote')
        self.assertIsNone(result[0].contract_type)

    def test_supported_contract_type_is_retained(self):
        job = parse_feed({'jobs': [self.fixture(contract_type='clt')]})[0]
        self.assertEqual(job.contract_type, 'clt')

    def test_source_is_exact_allowlist_https_and_no_local_address(self):
        self.assertEqual(approved_source('https://jobs.example.com/api', ['jobs.example.com']), 'https://jobs.example.com/api')
        for url in ['http://jobs.example.com/api', 'https://jobs.example.com.attacker.net/api', 'https://user:pass@jobs.example.com/api', 'https://127.0.0.1/api', 'https://192.168.1.2/api', 'https://localhost/api', 'https://jobs.example.com:8000/api']:
            with self.subTest(url=url), self.assertRaises(FeedError):
                approved_source(url, ['jobs.example.com'])

    def test_bad_records_are_rejected_and_scan_is_bounded(self):
        records = [self.fixture(url='http://insecure.example.com'), self.fixture(salary_min=8000, salary_max=4000), self.fixture(tags=[]), self.fixture()]
        self.assertEqual(len(parse_feed({'jobs': records})), 1)
        self.assertEqual(len(parse_feed({'jobs': records}, max_jobs=3)), 0)
        with self.assertRaises(FeedError):
            parse_feed({'not_jobs': []})

    def test_network_body_limit_and_no_redirect_following(self):
        original = httpx.AsyncClient
        async def scenario():
            response = json.dumps({'jobs': [self.fixture()]}).encode()
            def factory(**kwargs):
                self.assertFalse(kwargs['follow_redirects'])
                return original(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={'content-type': 'application/json'}, content=response)))
            with patch('app.job_sources.httpx.AsyncClient', side_effect=factory):
                jobs = await fetch_feed('https://jobs.example.com/api', ['jobs.example.com'])
                self.assertEqual(len(jobs), 1)
                with self.assertRaises(FeedError):
                    await fetch_feed('https://jobs.example.com/api', ['jobs.example.com'], max_bytes=8)
        asyncio.run(scenario())
