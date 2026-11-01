import unittest
from types import SimpleNamespace
from app.matching import (advertised_skills, compatible_region, dedupe_reasons, eligible,
    evaluate_job, filter_reason, is_brazilian_job, job_location_details, match)


class MatchingTests(unittest.TestCase):
    def test_boundary_categories(self):
        required = ['python', 'sql', 'docker', 'redis']
        for skills, score, category in [([], 0, 'discarded'), (['python'], 25, 'discarded'), (['python', 'sql'], 50, 'observation'), (['python', 'sql', 'docker'], 75, 'high'), (required, 100, 'high')]:
            with self.subTest(score=score):
                result = match(skills, required)
                self.assertEqual((result['match_score'], result['category']), (score, category))
                self.assertEqual(len(result['missing_skills']), 4 - len(skills))

    def test_accents_duplicates_and_empty_requirements(self):
        self.assertEqual(match(['GESTÃO', 'gestao'], ['Gestão', 'gestão'])['match_score'], 100)
        self.assertEqual(match(['python'], [])['category'], 'discarded')
        self.assertEqual(match(['java'], ['javascript'])['match_score'], 0)

    def test_filters_and_remote_location(self):
        job = SimpleNamespace(title='Desenvolvedor Python', description='Vaga com contrato CLT', keywords=['python'], contract_type='clt', salary_max=6000, modality='remote', location='São Paulo')
        preferences = {'min_salary': 5000, 'titles': ['python'], 'modalities': ['remote'], 'locations': ['Recife']}
        self.assertTrue(eligible(job, preferences))
        self.assertFalse(eligible(job, {**preferences, 'min_salary': 7000}))
        job.location = 'Europe, USA, Canada'
        self.assertFalse(eligible(job, preferences))
        job.location = 'São Paulo'
        self.assertTrue(eligible(job, {**preferences, 'contract_types': ['clt'], 'keywords': ['contrato']}))
        self.assertFalse(eligible(job, {**preferences, 'contract_types': ['pj']}))
        self.assertFalse(eligible(job, {**preferences, 'keywords': ['cobol']}))
        job.modality = 'onsite'
        self.assertFalse(eligible(job, {**preferences, 'modalities': ['onsite']}))
        job.location = 'Belém, PA'
        self.assertFalse(eligible(job, {**preferences, 'modalities': ['onsite']}))
        job.location = 'RECIFE / PE'
        self.assertTrue(eligible(job, {**preferences, 'locations': ['Recife, PE'], 'modalities': ['onsite']}))
        self.assertTrue(eligible(job, {**preferences, 'locations': ['Recife'], 'modalities': ['onsite']}))

    def test_filter_reason_explains_rejection(self):
        job = SimpleNamespace(title='Analista de dados', description='SQL e Python', keywords=['python'],
            contract_type='clt', salary_max=4000, modality='onsite', location='Recife / PE')
        self.assertEqual(filter_reason(job, {'min_salary': 5000}), 'Salário abaixo do piso definido.')
        self.assertEqual(filter_reason(job, {'keywords': ['Java']}), 'Palavras-chave não encontradas.')

    def test_evaluate_job_returns_strong_possible_and_discarded_reasons(self):
        job = SimpleNamespace(title='Analista Python', description='Python, SQL, Docker e Redis',
            keywords=['python', 'sql', 'docker', 'redis'],
            salary_max=6000, modality='hybrid', location='Recife / PE', contract_type='clt')
        preferences = {'titles': ['Analista'], 'keywords': ['python'], 'locations': ['Recife / PE'],
            'modalities': ['hybrid'], 'min_salary': 5000, 'contract_types': ['clt']}
        strong = evaluate_job(job, ['python', 'sql', 'docker', 'redis'], preferences)
        high_preference_partial_skills = evaluate_job(job, ['python', 'sql', 'docker'], preferences)
        possible = evaluate_job(job, ['python'], {**preferences, 'titles': ['Engenheiro'], 'locations': ['Brasília / DF']})
        discarded = evaluate_job(job, [], {**preferences, 'titles': ['Engenheiro'], 'keywords': ['java'],
            'locations': ['Brasília / DF'], 'modalities': ['onsite'], 'contract_types': ['pj'], 'min_salary': 10000})
        self.assertEqual(strong['category'], 'strong')
        self.assertEqual(strong['match_score'], 100)
        self.assertGreaterEqual(high_preference_partial_skills['match_score'], 70)
        self.assertEqual(high_preference_partial_skills['category'], 'strong')
        self.assertEqual(possible['category'], 'possible')
        self.assertTrue(any('Cidade/UF' in reason for reason in possible['missed_reasons']))
        self.assertEqual(discarded['category'], 'discarded')

    def test_unrelated_area_cannot_become_possible_from_location_and_modality(self):
        job = SimpleNamespace(title='Auxiliar Administrativo',
            description='Organização de documentos, planilhas e rotinas administrativas.',
            keywords=['excel'], salary_min=2500, salary_max=4000,
            modality='onsite', location='Recife / PE', contract_type='clt')
        preferences = {'titles': ['Suporte / TI / NOC'],
            'keywords': ['Windows', 'redes', 'NOC'], 'locations': ['Recife / PE'],
            'modalities': ['onsite']}

        result = evaluate_job(job, ['Excel', 'Windows', 'redes'], preferences)

        self.assertLess(result['match_score'], 40)
        self.assertEqual(result['category'], 'discarded')
        self.assertTrue(any('não corresponde à sua busca' in reason
                            for reason in result['missed_reasons']))

        technical_overlap = evaluate_job(
            SimpleNamespace(**{**vars(job), 'keywords': ['windows']}),
            ['Excel', 'Windows', 'redes'], preferences)
        self.assertTrue(40 <= technical_overlap['match_score'] < 70)
        self.assertEqual(technical_overlap['category'], 'possible')


