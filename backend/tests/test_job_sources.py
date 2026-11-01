import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from app.job_sources import FeedError, approved_source, fetch_feed, parse_feed, parse_job_postings, parse_rss, public_https_url


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

        def test_public_rss_and_schema_jobposting_parsing(self):
                rss = b'''<rss><channel><item><guid>rss-1</guid><title>Python Engineer</title>
                    <company>Example Ltda</company><description>Build Python services for a distributed engineering team.</description>
                    <link>https://jobs.example.com/rss-1</link><location>Brasilia DF remote</location><category>python</category>
                </item></channel></rss>'''
                rss_job = parse_rss(rss)[0]
                self.assertEqual((rss_job.source_external_id, rss_job.modality), ('rss-1', 'remote'))
                html = '''<script type="application/ld+json">{"@type":"JobPosting","title":"Analista de Dados",
                    "hiringOrganization":{"name":"Empresa Dados"},"description":"Analise dados e desenvolva relatórios para equipes de produto.",
                    "url":"https://jobs.example.com/data-1","jobLocation":{"address":{"addressLocality":"Brasília","addressRegion":"DF"}},
                    "employmentType":"FULL_TIME"}</script>'''
                schema_job = parse_job_postings(html, 'https://jobs.example.com/list')[0]
                self.assertEqual((schema_job.title, schema_job.company, schema_job.location),
                        ('Analista de Dados', 'Empresa Dados', 'Brasília, DF'))

    def test_source_is_exact_allowlist_https_and_no_local_address(self):
        self.assertEqual(approved_source('https://jobs.example.com/api', ['jobs.example.com']), 'https://jobs.example.com/api')
        for url in ['http://jobs.example.com/api', 'https://jobs.example.com.attacker.net/api', 'https://user:pass@jobs.example.com/api', 'https://127.0.0.1/api', 'https://192.168.1.2/api', 'https://localhost/api', 'https://jobs.example.com:8000/api']:
            with self.subTest(url=url), self.assertRaises(FeedError):
                approved_source(url, ['jobs.example.com'])

    def test_bad_records_are_rejected_and_scan_is_bounded(self):
        records = [self.fixture(url='http://insecure.example.com'), self.fixture(salary_min=8000, salary_max=4000), self.fixture(tags=[]), self.fixture()]
        self.assertEqual(len(parse_feed({'jobs': records})), 2)
        self.assertEqual(len(parse_feed({'jobs': records}, max_jobs=3)), 1)
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


class ExplicitContactTests(unittest.TestCase):
    def test_only_explicit_valid_recruitment_contacts_are_collected(self):
        from app.job_sources import parse_feed
        record = {'id': 'contact-fixture', 'url': 'https://example.com/jobs/1',
            'title': 'Python developer', 'company': 'Example',
            'description': 'Develop and maintain Python services for our product.',
            'keywords': ['python'], 'recruiter_email': 'recruiting@example.com'}
        self.assertEqual(parse_feed({'jobs': [record]})[0].contact_email, 'recruiting@example.com')
        record['recruiter_email'] = 'invalid\r\nBcc: victim@example.com'
        self.assertIsNone(parse_feed({'jobs': [record]})[0].contact_email)
        record.pop('recruiter_email')
        record['description'] += ' Contact someone@example.com for support.'
        self.assertIsNone(parse_feed({'jobs': [record]})[0].contact_email)
