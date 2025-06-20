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
import googlemaps
import json
import requests
from urllib.parse import urlencode

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Google Maps API Key
GOOGLE_MAPS_API_KEY = "AIzaSyCAwbHIFnRrswP38tnmYeR24cp0DPhLs2w"

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
        # Initialize Google Maps client
        gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
        
        # First, geocode the location to get coordinates
        geocode_result = gmaps.geocode(search_request.location)
        if not geocode_result:
            raise HTTPException(status_code=400, detail="Location not found")
        
        location_coords = geocode_result[0]['geometry']['location']
        
        # Perform places search
        places_result = gmaps.places_nearby(
            location=location_coords,
            radius=search_request.radius,
            keyword=search_request.query,
            type="establishment"
        )
        
        leads = []
        for place in places_result.get('results', []):
            # Get detailed place information
            place_details = gmaps.place(
                place_id=place['place_id'],
                fields=['name', 'formatted_address', 'formatted_phone_number', 'website', 'rating', 'user_ratings_total', 'geometry']
            )
            
            place_info = place_details.get('result', {})
            
            # Apply filters
            if search_request.min_rating and place_info.get('rating', 0) < search_request.min_rating:
                continue
                
            has_website = bool(place_info.get('website'))
            if search_request.has_website is not None and has_website != search_request.has_website:
                continue
            
            # Create business lead
            lead = BusinessLead(
                name=place_info.get('name', 'Unknown'),
                address=place_info.get('formatted_address', ''),
                phone=place_info.get('formatted_phone_number'),
                website=place_info.get('website'),
                google_maps_url=f"https://maps.google.com/maps?cid={place.get('place_id', '')}",
                rating=place_info.get('rating'),
                review_count=place_info.get('user_ratings_total'),
                has_website=has_website,
                latitude=place_info.get('geometry', {}).get('location', {}).get('lat', 0),
                longitude=place_info.get('geometry', {}).get('location', {}).get('lng', 0)
            )
            leads.append(lead)
        
        # Save leads to database
        for lead in leads:
            await db.business_leads.insert_one(lead.dict())
            
        return SearchResponse(
            leads=leads,
            total_count=len(leads),
            search_center={
                "lat": location_coords['lat'],
                "lng": location_coords['lng'],
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