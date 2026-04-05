import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# ⚠️ Replace with your actual Mongo URI
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "label_edi_validator"   # replace with your DB name


async def migrate():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]

    carriers = await db.carriers.find().to_list(length=None)

    if not carriers:
        print("No carriers found.")
        return

    for carrier in carriers:
        old_rules = carrier.get("label_rules", {})

        if not old_rules:
            print(f"Skipping {carrier['carrier']} (no label_rules)")
            continue

        if "fields" in old_rules:
            print(f"{carrier['carrier']} already migrated.")
            continue

        new_rules = {
            "fields": {},
            "barcode": {},
            "layout": {}
        }

        field_formats = old_rules.get("field_formats", {})

        for field_name, config in field_formats.items():
            new_rules["fields"][field_name] = {
                "required": config.get("required", False),
                "pattern": config.get("pattern"),
                "weight": 0.2
            }

        if "barcode" in field_formats:
            new_rules["barcode"] = {
                "required": field_formats["barcode"].get("required", False),
                "allowed_types": [field_formats["barcode"].get("format")],
                "weight": 0.2
            }

        new_rules["layout"] = {
            "min_blocks": 3,
            "weight": 0.1
        }

        await db.carriers.update_one(
            {"_id": carrier["_id"]},
            {"$set": {"label_rules": new_rules}}
        )

        print(f"Migrated: {carrier['carrier']}")

    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
