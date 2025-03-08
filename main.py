import json
import numpy as np
from pulp import (
    LpProblem, LpMinimize, LpVariable, lpSum, value, LpInteger, PULP_CBC_CMD, pulp, LpBinary, LpContinuous
)

import UserInput

s = 5  # Global rating scale

################################################################################
# DATA LOADING
################################################################################

#file_path = "Data/restaurant_data.json"  # Path to the JSON file
file_path = "Data/feat1000_v2.json"  # Path to the JSON file

def load_restaurant_data(filepath):
    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)
def display_restaurant_list(restaurants):
    print("Available Restaurants:")
    for idx, item in enumerate(restaurants, start=1):
        name = item.get("name", "Unknown")
        print(f"{idx}. {name}")


################################################################################
# PULP MODEL
################################################################################

def calculate_delta(ratings, n):
    return [n - (n * (ri - 1) / (s - 1)) for ri in ratings]

def create_problem_with_pulp_dict(vectors, deltas):
    n = len(vectors[0])
    m = len(vectors)

    prob = pulp.LpProblem("MyProblem", LpMinimize)

    x = [pulp.LpVariable(f"x{i}", lowBound=-1, upBound=1, cat=LpInteger) for i in range(1, n + 1)]
    x_like = [pulp.LpVariable(f"x{i}_like", cat=LpBinary) for i in range(1, n + 1)]
    x_dislike = [pulp.LpVariable(f"x{i}_dislike", cat=LpBinary) for i in range(1, n + 1)]
    z = [pulp.LpVariable(f"z{i}", cat=LpContinuous) for i in range(1, m + 1)]

    prob += lpSum(z)

    for i in range(m):
        prob += pulp.lpSum([x_like[j] if vectors[i][j] == 0 else x_dislike[j] for j in range(n)]) + z[i] >= deltas[i]
        prob += pulp.lpSum([x_like[j] if vectors[i][j] == 0 else x_dislike[j] for j in range(n)]) - z[i] <= deltas[i]

    for j in range(n):
        prob += x[j] + 2 * x_dislike[j] <= 1
        prob += x[j] + x_dislike[j] >= 0
        prob += x[j] - x_like[j] <= 0
        prob += x[j] - 2 * x_like[j] >= -1

    prob.solve(PULP_CBC_CMD(msg=False))

    profile_vector = [v.varValue for v in x]
    print("\nUser Profile Vector:", profile_vector)

    return value(prob.objective), profile_vector


def calculate_estimated_rating(user_profile, restaurant_features, s=5, n=20):
    delta = sum(
        (u == -1 and r == 1) or (u == 1 and r == 0)
        for u, r in zip(user_profile, restaurant_features)
    )
    return s - (delta * (s - 1) / n)

################################################################################
# Recommenf Function
################################################################################
def recommend_restaurants(file_path):
    restaurants = load_restaurant_data(file_path)
    display_restaurant_list(restaurants)
    selected_restaurants, chosen_indexes = UserInput.get_user_choices(restaurants,5)
    user_ratings = UserInput.get_user_ratings(selected_restaurants)
    print(chosen_indexes)
    print(user_ratings)

    vectors = []
    for i, rest in enumerate(restaurants):
        fv = rest["featureVector"][:]
        if i in chosen_indexes:
            idx_in_chosen = chosen_indexes.index(i)
            user_rating = user_ratings[idx_in_chosen]
            fv_plus_rating = fv + [user_rating]
        else:
            fv_plus_rating = fv + [3.0]
        vectors.append(fv_plus_rating)

    n_features = len(restaurants[0]["featureVector"])
    objective, profile_vector_new = create_problem_with_pulp_dict(
        vectors=[vectors[i][:n_features] for i in chosen_indexes],
        deltas=calculate_delta(user_ratings, n=n_features)
    )

    rated_restaurants = []
    for rest in restaurants:
        fv = rest["featureVector"]
        est_rating = calculate_estimated_rating(user_profile=profile_vector_new, restaurant_features=fv, s=s, n=n_features)
        rated_restaurants.append((rest["name"], est_rating))

    rated_restaurants.sort(key=lambda x: x[1], reverse=True)
    print("\nTop 10 Recommended Restaurants (highest estimated rating):")
    for name, est in rated_restaurants[:10]:
        print(f" - {name} (Estimated rating: {est:.2f})")

################################################################################
# MAIN SCRIPT
################################################################################

def main():
    recommend_restaurants(file_path)


if __name__ == "__main__":
    main()
