from pymongo import MongoClient
import os

_mongo_client = None

def init_db():
    global _mongo_client
    _mongo_client = MongoClient(os.getenv("MONGO_URI"))

def get_db():
    if not _mongo_client:
        raise Exception("DB not initialized")
    return _mongo_client["Rec_Generator"]
