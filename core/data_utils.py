from db.connection import get_db

def load_data(system):
    items = list(get_db()[system].find())
    print(f"Loaded {len(items)} items from '{system}'")
    return items

def normalize(data, mapping):
    out = []
    for it in data:
        if mapping["id"] not in it or mapping["featureVector"] not in it:
            raise Exception("Dataset missing mapped fields")
        out.append({
            "id":           str(it[mapping["id"]]),
            "name":         it.get(mapping["name"], "Unknown"),
            "description":  it.get(mapping["description"], ""),
            "image":        it.get(mapping["image"], ""),
            "featureVector": it[mapping["featureVector"]],
        })
    return out
