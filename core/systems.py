from db.collections import get_system_metadata_collection, get_db, get_items_collection, SYSTEMS
import logging
from db.collections import get_items_collection


def create_system(system_id, display_name, mapping):
    system_id = str(system_id)
    doc = {
        "collection_name": system_id,
        "display": display_name,
        "mapping": mapping,
    }
    return get_system_metadata_collection().insert_one(doc).inserted_id


def get_system(system_name):
    system_name = str(system_name)
    doc = get_system_metadata_collection().find_one({"collection_name": system_name}, {"_id": 0})
    if doc:
        return doc

    for key in SYSTEMS:
        if key.lower() == system_name.lower():
            mapping = SYSTEMS[key]["mapping"]
            return {
                "collection_name": key,
                "display": SYSTEMS[key].get("display", key),
                "mapping": mapping
            }
    return None


def update_system(system_id, updates):
    system_id = str(system_id)
    result = get_system_metadata_collection().update_one(
        {"collection_name": system_id}, {"$set": updates}
    )
    return result.modified_count > 0


def delete_system(system_name):
    system_name = str(system_name)
    db = get_db()
    db.drop_collection(system_name)
    result = get_system_metadata_collection().delete_one({"collection_name": system_name})
    return result.deleted_count > 0

def list_systems():
    return list(get_system_metadata_collection().find({}, {"_id": 0}))


def add_items_to_system(system_id, new_items):
    system_id = str(system_id)
    systems = get_items_collection('systems')

    system = systems.find_one({"system_id": system_id})
    if not system:
        return False

    for item in new_items:
        item["item_id"] = str(item.get("item_id"))

    current_items = system.get('items', [])
    updated_items = current_items + new_items

    result = systems.update_one(
        {"system_id": system_id},
        {"$set": {"items": updated_items}}
    )
    return result.modified_count > 0



def edit_item_in_system(system_id, item_id, updated_fields):
    system_id = str(system_id)
    item_id = str(item_id)

    systems = get_items_collection('systems')
    system = systems.find_one({"system_id": system_id})
    if not system or "items" not in system:
        return False

    items = system["items"]
    updated = False
    for item in items:
        if str(item.get("item_id")) == item_id:
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



    system = str(system)
    item_id = str(item_id)
    collection = get_items_collection(system)

    system_info = get_system(system)
    if not system_info:
        logging.error(f"[get_features] System '{system}' not found")
        raise ValueError(f"System '{system}' not found")

    mapping = system_info.get("mapping", {})
    id_field = mapping.get("id")
    if not id_field:
        logging.error(f"[get_features] System '{system}' mapping missing 'id'")
        raise ValueError(f"System '{system}' missing mapping.id")

    item = collection.find_one({id_field: item_id})
    if not item:
        logging.error(f"[get_features] Item {item_id} not found in system '{system}' using field '{id_field}'")
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



