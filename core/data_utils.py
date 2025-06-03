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
        item = {
            "id":           str(it[mapping["id"]]),
            "name":         it.get(mapping["name"], "Unknown"),
            "description":  it.get(mapping["description"], ""),
            "image":        it.get(mapping["image"], ""),
            "featureVector": it[mapping["featureVector"]],
        }
        # Only add latitude/longitude if present in mapping and in this item
        if "latitude" in mapping and mapping["latitude"] in it:
            item["latitude"] = it[mapping["latitude"]]
        if "longitude" in mapping and mapping["longitude"] in it:
            item["longitude"] = it[mapping["longitude"]]
        out.append(item)
    return out

