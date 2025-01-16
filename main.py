import json
import os
import uuid

import numpy as np
from pulp import (
    LpProblem, LpMinimize, LpVariable, lpSum, value, LpStatus,
    LpInteger, LpBinary, LpContinuous, PULP_CBC_CMD
)


s = 5  # Global rating scale

################################################################################
# DATA LOADING & USER INPUT
################################################################################

file_path = "Data/feat1000_v2.json"  # Path to the JSON file

def load_restaurant_data(filepath):
    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)

def display_restaurant_list(restaurants):
    print("Available Restaurants:")
    for idx, item in enumerate(restaurants, start=1):
        name = item.get("name", "Unknown")
        print(f"{idx}. {name}")

def get_user_choices(restaurants, n=5):
    user_choices = []
    while len(user_choices) < n:
        try:
            choice = int(
                input(f"Select restaurant #{len(user_choices) + 1} by number (1-{len(restaurants)}): ")
            )
            if 1 <= choice <= len(restaurants):
                selected_restaurant = restaurants[choice - 1]
                if selected_restaurant in user_choices:
                    print("You have already selected that restaurant. Please select a different one.")
                else:
                    user_choices.append(selected_restaurant)
            else:
                print(f"Please enter a valid number between 1 and {len(restaurants)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")
    return user_choices

def get_user_ratings(selected_restaurants):
    ratings = []
    for restaurant in selected_restaurants:
        name = restaurant.get("name", "Unknown")
        while True:
            try:
                rating = float(input(f"Rate the restaurant '{name}' on a scale of 1 to 5: "))
                if 1 <= rating <= 5:
                    ratings.append(rating)
                    break
                else:
                    print("Please enter a rating between 1 and 5.")
            except ValueError:
                print("Invalid input. Please enter a number.")
    return ratings

################################################################################
# OPTIONAL: OLD (WEIGHTED APPROACH)
################################################################################

def calculate_attribute_weights(selected_restaurants, ratings):
    num_attributes = len(selected_restaurants[0]["featureVector"])
    weights = [0] * num_attributes

    for j in range(num_attributes):
        has_attr_ratings = []
        no_attr_ratings = []

        for i, restaurant in enumerate(selected_restaurants):
            if restaurant["featureVector"][j] == 1:
                has_attr_ratings.append(ratings[i])
            else:
                no_attr_ratings.append(ratings[i])

        if has_attr_ratings and no_attr_ratings:
            avg_has_attr = sum(has_attr_ratings) / len(has_attr_ratings)
            avg_no_attr = sum(no_attr_ratings) / len(no_attr_ratings)
            # Normalize difference to [0,1] on a 5-star scale
            weights[j] = abs(avg_has_attr - avg_no_attr) / 4.0

    return weights

def calculate_hamming_distances(user_profile, restaurants, weights):
    distances = []
    for restaurant in restaurants:
        feature_vector = restaurant.get("featureVector", [])
        if len(feature_vector) != len(user_profile):
            feature_vector = feature_vector[:len(user_profile)] + [0] * (len(user_profile) - len(feature_vector))
        distance = sum(weights[j] * abs(user_profile[j] - feature_vector[j])
                       for j in range(len(user_profile)))
        distances.append((restaurant["name"], distance, feature_vector))
    return distances

def recommend_restaurants(user_profile, restaurants, weights, top_n=5):
    distances = calculate_hamming_distances(user_profile, restaurants, weights)
    sorted_restaurants = sorted(distances, key=lambda x: x[1])
    return sorted_restaurants[:top_n]

################################################################################
# NEW CODE: PULP MODEL
################################################################################

def calculate_delta(ratings, n):
    """
    Convert user ratings into 'delta' values for the optimization.
    s is the global rating scale (default = 5).
    """
    # e.g. delta_i = n - (n * (ri - 1) / (s - 1))
    print("Raw Ratings:", ratings)
    return [n - (n * (ri - 1) / (s - 1)) for ri in ratings]

