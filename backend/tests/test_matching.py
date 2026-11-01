import unittest
from types import SimpleNamespace
from app.matching import eligible, evaluate_job, filter_reason, match


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


if __name__ == '__main__':
    unittest.main()

class InternationalMatchingTests(unittest.TestCase):
    def test_brazilian_role_and_skill_aliases_are_explainable(self):
        job = SimpleNamespace(title='Data Analyst', description='Data analysis with SQL and spreadsheets.',
            keywords=['SQL', 'Excel'], salary_max=8000, salary_min=4000,
            modality='remote', location='Latin America', contract_type=None)
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
            keywords=['python'], salary_max=0, salary_min=0, modality='remote', location='Worldwide', contract_type=None)
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
            location='Worldwide', contract_type=None)
        for changed in [dict(location='Europe'), dict(location='UK'), dict(location='Berlin'), dict(modality='onsite'),
                        dict(salary_max=4000, salary_min=3000), dict(title='Java Developer')]:
            with self.subTest(changed=changed):
                job = SimpleNamespace(**{**base, **changed})
                result = evaluate_job(job, ['python'], preferences)
                self.assertLess(result['match_score'], 70)
                self.assertNotEqual(result['category'], 'strong')
                self.assertIn(filter_reason(job, preferences), result['missed_reasons'])
        for region in ['Worldwide', 'Brazil', 'Latin America']:
            job = SimpleNamespace(**{**base, 'location': region})
            self.assertGreaterEqual(evaluate_job(job, ['python'], preferences)['match_score'], 70)
