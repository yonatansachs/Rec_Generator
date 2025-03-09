import unittest
from app import calculate_estimated_rating, create_problem_with_pulp_dict, calculate_delta

class TestRecommendations(unittest.TestCase):
    def test_estimated_rating_matching(self):
        # When user profile exactly matches the item features, estimated rating should be maximum.
        user_profile = [1, 1, 1]
        item_features = [1, 1, 1]
        # For simplicity, we set n (the normalization factor) equal to the number of features.
        rating = calculate_estimated_rating(user_profile, item_features, s=5, n=3)
        self.assertAlmostEqual(rating, 5.0, places=2)

    def test_estimated_rating_opposite(self):
        # When user profile is opposite to the item features, estimated rating should be minimum.
        # According to our function, if for each feature we have (1,0) then each such feature contributes to delta.
        # With user_profile = [1, 1, 1] and item_features = [0, 0, 0]:
        # delta = 3, so estimated rating = 5 - (3*(5-1)/3) = 5 - 4 = 1.
        user_profile = [1, 1, 1]
        item_features = [0, 0, 0]
        rating = calculate_estimated_rating(user_profile, item_features, s=5, n=3)
        self.assertAlmostEqual(rating, 1.0, places=2)

    def test_create_problem_output(self):
        # Use a small test dataset.
        # Suppose we have two items with 3-dimensional feature vectors.
        vectors = [
            [0, 1, 0],
            [1, 0, 1]
        ]
        # Simulate user ratings for these two items.
        ratings = [5, 1]
        deltas = calculate_delta(ratings, 3)  # n_features is 3 in this case.
        obj, profile_vector = create_problem_with_pulp_dict(vectors, deltas)
        # The profile vector should have 3 elements.
        self.assertEqual(len(profile_vector), 3)
        # And each value should be between -1 and 1.
        for v in profile_vector:
            self.assertTrue(-1 <= v <= 1, f"Profile vector value {v} is out of expected range [-1, 1]")

if __name__ == "__main__":
    unittest.main()
