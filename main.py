import json
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, value
from scipy.spatial.distance import hamming

# Path to the JSON file
file_path = "Data/feat1000_v2.json"

def load_restaurant_data(filepath):
    """
    Load the JSON file and return the restaurant data.
    """
    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)

def display_restaurant_list(restaurants):
    """
    Display the list of restaurants to the user.
    """
    print("Available Restaurants:")
    for idx, item in enumerate(restaurants, start=1):
        name = item.get("name", "Unknown")
        print(f"{idx}. {name}")

def get_user_choices(restaurants, n=5):
    """
    Prompt the user to select n restaurants by index.
    Returns the list of selected restaurant dictionaries.
    """
    user_choices = []
    while len(user_choices) < n:
        try:
            choice = int(input(f"Select restaurant #{len(user_choices) + 1} by number (1-{len(restaurants)}): "))
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
    """
    Prompt the user to rate the selected restaurants.
    Returns the list of ratings.
    """
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

def create_user_profile_with_pulp(selected_restaurants, ratings):
    """
    Create a user profile using PuLP by minimizing the error between predicted and actual ratings.
    The profile values are restricted to -1, 0, or 1, and 'None' values are replaced with 0.
    """
    feature_vectors = [r["featureVector"] for r in selected_restaurants]
    num_attributes = len(feature_vectors[0])

    # Define the optimization problem
    problem = LpProblem("User_Profile_Optimization", LpMinimize)

    # Define the user profile variables (restricted to -1, 0, or 1)
    user_profile = [
        LpVariable(f"w_{i}", lowBound=-1, upBound=1, cat='Integer')
        for i in range(num_attributes)
    ]

    # Define auxiliary variables for absolute differences (errors)
    errors = [LpVariable(f"e_{i}", lowBound=0) for i in range(len(feature_vectors))]

    for i, feature_vector in enumerate(feature_vectors):
        # Calculate the predicted rating as a dot product
        predicted_rating = lpSum(feature_vector[j] * user_profile[j] for j in range(num_attributes))

        # Add constraints for absolute value representation
        problem += errors[i] >= ratings[i] - predicted_rating
        problem += errors[i] >= predicted_rating - ratings[i]

    # Objective: Minimize the sum of errors
    problem += lpSum(errors)

    # Solve the optimization problem
    problem.solve()

    # Extract the optimized user profile
    optimized_profile = [value(w) if value(w) is not None else 0 for w in user_profile]
    return optimized_profile


def calculate_hamming_distances(user_profile, restaurants):
    """
    Calculate the Hamming distance between the user profile and each restaurant.
    """
    distances = []
    for restaurant in restaurants:
        feature_vector = restaurant.get("featureVector", [])

        # Ensure the feature vector is the same length as the user profile
        if len(feature_vector) != len(user_profile):
            feature_vector = feature_vector[:len(user_profile)] + [0] * (len(user_profile) - len(feature_vector))

        # Calculate the Hamming distance
        distance = hamming(user_profile, feature_vector) * len(user_profile)  # Convert fraction to absolute count
        distances.append((restaurant["name"], distance))

    return distances


def recommend_restaurants(user_profile, restaurants, top_n=5):
    """
    Recommend the top N restaurants with the smallest Hamming distance to the user profile.
    """
    distances = calculate_hamming_distances(user_profile, restaurants)

    # Sort by distance (ascending) and take the top N
    sorted_restaurants = sorted(distances, key=lambda x: x[1])
    return sorted_restaurants[:top_n]

def main():
    # 1. Load restaurant data
    restaurants = load_restaurant_data(file_path)

    # 2. Display restaurant list
    display_restaurant_list(restaurants)

    # 3. Get user's choices
    selected_restaurants = get_user_choices(restaurants, n=5)

    # 4. Get user's ratings for the selected restaurants
    ratings = get_user_ratings(selected_restaurants)

    # 5. Create user profile using PuLP
    user_profile = create_user_profile_with_pulp(selected_restaurants, ratings)

    # 6. Recommend restaurants based on Hamming distance
    recommendations = recommend_restaurants(user_profile, restaurants)

    # 7. Display recommendations
    print("\nTop 5 Recommended Restaurants:")
    for name, distance in recommendations:
        print(f" - {name} (Hamming Distance: {distance:.2f})")

if __name__ == "__main__":
    main()
