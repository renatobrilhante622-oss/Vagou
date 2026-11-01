import asyncio
import json
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import httpx

from app import collectors
from app.collectors import (BRAZILIAN_PORTALS, CollectedSource, collect_authorized_sources,
    collect_brazilian_portal, collect_gupy, parse_gupy_response,
    regional_search_channels, source_name)
from app.job_sources import ExternalJob, FeedError


def gupy_record(**updates):
    return {'id': 42, 'name': 'Analista de Suporte N2', 'careerPageName': 'Empresa Anunciante',
        'description': 'Responsabilidades: atendimento de chamados. Requisitos e qualificações: suporte técnico, Windows, Linux e redes. Informações adicionais: vale refeição.',
        'jobUrl': 'https://empresa.gupy.io/jobs/42', 'city': 'Brasília', 'state': 'Distrito Federal',
        'workplaceType': 'on-site', 'type': 'vacancy_type_effective', **updates}


def posting(url, city='Brasília', state='DF', country='BR'):
    return '<script type="application/ld+json">' + json.dumps({'@context': 'https://schema.org',
        '@type': 'JobPosting', 'title': 'Analista de Suporte', 'description': 'Atendimento de chamados. Requisitos: Windows e redes de computadores.',
        'hiringOrganization': {'name': 'Empresa Anunciante'}, 'jobLocation': {'address': {
            'addressLocality': city, 'addressRegion': state, 'addressCountry': country}}, 'url': url}) + '</script>'


