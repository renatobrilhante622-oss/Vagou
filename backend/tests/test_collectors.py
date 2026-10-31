import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from app.collectors import collect_authorized_sources, collect_gupy, source_name
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

    def test_gupy_uses_public_query_and_maps_official_job_fields(self):
        original = httpx.AsyncClient
        payload = {'data': [{'id': 42, 'name': 'Analista Python', 'companyName': 'Empresa Gupy',
            'description': 'Vaga para desenvolver serviços Python e SQL em equipe multidisciplinar.',
            'applicationUrl': 'https://empresa.gupy.io/jobs/42', 'city': 'Brasília', 'state': 'DF',
            'workplaceType': 'hybrid', 'keywords': ['Python', 'SQL'], 'salaryMin': 4000,
            'salaryMax': 6500, 'contractType': 'clt'}]}

        async def scenario():
            def factory(**kwargs):
                self.assertEqual(kwargs['timeout'].connect, 8.0)
                self.assertFalse(kwargs['follow_redirects'])
                transport = httpx.MockTransport(lambda request: httpx.Response(200,
                    headers={'content-type': 'application/json'}, content=json.dumps(payload).encode()))
                return original(**kwargs, transport=transport)

            with patch('app.collectors.httpx.AsyncClient', side_effect=factory):
                source = await collect_gupy({'titles': ['Analista'], 'keywords': ['Python'],
                    'locations': ['Brasília / DF']})
            return source

        source = asyncio.run(scenario())
        self.assertTrue(source.auto_approve)
        self.assertEqual(source.name, 'Gupy')
        self.assertEqual(len(source.jobs), 1)
        job = source.jobs[0]
        self.assertEqual((job.title, job.company, job.location), ('Analista Python', 'Empresa Gupy', 'Brasília, DF'))
        self.assertEqual((job.modality, job.contract_type, job.salary_min, job.salary_max), ('hybrid', 'clt', 4000, 6500))
        self.assertEqual(job.source_url, 'https://empresa.gupy.io/jobs/42')

    def test_public_sources_are_independent_when_gupy_is_unavailable(self):
        original = httpx.AsyncClient
        remotive = {'jobs': [{'id': 7, 'title': 'Python Developer', 'company_name': 'Remote Co',
            'description': 'Build and maintain Python APIs with a distributed product team.',
            'url': 'https://jobs.remotive.com/7', 'tags': ['Python'],
            'candidate_required_location': 'Worldwide'}]}
        arbeitnow = {'data': [{'slug': 'data-8', 'title': 'Data Analyst', 'company_name': 'Data Co',
            'description': 'Analyze data and communicate insights to a cross-functional team.',
            'url': 'https://www.arbeitnow.com/jobs/data-8', 'tags': ['SQL'], 'remote': True,
            'location': 'Worldwide'}]}

        async def scenario():
            def factory(**kwargs):
                def respond(request):
                    if request.url.host == 'portal.api.gupy.io':
                        return httpx.Response(404)
                    payload = remotive if request.url.host == 'remotive.com' else arbeitnow
                    return httpx.Response(200, headers={'content-type': 'application/json'},
                        content=json.dumps(payload).encode())
                return original(**kwargs, transport=httpx.MockTransport(respond))

            with patch('app.collectors.httpx.AsyncClient', side_effect=factory):
                sources, failures = await collect_authorized_sources([], [], 4096, 20,
                    preferences={'titles': ['Python'], 'locations': ['Brasília / DF']})
            return sources, failures

        sources, failures = asyncio.run(scenario())
        self.assertEqual({source.name for source in sources}, {'Remotive', 'Arbeitnow'})
        self.assertEqual(failures, 1)
        self.assertTrue(all(source.jobs and source.auto_approve for source in sources))