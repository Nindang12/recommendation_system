"""
Import seed data from seed_data.txt (JSON) into MongoDB.
Chạy script này để nạp dữ liệu mẫu từ file txt vào MongoDB.
"""
from pymongo import MongoClient
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "rd_recommendation_system")

# Đường dẫn file dữ liệu: cùng thư mục với script này
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_FILE = SCRIPT_DIR / "seed_data.txt"


def load_seed_data(file_path=None):
    """Đọc và parse JSON từ file txt."""
    path = file_path or DEFAULT_DATA_FILE
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file dữ liệu: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def import_to_mongodb(data_file=None, force=False):
    """
    Import dữ liệu từ file vào MongoDB.
    :param data_file: Đường dẫn file .txt chứa JSON (mặc định: seed_data.txt)
    :param force: Nếu True, xóa và ghi đè; nếu False chỉ insert khi collection rỗng
    """
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    print(f"Connected to MongoDB database: {DB_NAME}")

    data = load_seed_data(data_file)
    collection_map = {
        "research_fields": "research_fields",
        "industries": "industries",
        "method_techniques": "method_techniques",
        "output_assets": "output_assets",
        "experts": "experts",
        "enterprises": "enterprises",
        "funders": "funders",
        "projects": "projects",
    }

    for key, collection_name in collection_map.items():
        if key not in data:
            print(f"  [SKIP] Không có key '{key}' trong file dữ liệu.")
            continue
        collection = db[collection_name]
        count_before = collection.count_documents({})
        if force and count_before > 0:
            collection.delete_many({})
            count_before = 0
        if count_before == 0:
            items = data[key]
            if items:
                collection.insert_many(items)
                print(f"Inserted {len(items)} documents into {collection_name}")
            else:
                print(f"  [SKIP] '{key}' rỗng, không insert.")
        else:
            print(f"  [SKIP] {collection_name} đã có {count_before} bản ghi (không ghi đè). Chạy với force=True để ghi đè.")

    print("\nSeed data import hoàn tất.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Import seed data từ file txt vào MongoDB")
    parser.add_argument("--file", "-f", default=None, help="Đường dẫn file dữ liệu (mặc định: seed_data.txt)")
    parser.add_argument("--force", action="store_true", help="Xóa dữ liệu cũ và ghi đè bằng dữ liệu từ file")
    args = parser.parse_args()
    import_to_mongodb(data_file=args.file, force=args.force)
