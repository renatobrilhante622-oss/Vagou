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
        self.assertIsNone(schema_job.contract_type)

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

    def test_hiring_description_contact_is_extracted_without_legal_or_script_contacts(self):
        from app.job_sources import recruitment_contact
        self.assertEqual(recruitment_contact({}, '<p>Envie seu currículo para <a href="mailto:rh@example.com">rh@example.com</a>.</p>'), 'rh@example.com')
        self.assertIsNone(recruitment_contact({}, '<p>Dúvidas sobre o processo seletivo: suporte@example.com.</p>'))
        self.assertIsNone(recruitment_contact({}, '<script>curriculos@example.com</script><p>Atue na área de recrutamento.</p>'))
        self.assertIsNone(recruitment_contact({'hiringOrganization': {'email': 'support@example.com'}}, 'Atue na equipe de RH e seleção de candidatos.'))
        self.assertEqual(recruitment_contact({'applicationContact': {'email': 'selecao@example.com'}}), 'selecao@example.com')


class BrazilianMetadataTests(unittest.TestCase):
    def posting(self, **changes):
        return {**{'@type': 'JobPosting', 'title': 'Analista de Suporte',
            'hiringOrganization': {'name': 'Empresa de Tecnologia'},
            'description': 'Modalidade: Presencial. Prestar suporte remoto aos clientes e manter sistemas internos.',
            'url': 'https://jobs.example.com/suporte',
            'jobLocation': {'address': {'addressLocality': 'Brasília', 'addressRegion': 'Distrito Federal', 'addressCountry': 'BR'}},
            'skills': ['Suporte', 'Sistemas'], 'employmentType': 'FULL_TIME'}, **changes}

    def parse(self, posting):
        return parse_job_postings('<script type="application/ld+json">' + json.dumps(posting) + '</script>', 'https://jobs.example.com/list')

    def test_structured_country_state_and_declared_modality_are_retained(self):
        job = self.parse(self.posting())[0]
        self.assertEqual((job.city, job.state, job.country, job.modality), ('Brasília', 'DF', 'BR', 'onsite'))
        self.assertEqual(job.location, 'Brasília, DF')
        self.assertEqual(job.values()['state'], 'DF')
        self.assertIsNone(job.contract_type)  # FULL_TIME does not prove CLT.

    def test_foreign_provenance_is_not_disguised_by_a_similarly_named_city(self):
        posting = self.posting(jobLocation={'address': {'addressLocality': 'Brasília', 'addressRegion': 'Bavaria', 'addressCountry': 'Germany'}})
        job = self.parse(posting)[0]
        self.assertEqual(job.country, 'DE')
        self.assertIsNone(job.state)
        self.assertIn('Bavaria', job.location)

    def test_remote_brazil_eligibility_is_explicit_and_foreign_salary_not_guessed(self):
        job = self.parse(self.posting(jobLocation={}, jobLocationType='TELECOMMUTE',
            applicantLocationRequirements={'@type': 'Country', 'name': 'Brazil'},
            baseSalary={'currency': 'USD', 'value': {'minValue': 3000, 'maxValue': 5000}}))[0]
        self.assertEqual((job.location, job.country, job.modality), ('Remoto Brasil', 'BR', 'remote'))
        self.assertEqual((job.salary_min, job.salary_max), (0, 0))

    def test_expired_vacancy_is_not_republished(self):
        self.assertEqual(self.parse(self.posting(validThrough='2001-01-01')), [])

    def test_malformed_control_characters_and_escaped_markup_are_bounded_plain_text(self):
        document = json.dumps(self.posting(description='Atue no atendimento e suporte de sistemas.\r\nBenefícios informados no anúncio.'))
        document = document.replace('\\r\\n', '\r\n')
        job = parse_job_postings('<script type="application/ld+json">' + document + '</script>', 'https://jobs.example.com/list')[0]
        self.assertIn('Benefícios informados', job.description)
        from app.job_sources import plain
        self.assertEqual(plain('&lt;p&gt;Suporte técnico&lt;/p&gt;', 100), 'Suporte técnico')

    def test_json_location_and_contact_support_brazilian_fields(self):
        fixture = JobSourcesTests().fixture(city='Goiânia', state='Goiás', country='BR', location=None,
            modality='híbrido', contact_email='rh@example.com')
        job = parse_feed({'jobs': [fixture]})[0]
        self.assertEqual((job.city, job.state, job.country, job.modality), ('Goiânia', 'GO', 'BR', 'hybrid'))
        self.assertEqual(job.contact_email, 'rh@example.com')

    def test_gupy_entity_encoded_json_declares_remote_brazil_in_nested_property(self):
        from html import escape
        record = self.posting(description='Atendimento técnico e suporte aos sistemas de clientes no Brasil.',
            jobLocation={'@type': 'Place',
                'additionalProperty': {'@type': 'PropertyValue', 'value': 'TELECOMMUTE'},
                'address': {'streetAddress': 'Brasil', 'addressCountry': 'Brasil'}})
        encoded = escape(json.dumps(record, ensure_ascii=False), quote=True)
        jobs = parse_job_postings('<script type="application/ld+json">' + encoded + '</script>',
                                  'https://company.gupy.io/jobs/remote-br')
        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0].modality, jobs[0].country, jobs[0].location),
                         ('remote', 'BR', 'Remoto Brasil'))

    def test_valid_json_with_description_entities_is_not_whole_document_unescaped(self):
        record = self.posting(description='Atendimento técnico &quot;especializado&quot; aos clientes e suporte a sistemas.')
        jobs = self.parse(record)
        self.assertEqual(len(jobs), 1)
        self.assertIn('"especializado"', jobs[0].description)


def test_clean_description_normalizes_advertisement_without_script_or_collapsed_heading():
    from app.job_sources import clean_description, recruitment_contact
    description = clean_description('<h2>Descrição Geral:</h2>Atendimento <b>técnico</b><script>private()</script><p>Recrutamento:rh@example.com</p>')
    assert '<' not in description and 'private' not in description
    assert 'Geral: Atendimento' in description
    assert recruitment_contact({}, description) == 'rh@example.com'