def create_problem_with_pulp_dict(vectors, deltas):
    """
    Creates and solves the PuLP optimization problem given feature vectors (0/1)
    and 'delta' values derived from user ratings.
    """
    n = len(vectors[0])  # number of features
    m = len(vectors)     # number of items (chosen restaurants)

    print("create_problem_with_pulp_dict with n =", n)
    print("create_problem_with_pulp_dict with m =", m)

    # Create the problem
    prob = LpProblem("MyProblem", LpMinimize)

    # Create your variables
    # We'll allow x_j to be -1, 0, or +1, so we use LpInteger with bounds -1 to 1.
    x = [LpVariable(f"x{i}", lowBound=-1, upBound=1, cat=LpInteger) for i in range(1, n + 1)]
    x_like = [LpVariable(f"x{i}_like", cat=LpBinary) for i in range(1, n + 1)]
    x_dislike = [LpVariable(f"x{i}_dislike", cat=LpBinary) for i in range(1, n + 1)]
    z = [LpVariable(f"z{i}", cat=LpContinuous, lowBound=0) for i in range(1, m + 1)]

    # Objective: minimize sum of z[i]
    prob += lpSum(z)

    # For each chosen restaurant i, define constraints:
    for i in range(m):
        # If vectors[i][j] == 0, we add x_like[j], else we add x_dislike[j].
        # sum(...) + z[i] >= deltas[i]  and  sum(...) - z[i] <= deltas[i]
        prob += lpSum([x_like[j] if vectors[i][j] == 0 else x_dislike[j] for j in range(n)]) + z[i] >= deltas[i]
        prob += lpSum([x_like[j] if vectors[i][j] == 0 else x_dislike[j] for j in range(n)]) - z[i] <= deltas[i]

    # Next constraints to link x_j with x_like[j] and x_dislike[j].
    for j in range(n):
        prob += x[j] + 2 * x_dislike[j] <= 1
        prob += x[j] + x_dislike[j] >= 0
        prob += x[j] - x_like[j] <= 0
        prob += x[j] - 2 * x_like[j] >= -1

    # Solve
    prob.solve(PULP_CBC_CMD(msg=True))

    print("Finished solving create_problem_with_pulp_dict.")
    print("Solution status:", LpStatus[prob.status])

    # Show variable values
    #for v in prob.variables():
        #print(v.name, "=", v.varValue)

    # Extract the user profile as a list of -1, 0, or +1
    profile_vector = [v.varValue for v in x]
    print("Objective =", value(prob.objective))

    return value(prob.objective), profile_vector

def calculate_estimated_rating(user_profile, restaurant_features, s=5, n=20):
    """
    Calculates the estimated rating for a restaurant based on the user's profile.
    By default, n=20 is the number of features if your user_profile has length 20, etc.
    Feel free to auto-detect n = len(user_profile).
    """
    # Count "mismatch" between user_profile and restaurant_features:
    # If user_profile[j] == -1 and feature_vector[j] == 1 => mismatch
    # If user_profile[j] ==  1 and feature_vector[j] == 0 => mismatch
    if len(user_profile) != len(restaurant_features):
        raise ValueError("Profile and restaurant feature lengths differ!")
    delta = sum(
        (u == -1 and r == 1) or (u == 1 and r == 0)
        for u, r in zip(user_profile, restaurant_features)
    )
    # Convert delta to a rating on [1, s].
    return s - (delta * (s - 1) / n)

def calculate_all_expected_ratings(vectors, profile_vector):
    """
    For a set of item vectors, returns the list of estimated ratings
    according to the profile.
    """
    n = len(profile_vector)  # number of features
    results = []
    for v in vectors:
        # remove rating if you appended a placeholder
        # or only if you're certain v has no extra columns
        if len(v) == n:
            item_features = v
        else:
            # assume last col is a rating => slice it off
            item_features = v[:-1]
        est = calculate_estimated_rating(
            user_profile=profile_vector,
            restaurant_features=item_features,
            s=s,
            n=n
        )
        results.append(est)
    return results

################################################################################
# REVISED "run_your_script_on_file"
################################################################################

def run_your_script_on_file(vectors, chosen_indexes, s, n):
    """
    1) Build the training set from the chosen indexes (the user-rated items),
       so that the solver learns from real user ratings.
    2) Solve the new PuLP model to get the user_profile.
    3) Compute expected ratings for those chosen items (just as a check),
       or for the entire dataset if desired.
    """
    print("-------- run_your_script_on_file ----------")
    print("Selected indices:", chosen_indexes)

    # 1) TRAINING SET: chosen_arrays & real ratings
    selected_arrays = [vectors[i] for i in chosen_indexes]

    # The new code expects the last column to be the rating
    # for the chosen items:
    d_ratings = [arr[-1] for arr in selected_arrays]

    # Remove the last col so the solver only sees 0/1 features
    selected_features_only = np.delete(selected_arrays, -1, axis=1)

    print("CHOSEN arrays (features+rating):", selected_arrays)

    # 2) Solve with PuLP
    deltas = calculate_delta(d_ratings, n)
    objective, profile_vector = create_problem_with_pulp_dict(selected_features_only, deltas)

    print("Profile Vector:", profile_vector)
    print("Objective Value:", objective)

    # 3) Optionally, compute expected ratings for the chosen items
    #    (just to see if the solver matches them).
    expected_ratings_chosen = calculate_all_expected_ratings(selected_arrays, profile_vector)
    print("Expected Ratings for the CHOSEN items:", expected_ratings_chosen)

    return objective, profile_vector

