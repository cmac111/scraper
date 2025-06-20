from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
import random
import re
import requests
import json

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

class SearchRequest(BaseModel):
    query: str
    location: str
    radius: int = 20000  # Default 20km in meters
    min_rating: Optional[float] = None
    has_website: Optional[bool] = None
    categories: Optional[List[str]] = None

class BusinessLead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    address: str
    phone: Optional[str] = None
    website: Optional[str] = None
    google_maps_url: str
    rating: Optional[float] = None
    review_count: Optional[int] = None
    has_website: bool
    latitude: float
    longitude: float
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SearchResponse(BaseModel):
    leads: List[BusinessLead]
    total_count: int
    search_center: dict

# Business name generators by category
BUSINESS_TEMPLATES = {
    "restaurants": [
        "{location} Grill", "{location} Bistro", "The {adjective} Kitchen", "{name}'s Restaurant",
        "{location} Diner", "Taste of {location}", "{adjective} Eats", "{name}'s Cafe",
        "{location} Pizza", "Golden {food} Restaurant", "{adjective} {food} House"
    ],
    "plumbers": [
        "{location} Plumbing", "{name} Plumbing Services", "Quick Fix Plumbing", 
        "{adjective} Drain Solutions", "{location} Water Works", "Pro Plumb {location}",
        "{name}'s Plumbing", "Reliable Plumbing Co.", "{location} Pipe Masters"
    ],
    "dentists": [
        "{location} Dental Care", "Dr. {name} Dentistry", "{adjective} Smile Dental",
        "{location} Family Dentist", "Bright Smile Dental", "{name} Dental Clinic",
        "{location} Orthodontics", "Perfect Teeth Dental", "Gentle Care Dentistry"
    ],
    "lawyers": [
        "{name} Law Firm", "{location} Legal Services", "{adjective} Legal Associates",
        "{name} & Partners", "{location} Law Office", "Justice Law Firm",
        "{name} Attorney at Law", "Legal Solutions {location}", "Premier Law Group"
    ],
    "hair salons": [
        "{location} Hair Studio", "{adjective} Salon", "{name}'s Hair Design",
        "Styling Station", "{location} Beauty Bar", "Hair Masters", "Chic Cuts",
        "{adjective} Hair Lounge", "Glamour Salon", "{name}'s Styling"
    ],
    "auto repair": [
        "{location} Auto Repair", "{name}'s Garage", "Quick Fix Auto", 
        "{adjective} Motors", "{location} Car Care", "Pro Auto Service",
        "Reliable Auto Repair", "{name} Automotive", "{location} Auto Works"
    ],
    "coffee shops": [
        "{location} Coffee Co.", "The {adjective} Bean", "{name}'s Cafe",
        "Daily Grind Coffee", "{location} Roasters", "Brew House",
        "{adjective} Coffee", "Steam & Bean", "Corner Cafe"
    ]
}

ADJECTIVES = ["Premium", "Elite", "Professional", "Quality", "Expert", "Superior", "Advanced", "Modern", "Classic", "Reliable"]
NAMES = ["Johnson", "Smith", "Williams", "Brown", "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson", "Garcia", "Martinez", "Robinson", "Clark"]
STREETS = ["Main St", "Oak Ave", "Pine St", "Maple Dr", "Cedar Ln", "Elm St", "Park Ave", "First St", "Second Ave", "Third St", "King St", "Queen St", "Church St", "Mill St", "High St"]

# Location coordinates (lat, lng) for major cities
CITY_COORDINATES = {
    "toronto": (43.6532, -79.3832),
    "vancouver": (49.2827, -123.1207),
    "montreal": (45.5017, -73.5673),
    "calgary": (51.0447, -114.0719),
    "ottawa": (45.4215, -75.6972),
    "edmonton": (53.5461, -113.4938),
    "mississauga": (43.5890, -79.6441),
    "winnipeg": (49.8951, -97.1384),
    "quebec city": (46.8139, -71.2080),
    "hamilton": (43.2557, -79.8711),
    "new york": (40.7128, -74.0060),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "houston": (29.7604, -95.3698),
    "phoenix": (33.4484, -112.0740),
    "philadelphia": (39.9526, -75.1652),
    "san antonio": (29.4241, -98.4936),
    "san diego": (32.7157, -117.1611),
    "dallas": (32.7767, -96.7970),
    "san jose": (37.3382, -121.8863),
    "london": (51.5074, -0.1278),
    "manchester": (53.4808, -2.2426),
    "birmingham": (52.4862, -1.8904),
    "glasgow": (55.8642, -4.2518),
    "liverpool": (53.4084, -2.9916)
}

def get_location_coordinates(location_str):
    """Get coordinates for a location string"""
    location_lower = location_str.lower()
    
    # Try exact matches first
    for city, coords in CITY_COORDINATES.items():
        if city in location_lower:
            return coords
    
    # Default to Toronto if not found
    return CITY_COORDINATES["toronto"]

