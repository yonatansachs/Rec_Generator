import json

#file_path = "Data/feat1000_v2.json"  # Path to the JSON file
file_path = "Data/restaurant_data.json"  # Path to the JSON file

def load_restaurant_data(filepath):
    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)


def display_restaurant_list(restaurants):
    print("Available Restaurants:")
    for idx, item in enumerate(restaurants, start=1):
        name = item.get("name", "Unknown")
        print(f"{idx}. {name}")

def get_user_choices(restaurants,n):
    selected_restaurants = []
    chosen_indexes = []
    for _ in range(n):
        choice = int(input(f"Select restaurant #{len(selected_restaurants) + 1} (by number): "))
        while choice < 0 or choice > len(restaurants):
            print("Select a number between 1 and", len(restaurants))
            choice = int(input(f"Select restaurant #{len(selected_restaurants) + 1} (by number): "))
        selected_restaurants.append(restaurants[choice - 1])
        chosen_indexes.append(choice - 1)
    return selected_restaurants, chosen_indexes

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