if __name__ == '__main__':
    unittest.main()

class InternationalMatchingTests(unittest.TestCase):
    def test_brazilian_role_and_skill_aliases_are_explainable(self):
        job = SimpleNamespace(title='Data Analyst', description='Data analysis with SQL and spreadsheets.',
            keywords=['SQL', 'Excel'], salary_max=8000, salary_min=4000,
            modality='remote', location='Brasil', contract_type=None)
        result = evaluate_job(job, ['sql', 'planilhas'], {'titles': ['Analista de Dados'],
            'locations': ['Brasília / DF'], 'modalities': ['remote']})
        self.assertEqual(result['match_score'], 100)
        self.assertEqual(result['category'], 'strong')
        self.assertTrue(eligible(job, {'titles': ['Analista de Dados'], 'locations': ['Goiânia / GO']}))
        self.assertTrue(result['match_reasons'])
        self.assertEqual(match(['js'], ['javascript'])['match_score'], 100)
        self.assertEqual(match(['java'], ['javascript'])['match_score'], 0)

    def test_missing_salary_or_inferred_skills_remain_possible_not_auto(self):
        job = SimpleNamespace(title='Python Developer', description='Build APIs using Python and Docker.',
            keywords=['python'], salary_max=0, salary_min=0, modality='remote', location='Remoto Brasil', contract_type=None)
        preferences = {'titles': ['Desenvolvedor Python'], 'locations': ['São Paulo / SP'],
            'modalities': ['remote'], 'min_salary': 5000}
        self.assertTrue(eligible(job, preferences))
        result = evaluate_job(job, ['python', 'docker'], preferences)
        self.assertEqual(result['category'], 'possible')
        self.assertLess(result['match_score'], 70)
        self.assertTrue(any('salarial não informada' in value for value in result['missed_reasons']))
        job.salary_max = 7000
        job.keywords = []
        result = evaluate_job(job, ['python', 'docker'], preferences)
        self.assertEqual(result['category'], 'possible')
        self.assertTrue(any('inferidas' in value for value in result['missed_reasons']))
        job.location = 'Germany'
        self.assertFalse(eligible(job, preferences))

    def test_seventy_is_high_and_forty_is_observation(self):
        required = [f'skill{i}' for i in range(10)]
        self.assertEqual(match(required[:7], required)['category'], 'high')
        self.assertEqual(match(required[:4], required)['category'], 'observation')
        self.assertEqual(match(required[:3], required)['category'], 'discarded')


class HardPreferenceScoreTests(unittest.TestCase):
    def test_explicit_incompatible_preferences_never_authorize_auto_submission(self):
        preferences = {'titles': ['Desenvolvedor Python'], 'locations': ['Brasília / DF'],
            'modalities': ['remote'], 'min_salary': 5000}
        base = dict(title='Python Developer', description='Build distributed Python services.',
            keywords=['python'], salary_min=5000, salary_max=8000, modality='remote',
            location='Remoto Brasil', contract_type=None)
        for changed in [dict(location='Europe'), dict(location='UK'), dict(location='Berlin'), dict(modality='onsite'),
                        dict(salary_max=4000, salary_min=3000), dict(title='Java Developer')]:
            with self.subTest(changed=changed):
                job = SimpleNamespace(**{**base, **changed})
                result = evaluate_job(job, ['python'], preferences)
                self.assertLess(result['match_score'], 70)
                self.assertNotEqual(result['category'], 'strong')
                self.assertIn(filter_reason(job, preferences), result['missed_reasons'])
        for region in ['Brasília / DF', 'Brazil', 'Remoto Brasil']:
            job = SimpleNamespace(**{**base, 'location': region})
            self.assertGreaterEqual(evaluate_job(job, ['python'], preferences)['match_score'], 70)


