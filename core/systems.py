from db.collections import get_system_metadata_collection, get_db, get_items_collection


def create_system(system_id, display_name, mapping):
    doc = {
        "collection_name": system_id,
        "display": display_name,
        "mapping": mapping,
    }
    return get_system_metadata_collection().insert_one(doc).inserted_id

def get_system(system_id):
    return get_system_metadata_collection().find_one({"collection_name": system_id}, {"_id": 0})

def update_system(system_id, updates):
    result = get_system_metadata_collection().update_one(
        {"collection_name": system_id}, {"$set": updates}
    )
    return result.modified_count > 0

def delete_system(system_id):
    db = get_db()
    db.drop_collection(system_id)  # delete dataset collection
    result = get_system_metadata_collection().delete_one({"collection_name": system_id})
    return result.deleted_count > 0

def list_systems():
    return list(get_system_metadata_collection().find({}, {"_id": 0}))


def add_items_to_system(system_id, new_items):
    systems = get_items_collection('systems')  # adjust as needed

    system = systems.find_one({"system_id": system_id})
    if not system:
        return False

    # Assuming items are under 'items' key, adjust as needed
    current_items = system.get('items', [])
    updated_items = current_items + new_items

    result = systems.update_one(
        {"system_id": system_id},
        {"$set": {"items": updated_items}}
    )
    return result.modified_count > 0


def edit_item_in_system(system_id, item_id, updated_fields):
    systems = get_items_collection('systems')

    system = systems.find_one({"system_id": system_id})
    if not system or "items" not in system:
        return False

    items = system["items"]
    updated = False
    for item in items:
        if str(item.get("item_id")) == str(item_id):
            item.update(updated_fields)
            updated = True
            break
    if not updated:
        return False

    result = systems.update_one(
        {"system_id": system_id},
        {"$set": {"items": items}}
    )
    return result.modified_count > 0

def get_features(item_id, system):
    from db.collections import get_items_collection
    import logging

    collection = get_items_collection(system)

    # Search using "WineID" as a string
    item = collection.find_one({"WineID": str(item_id)})

    if not item:
        logging.error(f"[get_features] Item {item_id} not found in collection '{system}'")
        raise ValueError(f"Item {item_id} not found in system '{system}'")

    vector = (
        item.get("FeatureVector") or
        item.get("featureVector") or
        item.get("feature_vector")
    )

    if vector is None:
        logging.error(f"[get_features] Item {item_id} in system '{system}' has no FeatureVector")
        raise ValueError(f"Item {item_id} has no FeatureVector")

    return vector