class CollectorTests(unittest.TestCase):
    def setUp(self):
        collectors._source_cache.clear()

    def test_source_labels_cover_brazilian_portals(self):
        expected = {'Gupy', 'LinkedIn', 'Indeed', 'InfoJobs', 'Vagas.com.br', 'Catho', 'Programathor', 'Trabalha Brasil'}
        self.assertEqual({portal.name for portal in BRAZILIAN_PORTALS}, expected)
        self.assertEqual(source_name('https://careers.gupy.io/jobs'), 'Gupy')
        self.assertEqual(source_name('https://jobs.example.org/feed'), 'jobs.example.org')
        self.assertFalse(any(term in portal.origin for portal in BRAZILIAN_PORTALS for term in ['remotive', 'arbeitnow', 'jobicy']))

    def test_collects_configured_sources_independently_and_rejects_foreign_jobs(self):
        brazil = ExternalJob('1', 'Analista de Suporte', 'Empresa', 'Uma descrição real de atividades de suporte técnico.', 'Brasília / DF', 'onsite', ['suporte'], 2000, 3500, 'clt', 'https://jobs.example.org/1')
        foreign = ExternalJob('2', 'IT Support', 'Foreign', 'A real vacancy located in Munich, Germany.', 'Munich, Bavaria', 'onsite', ['support'], 0, 0, None, 'https://jobs.example.org/2')
        async def fake_fetch(url, *args):
            if url.endswith('/bad'):
                raise FeedError('blocked source')
            return [brazil, foreign]
        with patch('app.collectors.fetch_feed', side_effect=fake_fetch):
            sources, failures = asyncio.run(collect_authorized_sources(
                ['https://jobs.example.org/good', 'https://jobs.example.org/bad'], ['jobs.example.org'], 4096, 20))
        self.assertEqual(failures, 1)
        self.assertEqual(len(sources), 1)
        self.assertEqual([job.source_external_id for job in sources[0].jobs], ['1'])
        self.assertEqual((sources[0].jobs[0].city, sources[0].jobs[0].state, sources[0].jobs[0].country), ('Brasília', 'DF', 'BR'))

    def test_gupy_public_ssr_route_queries_candidate_city_and_parses_actual_requirements(self):
        original = httpx.AsyncClient
        observed = []
        payload = {'props': {'pageProps': {'initialJobList': {'data': [gupy_record()]}}}}
        html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'
        def factory(**kwargs):
            self.assertFalse(kwargs['follow_redirects'])
            def respond(request):
                observed.append(str(request.url))
                return httpx.Response(200, headers={'content-type': 'text/html'}, text=html)
            return original(**kwargs, transport=httpx.MockTransport(respond))
        with patch('app.collectors.httpx.AsyncClient', side_effect=factory):
            source = asyncio.run(collect_gupy({'titles': ['Suporte'], 'locations': ['Brasília / DF']}))
        self.assertEqual(len(source.jobs), 1)
        job = source.jobs[0]
        self.assertEqual((job.company, job.city, job.state, job.country, job.modality), ('Empresa Anunciante', 'Brasília', 'DF', 'BR', 'onsite'))
        self.assertIn('windows', job.keywords)
        self.assertIn('networking', job.keywords)
        self.assertNotIn('vale refeicao', job.keywords)
        self.assertIn('portal.gupy.io/job-search/term=Suporte&city=Bras', observed[0])
        self.assertNotIn('portal.api.gupy.io', observed[0])

    def test_gupy_rejects_foreign_expired_talent_pool_and_invalid_contact(self):
        payload = {'data': [gupy_record(city='Munich', state='Bavaria', country='DE'),
            gupy_record(applicationDeadline='2000-01-01T00:00:00Z'),
            gupy_record(type='vacancy_type_talent_pool'),
            gupy_record(contact_email='rh@example.com\r\nBcc: victim@example.com')]}
        jobs = parse_gupy_response(payload)
        self.assertEqual(len(jobs), 1)
        self.assertIsNone(jobs[0].contact_email)
        self.assertEqual(jobs[0].modality, 'onsite')

    def test_gupy_onsite_is_not_overridden_by_remote_support_activity(self):
        job = parse_gupy_response({'data': [gupy_record(description='Realizar suporte remoto aos usuários. Requisitos e qualificações: Windows e redes.')]})[0]
        self.assertEqual(job.modality, 'onsite')

    def test_sparse_specific_gupy_query_broadens_support_family_in_original_city(self):
        original = httpx.AsyncClient
        observed = []
        def factory(**kwargs):
            def respond(request):
                observed.append(unquote(str(request.url)))
                broad = 'term=suporte&city=Brasília' in unquote(str(request.url))
                records = [gupy_record(), gupy_record(id=43, city='Munich', state='Bavaria', country='DE')] if broad else []
                html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(
                    {'props': {'pageProps': {'initialJobList': {'data': records}}}}) + '</script>'
                return httpx.Response(200, headers={'content-type': 'text/html'}, text=html)
            return original(**kwargs, transport=httpx.MockTransport(respond))
        with patch('app.collectors.httpx.AsyncClient', side_effect=factory):
            source = asyncio.run(collect_gupy({'titles': ['Analista de Suporte N2'], 'locations': ['Brasília / DF']}))
        self.assertEqual(len(source.jobs), 1)
        self.assertEqual((source.jobs[0].city, source.jobs[0].state), ('Brasília', 'DF'))
        self.assertEqual(len(observed), 2)
        self.assertIn('term=Analista de Suporte N2&city=Brasília', observed[0])
        self.assertIn('term=suporte&city=Brasília', observed[1])

    def test_gupy_remote_requires_explicit_brazilian_scope_on_official_detail(self):
        original = httpx.AsyncClient
        def ssr(records):
            return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(
                {'props': {'pageProps': {'initialJobList': {'data': records}}}}) + '</script>'
        remote = [gupy_record(id=43, jobUrl='https://empresa.gupy.io/jobs/43', city='', state='', workplaceType='remote'),
                  gupy_record(id=44, jobUrl='https://empresa.gupy.io/jobs/44', city='', state='', workplaceType='remote')]
        def factory(**kwargs):
            def respond(request):
                if '/jobs/' in request.url.path:
                    html = posting(str(request.url), city='', state='', country='BR' if request.url.path.endswith('/43') else 'DE')
                    html = html.replace('"url":', '"jobLocationType": "TELECOMMUTE", "url":')
                else:
                    html = ssr(remote if 'workplaceTypes' in request.url.path else [gupy_record()])
                return httpx.Response(200, headers={'content-type': 'text/html'}, text=html)
            return original(**kwargs, transport=httpx.MockTransport(respond))
        with patch('app.collectors.httpx.AsyncClient', side_effect=factory):
            source = asyncio.run(collect_gupy({'titles': ['Suporte'], 'locations': ['Brasília / DF'], 'modalities': ['remote', 'onsite']}))
        self.assertEqual(len(source.jobs), 2)
        self.assertEqual({job.country for job in source.jobs}, {'BR'})
        verified_remote = next(job for job in source.jobs if job.modality == 'remote')
        self.assertEqual((verified_remote.location, verified_remote.source_url), ('Remoto Brasil', 'https://empresa.gupy.io/jobs/43'))

    def test_optional_remote_outage_keeps_verified_regional_gupy_jobs(self):
        original = httpx.AsyncClient
        html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(
            {'props': {'pageProps': {'initialJobList': {'data': [gupy_record()]}}}}) + '</script>'
        def factory(**kwargs):
            def respond(request):
                if 'workplaceTypes' in request.url.path:
                    return httpx.Response(503)
                return httpx.Response(200, headers={'content-type': 'text/html'}, text=html)
            return original(**kwargs, transport=httpx.MockTransport(respond))
        with patch('app.collectors.httpx.AsyncClient', side_effect=factory):
            source = asyncio.run(collect_gupy({'titles': ['Suporte'], 'locations': ['Brasília / DF'], 'modalities': ['remote']}))
        self.assertEqual(len(source.jobs), 1)
        self.assertEqual(source.jobs[0].city, 'Brasília')

    def test_portal_index_fetches_official_details_and_ignores_external_or_private_links(self):
        portal = next(portal for portal in BRAZILIAN_PORTALS if portal.name == 'Vagas.com.br')
        official = 'https://www.vagas.com.br/vagas/v42/analista-de-suporte'
        index = '<a href="https://attacker.example/vagas/v43">Vaga indevida</a><a href="http://127.0.0.1/vagas/v44">Privado</a><a href="' + official + '">Analista de Suporte</a>'
        original = httpx.AsyncClient
        requests = []
        def factory(**kwargs):
            def respond(request):
                requests.append(str(request.url))
                return httpx.Response(200, headers={'content-type': 'text/html'}, text=posting(official) if str(request.url) == official else index)
            return original(**kwargs, transport=httpx.MockTransport(respond))
        with patch('app.collectors.httpx.AsyncClient', side_effect=factory):
            source = asyncio.run(collect_brazilian_portal(portal, {'titles': ['Suporte'], 'locations': ['Brasília / DF']}))
        self.assertEqual(len(source.jobs), 1)
        self.assertEqual(source.jobs[0].source_url, official)
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(urlsplit(url).hostname == 'www.vagas.com.br' for url in requests))

    def test_redirect_to_another_host_is_rejected_without_following_it(self):
        original = httpx.AsyncClient
        observed = []
        def factory(**kwargs):
            def respond(request):
                observed.append(str(request.url))
                return httpx.Response(302, headers={'location': 'https://attacker.example/private'})
            return original(**kwargs, transport=httpx.MockTransport(respond))
        with patch('app.collectors.httpx.AsyncClient', side_effect=factory), self.assertRaises(FeedError):
            asyncio.run(collect_gupy({'titles': ['Suporte']}))
        self.assertEqual(len(observed), 1)

    def test_all_portals_are_independent_and_outage_keeps_eight_honest_search_channels(self):
        async def unavailable(*args, **kwargs):
            raise httpx.ConnectError('publisher unavailable')
        with patch('app.collectors.collect_brazilian_portal', side_effect=unavailable):
            sources, failures = asyncio.run(collect_authorized_sources([], [], 4096, 20,
                preferences={'titles': ['Suporte'], 'locations': ['Brasília / DF']}))
        self.assertEqual(failures, 8)
        self.assertEqual(sum(len(source.jobs) for source in sources), 0)
        channels = [channel for source in sources for channel in source.search_channels]
        self.assertEqual({channel.source_name for channel in channels}, {portal.name for portal in BRAZILIAN_PORTALS})
        self.assertTrue(all(channel.location == 'Brasília / DF' and channel.query == 'Suporte' for channel in channels))
        self.assertTrue(all(channel.external_url.startswith('https://') and channel.destination_channel == 'portal_search' for channel in channels))

    def test_one_working_brazilian_portal_survives_other_source_failures_and_cache(self):
        calls = []
        async def collect(portal, *args, **kwargs):
            calls.append(portal.name)
            if portal.name != 'Gupy':
                raise httpx.HTTPStatusError('blocked', request=httpx.Request('GET', portal.origin), response=httpx.Response(403))
            return CollectedSource('Gupy', parse_gupy_response({'data': [gupy_record()]}), True)
        async def scenario():
            prefs = {'titles': ['Suporte'], 'locations': ['Brasília / DF']}
            with patch('app.collectors.collect_brazilian_portal', side_effect=collect):
                first = await collect_authorized_sources([], [], 4096, 20, preferences=prefs)
                second = await collect_authorized_sources([], [], 4096, 20, preferences=prefs)
            return first, second
        first, second = asyncio.run(scenario())
        self.assertEqual(first[1], 7)
        self.assertEqual(sum(len(source.jobs) for source in first[0]), 1)
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 8)

    def test_regional_search_urls_preserve_real_city_and_role(self):
        channels = regional_search_channels({'titles': ['Analista de Suporte'], 'locations': ['Goiânia / GO']})
        self.assertEqual(len(channels), 8)
        for channel in channels:
            self.assertEqual(channel.query, 'Analista de Suporte')
            self.assertNotIn('google.com', channel.external_url)
        gupy = next(channel for channel in channels if channel.source_name == 'Gupy')
        self.assertIn('city=Goiânia', unquote(gupy.external_url))
        infojobs = next(channel for channel in channels if channel.source_name == 'InfoJobs')
        self.assertIn('/empregos-em-goias.aspx?', infojobs.external_url)
