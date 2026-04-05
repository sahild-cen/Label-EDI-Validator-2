from app.database import get_database
import asyncio


async def migrate():
    db = get_database()

    carriers = await db.carriers.find().to_list(length=None)

    for carrier in carriers:
        old_rules = carrier.get("label_rules", {})

        if not old_rules:
            continue

        # Skip if already migrated
        if "fields" in old_rules:
            print(f"Carrier {carrier['carrier']} already migrated.")
            continue

        new_rules = {
            "fields": {},
            "barcode": {},
            "layout": {}
        }

        # Convert field_formats into fields
        field_formats = old_rules.get("field_formats", {})

        for field_name, config in field_formats.items():
            new_rules["fields"][field_name] = {
                "required": config.get("required", False),
                "pattern": config.get("pattern"),
                "weight": 0.2
            }

        # Convert barcode
        if "barcode" in field_formats:
            new_rules["barcode"] = {
                "required": field_formats["barcode"].get("required", False),
                "allowed_types": [field_formats["barcode"].get("format")],
                "weight": 0.2
            }

        # Convert layout
        layout_constraints = old_rules.get("layout_constraints", {})
        new_rules["layout"] = {
            "min_blocks": 3,
            "weight": 0.1
        }

        await db.carriers.update_one(
            {"_id": carrier["_id"]},
            {"$set": {"label_rules": new_rules}}
        )

        print(f"Migrated carrier: {carrier['carrier']}")

    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
