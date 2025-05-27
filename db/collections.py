from db.connection import get_db

# ───────────── Static SYSTEMS config ─────────────
SYSTEMS = {
    "Restaurants": {
        "display": "Restaurants",
        "mapping": {
            "id": "aaaid",
            "name": "name",
            "description": "description",
            "image": "image",
            "featureVector": "featureVector",
        },
    },
    "movie": {
        "display": "Movies",
        "mapping": {
            "id": "aaaid",
            "name": "aaamovieName",
            "description": "directors_names",
            "image": "image",
            "featureVector": "featureVector",
        },
    },
}

# ───────────── Collection Access Helpers ─────────────

def get_users_collection():
    return get_db()["users"]

def get_ratings_collection():
    return get_db()["ratings"]

def get_system_metadata_collection():
    return get_db()["system_metadata"]

def get_items_collection(system_name):
    return get_db()[system_name]

# ───────────── Create Indexes ─────────────

def create_indexes():
    get_users_collection().create_index("username", unique=True)
    get_ratings_collection().create_index(
        [("user_id", 1), ("system", 1), ("item_id", 1)], unique=True
    )

# ───────────── Dynamic Collection Loader ─────────────

def load_existing_collections() -> None:
    """
    Register every non-utility Mongo collection as a system.
    If we stored a user-defined mapping in `system_metadata`,
    use it; otherwise fall back to default field names.
    """
    db = get_db()
    exclude = {
        "users", "ratings", "system.indexes", "system_metadata"
    }
    for cname in db.list_collection_names():
        if cname in exclude or cname in SYSTEMS:
            continue

        meta = get_system_metadata_collection().find_one({"collection_name": cname})
        mapping = (
            meta["mapping"]
            if meta and "mapping" in meta else {
                "id": "id",
                "name": "name",
                "description": "description",
                "image": "image",
                "featureVector": "featureVector",
            }
        )
        SYSTEMS[cname] = {
            "display": cname.capitalize(),
            "mapping": mapping,
        }
        print(f"Registered '{cname}' with mapping {mapping}")
