import unittest
from types import SimpleNamespace
from app.matching import eligible, evaluate_job, filter_reason, match


class MatchingTests(unittest.TestCase):
    def test_boundary_categories(self):
        required = ['python', 'sql', 'docker', 'redis']
        for skills, score, category in [([], 0, 'discarded'), (['python'], 25, 'discarded'), (['python', 'sql'], 50, 'observation'), (['python', 'sql', 'docker'], 75, 'observation'), (required, 100, 'high')]:
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
        self.assertEqual(high_preference_partial_skills['category'], 'possible')
        self.assertEqual(possible['category'], 'possible')
        self.assertTrue(any('Cidade/UF' in reason for reason in possible['missed_reasons']))
        self.assertEqual(discarded['category'], 'discarded')


if __name__ == '__main__':
    unittest.main()