class BrazilianSupportMatchingTests(unittest.TestCase):
    def job(self, **changes):
        values = dict(title='Analista de Suporte N2', description='Suporte técnico em Windows e redes corporativas.',
            keywords=['suporte', 'windows', 'redes'], salary_min=3500, salary_max=5000,
            modality='onsite', location='Brasília / Distrito Federal', contract_type='clt', country='BR')
        return SimpleNamespace(**{**values, **changes})

    def preferences(self):
        return {'titles': ['Analista de Suporte N2'], 'keywords': ['suporte', 'tecnologia'],
                'locations': ['Brasília / DF'], 'modalities': ['onsite'], 'min_salary': 3000}

    def test_exact_support_role_high_and_related_service_desk_requires_review(self):
        skills = ['suporte', 'windows', 'redes']
        exact = evaluate_job(self.job(), skills, self.preferences())
        self.assertGreaterEqual(exact['match_score'], 70)
        self.assertEqual(exact['category'], 'strong')
        adjacent = evaluate_job(self.job(title='Analista de Service Desk',
            keywords=['atendimento', 'windows', 'office365']), skills, self.preferences())
        self.assertTrue(40 <= adjacent['match_score'] < 70, adjacent)
        self.assertEqual(adjacent['category'], 'possible')
        self.assertTrue(any('mesma área' in reason for reason in adjacent['match_reasons']))
        other_level = evaluate_job(self.job(title='Analista de Suporte N3'), skills, self.preferences())
        self.assertTrue(40 <= other_level['match_score'] < 70, other_level)

    def test_only_brazilian_locations_are_admitted_even_without_city_preferences(self):
        for location, country in [('Munich, Bavaria', None), ('Worldwide', None),
                                  ('Latin America', None), ('Brasília / DF', 'DE'),
                                  ('Springfield, MA', None), ('Oxford, MS', None)]:
            with self.subTest(location=location, country=country):
                job = self.job(location=location, country=country)
                self.assertFalse(is_brazilian_job(job))
                self.assertFalse(compatible_region(job, {}))
                self.assertEqual(evaluate_job(job, ['suporte', 'windows', 'redes'], {})['category'], 'discarded')
        for location in ['Remoto Brasil', 'Recife / Pernambuco', 'Goiânia, Goiás', 'Campinas / SP',
                         'Franca / SP', 'Brasília (DF)']:
            with self.subTest(location=location):
                self.assertTrue(is_brazilian_job(self.job(location=location, country=None)))

    def test_full_state_names_structured_fields_and_city_preferences_agree(self):
        job = self.job(location='Brasília, Distrito Federal, Brasil')
        details = job_location_details(job)
        self.assertEqual((details['city'], details['state']), ('Brasília', 'DF'))
        self.assertTrue(compatible_region(job, self.preferences()))
        self.assertFalse(compatible_region(self.job(location='Goiânia / GO'), self.preferences()))
        self.assertTrue(compatible_region(self.job(location='Remoto Brasil', modality='remote'), self.preferences()))
        structured = self.job(location='Não informada', city='Brasília', state='Distrito Federal')
        self.assertTrue(compatible_region(structured, self.preferences()))
        self.assertTrue(compatible_region(self.job(location='Brasília (DF)', country=None), self.preferences()))
        self.assertTrue(compatible_region(self.job(location='São Paulo', country=None), {'locations': ['São Paulo / SP']}))
        self.assertTrue(is_brazilian_job(self.job(location='Franca / SP', city='Franca', state='SP', country='BR')))
        interior = self.job(location='Corumbá / MS', city='Corumbá', state='MS', country='BR')
        self.assertTrue(is_brazilian_job(interior))
        self.assertTrue(compatible_region(interior, {'locations': ['Corumbá / MS']}))
        self.assertEqual(job_location_details(interior)['state'], 'MS')

    def test_requirement_extraction_uses_observed_words_and_reasons_are_unique(self):
        terms = advertised_skills('Experiência comprovada em suporte técnico, Windows e redes TCP/IP.')
        self.assertIn('technical support', terms)
        self.assertIn('windows', terms)
        self.assertIn('networking', terms)
        self.assertNotIn('python', terms)
        self.assertEqual(dedupe_reasons(['Cargo compatível.', ' Cargo compatível. ', 'Localização compatível.']),
                         ['Cargo compatível.', 'Localização compatível.'])
        result = evaluate_job(self.job(), ['suporte', 'windows', 'redes'], self.preferences())
        self.assertEqual(len(result['match_reasons']), len(set(result['match_reasons'])))

    def test_explicit_support_specialization_includes_core_without_inventing_advanced_skills(self):
        for specialization in ['Suporte N2', 'Suporte NOC', 'Suporte técnico nível 2']:
            with self.subTest(specialization=specialization):
                result = match([specialization, 'Windows'], ['suporte', 'Windows'])
                self.assertEqual(result['match_score'], 100)
                self.assertEqual(result['missing_skills'], [])
        self.assertEqual(match(['Suporte N1'], ['Suporte N2'])['match_score'], 0)
        self.assertEqual(match(['Suporte'], ['Suporte NOC'])['match_score'], 0)
        self.assertEqual(match(['Java'], ['JavaScript'])['match_score'], 0)
        self.assertEqual(match([], ['suporte'])['match_score'], 0)
