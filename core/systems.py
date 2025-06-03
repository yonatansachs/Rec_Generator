from db.collections import get_system_metadata_collection, get_db

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