################################################################################
# (OPTIONAL) OLD create_user_profile_with_pulp
################################################################################

def create_user_profile_with_pulp(selected_restaurants, ratings):
    feature_vectors = [r["featureVector"] for r in selected_restaurants]
    num_attributes = len(feature_vectors[0])

    problem = LpProblem("User_Profile_Optimization", LpMinimize)

    user_profile = [
        LpVariable(f"w_{i}", lowBound=-1, upBound=1, cat='Integer')
        for i in range(num_attributes)
    ]
    errors = [LpVariable(f"e_{i}", lowBound=0) for i in range(len(feature_vectors))]

    # Fallback if no ratings
    if ratings is None:
        ratings = [3.0] * len(feature_vectors)

    for i, feature_vector in enumerate(feature_vectors):
        predicted_rating = lpSum(feature_vector[j] * user_profile[j] for j in range(num_attributes))
        problem += errors[i] >= ratings[i] - predicted_rating
        problem += errors[i] >= predicted_rating - ratings[i]

    problem += lpSum(errors)
    problem.solve(PULP_CBC_CMD(msg=False))

    optimized_profile = [value(w) if value(w) is not None else 0 for w in user_profile]
    return optimized_profile

################################################################################
# FINAL MAIN
################################################################################

def main():
    # 1. Load restaurant data
    restaurants = load_restaurant_data(file_path)

    # 2. Display restaurant list
    display_restaurant_list(restaurants)

    # 3. Get user's choices (indices)
    selected_restaurants = []
    chosen_indexes = []
    for _ in range(5):

        choice = int(input(f"Select restaurant #{len(selected_restaurants)+1} (by number): "))
        while choice<0 or choice>428:
            print("Select number between 0-428")
            choice = int(input(f"Select restaurant #{len(selected_restaurants) + 1} (by number): "))

        selected_restaurants.append(restaurants[choice - 1])
        chosen_indexes.append(choice - 1)

    # 4. Get user's ratings for the selected restaurants
    ratings = get_user_ratings(selected_restaurants)

    # ----- OLD APPROACH (optional) -----
    weights = calculate_attribute_weights(selected_restaurants, ratings)
    user_profile_old = create_user_profile_with_pulp(selected_restaurants, ratings)
    print("\n[OLD APPROACH] Optimized User Profile:", user_profile_old)
    recommendations_old = recommend_restaurants(user_profile_old, restaurants, weights)
    print("\n[OLD APPROACH] Top 5 Recommended Restaurants (Weighted Hamming):")
    for name, distance, feature_vector in recommendations_old:
        print(f" - {name} (Distance: {distance:.2f})")

    # ----- NEW APPROACH -----
    # Build vectors with the last column as "user rating" if chosen; else placeholder
    vectors = []
    for i, rest in enumerate(restaurants):
        fv = rest["featureVector"][:]
        if i in chosen_indexes:
            idx_in_chosen = chosen_indexes.index(i)
            user_rating = ratings[idx_in_chosen]
            fv_plus_rating = fv + [user_rating]
        else:
            fv_plus_rating = fv + [3.0]  # or 0.0 or any placeholder for non-chosen
        vectors.append(fv_plus_rating)

    # Train using the chosen data
    n_features = len(restaurants[0]["featureVector"])
    objective, profile_vector_new = run_your_script_on_file(
        vectors=vectors,
        chosen_indexes=chosen_indexes,
        s=s,
        n=n_features
    )
    print("\n[NEW APPROACH] Profile Vector (from advanced PuLP):", profile_vector_new)
    print("[NEW APPROACH] Objective Value:", objective)

    # Now predict or "recommend" for all restaurants
    rated_restaurants = []
    for rest in restaurants:
        fv = rest["featureVector"]
        # If the user_profile is length n_features, we pass fv directly
        est_rating = calculate_estimated_rating(
            user_profile=profile_vector_new,
            restaurant_features=fv,
            s=s,
            n=n_features
        )
        rated_restaurants.append((rest["name"], est_rating))

    # Sort by estimated rating descending
    rated_restaurants.sort(key=lambda x: x[1], reverse=True)
    print("\n[NEW APPROACH] Top 5 Recommended Restaurants (highest estimated rating):")
    for name, est in rated_restaurants[:5]:
        print(f" - {name} (Estimated rating: {est:.2f})")
if __name__ == "__main__":
    main()
