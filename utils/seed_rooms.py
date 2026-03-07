"""
Database Seed Script — Populate sample rooms
Usage: python -m utils.seed_rooms
"""

import asyncio
import logging
from datetime import datetime
from database.mongodb import connect_db, disconnect_db, get_db
from database.models import Room, RoomType, BedType, RoomPricing, RoomAmenities

logger = logging.getLogger(__name__)


# Sample rooms data
SAMPLE_ROOMS = [
    {
        "room_number": "101",
        "room_type": RoomType.STANDARD,
        "bed_type": BedType.SINGLE,
        "floor": 1,
        "capacity": 1,
        "size_sqft": 200,
        "description": "Cozy single room with city view",
        "amenities": RoomAmenities(
            wifi=True, ac=True, tv=True, workspace=True
        ),
        "pricing": RoomPricing(
            base_price_per_night=3500,
            tax_pct=15
        ),
    },
    {
        "room_number": "102",
        "room_type": RoomType.STANDARD,
        "bed_type": BedType.DOUBLE,
        "floor": 1,
        "capacity": 2,
        "size_sqft": 250,
        "description": "Comfortable double room",
        "amenities": RoomAmenities(
            wifi=True, ac=True, tv=True, workspace=True
        ),
        "pricing": RoomPricing(
            base_price_per_night=4500,
            tax_pct=15
        ),
    },
    {
        "room_number": "201",
        "room_type": RoomType.DELUXE,
        "bed_type": BedType.QUEEN,
        "floor": 2,
        "capacity": 2,
        "size_sqft": 350,
        "description": "Luxurious deluxe room with city view",
        "amenities": RoomAmenities(
            wifi=True, ac=True, tv=True, minibar=True, 
            balcony=True, workspace=True, breakfast_included=True
        ),
        "pricing": RoomPricing(
            base_price_per_night=8500,
            weekend_surcharge_pct=10,
            discount_weekly_pct=10,
            tax_pct=15
        ),
    },
    {
        "room_number": "202",
        "room_type": RoomType.DELUXE,
        "bed_type": BedType.KING,
        "floor": 2,
        "capacity": 2,
        "size_sqft": 400,
        "description": "Premium deluxe room with sea view",
        "amenities": RoomAmenities(
            wifi=True, ac=True, tv=True, minibar=True, 
            balcony=True, sea_view=True, workspace=True, 
            breakfast_included=True
        ),
        "pricing": RoomPricing(
            base_price_per_night=10000,
            weekend_surcharge_pct=10,
            discount_weekly_pct=10,
            tax_pct=15
        ),
    },
    {
        "room_number": "301",
        "room_type": RoomType.SUITE,
        "bed_type": BedType.KING,
        "floor": 3,
        "capacity": 3,
        "size_sqft": 550,
        "description": "Spacious suite with living area",
        "amenities": RoomAmenities(
            wifi=True, ac=True, tv=True, minibar=True, 
            balcony=True, kitchen=True, workspace=True, 
            breakfast_included=True
        ),
        "pricing": RoomPricing(
            base_price_per_night=15000,
            weekend_surcharge_pct=15,
            discount_weekly_pct=15,
            tax_pct=15
        ),
    },
    {
        "room_number": "401",
        "room_type": RoomType.EXECUTIVE,
        "bed_type": BedType.KING,
        "floor": 4,
        "capacity": 2,
        "size_sqft": 450,
        "description": "Executive room with premium amenities",
        "amenities": RoomAmenities(
            wifi=True, ac=True, tv=True, minibar=True, 
            balcony=True, sea_view=True, workspace=True, 
            breakfast_included=True, jacuzzi=True
        ),
        "pricing": RoomPricing(
            base_price_per_night=12000,
            weekend_surcharge_pct=15,
            discount_weekly_pct=15,
            tax_pct=15
        ),
    },
    {
        "room_number": "501",
        "room_type": RoomType.PRESIDENTIAL,
        "bed_type": BedType.KING,
        "floor": 5,
        "capacity": 4,
        "size_sqft": 800,
        "description": "Luxurious presidential suite with all amenities",
        "amenities": RoomAmenities(
            wifi=True, ac=True, tv=True, minibar=True, 
            balcony=True, sea_view=True, kitchen=True, 
            workspace=True, breakfast_included=True, jacuzzi=True
        ),
        "pricing": RoomPricing(
            base_price_per_night=25000,
            weekend_surcharge_pct=20,
            discount_weekly_pct=20,
            tax_pct=15
        ),
    },
]


async def seed_rooms():
    """Seed database with sample rooms"""
    try:
        await connect_db()
        db = get_db()
        
        # Clear existing rooms
        result = await db.rooms.delete_many({})
        logger.info(f"🗑️  Deleted {result.deleted_count} existing rooms")
        
        # Insert new rooms
        rooms_to_insert = []
        for room_data in SAMPLE_ROOMS:
            room = Room(**room_data)
            rooms_to_insert.append(room.model_dump(by_alias=True))
        
        result = await db.rooms.insert_many(rooms_to_insert)
        logger.info(f"✅ Seeded {len(result.inserted_ids)} rooms")
        
        # Print summary
        for room_data in SAMPLE_ROOMS:
            print(
                f"  Room {room_data['room_number']}: "
                f"{room_data['room_type'].value.upper()} "
                f"({room_data['bed_type'].value.title()}) - "
                f"BDT {room_data['pricing'].base_price_per_night}/night"
            )
        
    except Exception as e:
        logger.error(f"❌ Seeding error: {e}", exc_info=True)
        raise
    finally:
        await disconnect_db()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    asyncio.run(seed_rooms())
