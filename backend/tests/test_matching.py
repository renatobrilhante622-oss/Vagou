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

class AdvancedPreferenceFilters(unittest.TestCase):
    def job(self, **changes):
        data = {'title': 'Desenvolvedor Python', 'salary_min': 4000, 'salary_max': 7000,
                'modality': 'onsite', 'location': 'São Paulo / SP'}
        return SimpleNamespace(**{**data, **changes})

    def test_location_mask_accents_state_and_hyphenated_city(self):
        prefs = {'locations': ['sao paulo, SP']}
        for location in ['São Paulo / SP', 'SÃO PAULO, SP', 'São Paulo - São Paulo', 'São Paulo SP']:
            with self.subTest(location=location):
                self.assertTrue(eligible(self.job(location=location), prefs))
        self.assertFalse(eligible(self.job(location='São Paulo / PR'), prefs))
        self.assertFalse(eligible(self.job(location='São Paulo'), prefs))
        self.assertTrue(eligible(self.job(location='São Paulo / SP'), {'locations': ['São Paulo']}))
        self.assertTrue(eligible(self.job(location='Pindaré-Mirim - MA'), {'locations': ['Pindaré-Mirim / MA']}))

    def test_salary_interval_overlap_inclusive_and_unknown_salary(self):
        self.assertTrue(eligible(self.job(), {'min_salary': 7000, 'max_salary': 8000}))
        self.assertTrue(eligible(self.job(), {'min_salary': 2000, 'max_salary': 4000}))
        self.assertFalse(eligible(self.job(), {'min_salary': 7001}))
        self.assertFalse(eligible(self.job(), {'max_salary': 3999}))
        self.assertFalse(eligible(self.job(salary_min=0, salary_max=0), {'min_salary': 1}))

    def test_remote_ignores_city_but_title_and_modality_still_apply(self):
        prefs = {'locations': ['Recife / PE'], 'titles': ['  desenvolvedor   python '],
                 'modalities': ['remote'], 'min_salary': 4000, 'max_salary': 8000}
        self.assertTrue(eligible(self.job(modality='remote'), prefs))
        self.assertFalse(eligible(self.job(modality='hybrid'), prefs))
        self.assertFalse(eligible(self.job(modality='remote', title='Engenheiro Java'), prefs))
