import unittest
from types import SimpleNamespace
from app.matching import eligible, match


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
        job = SimpleNamespace(title='Desenvolvedor Python', salary_max=6000, modality='remote', location='São Paulo')
        preferences = {'min_salary': 5000, 'titles': ['python'], 'modalities': ['remote'], 'locations': ['Recife']}
        self.assertTrue(eligible(job, preferences))
        self.assertFalse(eligible(job, {**preferences, 'min_salary': 7000}))
        job.modality = 'onsite'
        self.assertFalse(eligible(job, {**preferences, 'modalities': ['onsite']}))
        job.location = 'RECIFE'
        self.assertTrue(eligible(job, {**preferences, 'modalities': ['onsite']}))


if __name__ == '__main__':
    unittest.main()