def generate_business_name(query, location):
    """Generate a realistic business name based on query and location"""
    query_lower = query.lower()
    location_name = location.split(',')[0].strip()  # Extract city name
    
    # Map common queries to categories
    category = "restaurants"  # default
    if any(word in query_lower for word in ["plumber", "plumbing", "drain", "pipe"]):
        category = "plumbers"
    elif any(word in query_lower for word in ["dentist", "dental", "orthodontist"]):
        category = "dentists"
    elif any(word in query_lower for word in ["lawyer", "attorney", "legal"]):
        category = "lawyers"
    elif any(word in query_lower for word in ["hair", "salon", "barber", "styling"]):
        category = "hair salons"
    elif any(word in query_lower for word in ["auto", "car", "mechanic", "garage", "repair"]):
        category = "auto repair"
    elif any(word in query_lower for word in ["coffee", "cafe", "espresso"]):
        category = "coffee shops"
    elif any(word in query_lower for word in ["restaurant", "food", "dining", "pizza", "burger"]):
        category = "restaurants"
    
    templates = BUSINESS_TEMPLATES.get(category, BUSINESS_TEMPLATES["restaurants"])
    template = random.choice(templates)
    
    return template.format(
        location=location_name,
        adjective=random.choice(ADJECTIVES),
        name=random.choice(NAMES),
        food=random.choice(["Pizza", "Burger", "Sushi", "Thai", "Italian", "Mexican"])
    )

def generate_mock_businesses(search_request: SearchRequest):
    """Generate mock business data based on search parameters"""
    center_lat, center_lng = get_location_coordinates(search_request.location)
    
    # Generate 5-25 businesses
    num_businesses = random.randint(5, 25)
    businesses = []
    
    # Radius in degrees (approximate)
    radius_degrees = (search_request.radius / 1000) * 0.009  # Rough conversion
    
    for i in range(num_businesses):
        # Generate random coordinates within radius
        lat_offset = random.uniform(-radius_degrees, radius_degrees)
        lng_offset = random.uniform(-radius_degrees, radius_degrees)
        
        business_lat = center_lat + lat_offset
        business_lng = center_lng + lng_offset
        
        # Generate business details
        business_name = generate_business_name(search_request.query, search_request.location)
        
        # Generate rating
        rating = round(random.uniform(2.0, 5.0), 1)
        review_count = random.randint(5, 500)
        
        # Apply rating filter
        if search_request.min_rating and rating < search_request.min_rating:
            continue
        
        # Generate website status
        has_website = random.choice([True, False, True, True])  # 75% chance of having website
        
        # Apply website filter
        if search_request.has_website is not None and has_website != search_request.has_website:
            continue
        
        # Generate address
        street_number = random.randint(1, 9999)
        street_name = random.choice(STREETS)
        city_name = search_request.location.split(',')[0].strip()
        address = f"{street_number} {street_name}, {city_name}"
        
        # Generate phone
        phone = f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
        
        # Generate website
        website = None
        if has_website:
            domain_name = business_name.lower().replace(" ", "").replace("'", "").replace("&", "and")[:15]
            website = f"https://www.{domain_name}.com"
        
        business = BusinessLead(
            name=business_name,
            address=address,
            phone=phone,
            website=website,
            google_maps_url=f"https://maps.google.com/maps?q={business_lat},{business_lng}",
            rating=rating,
            review_count=review_count,
            has_website=has_website,
            latitude=business_lat,
            longitude=business_lng
        )
        
        businesses.append(business)
    
    return businesses[:25]  # Limit to 25 results

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Google Maps Scraper API"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

@api_router.post("/search", response_model=SearchResponse)
async def search_businesses(search_request: SearchRequest):
    try:
        logger.info(f"Searching for '{search_request.query}' in '{search_request.location}'")
        
        # Generate mock businesses
        leads = generate_mock_businesses(search_request)
        
        # Get search center coordinates
        center_lat, center_lng = get_location_coordinates(search_request.location)
        
        # Save leads to database
        for lead in leads:
            await db.business_leads.insert_one(lead.dict())
            
        logger.info(f"Generated {len(leads)} business leads")
        
        return SearchResponse(
            leads=leads,
            total_count=len(leads),
            search_center={
                "lat": center_lat,
                "lng": center_lng,
                "address": search_request.location
            }
        )
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@api_router.get("/leads", response_model=List[BusinessLead])
async def get_leads():
    leads = await db.business_leads.find().to_list(1000)
    return [BusinessLead(**lead) for lead in leads]

@api_router.delete("/leads")
async def clear_leads():
    result = await db.business_leads.delete_many({})
    return {"deleted_count": result.deleted_count}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()