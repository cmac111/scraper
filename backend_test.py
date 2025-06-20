#!/usr/bin/env python3
import requests
import json
import time
import os
from typing import Dict, Any, List, Optional

# Get the backend URL from the frontend .env file
def get_backend_url():
    with open('/app/frontend/.env', 'r') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                return line.strip().split('=')[1].strip('"\'')
    raise ValueError("Could not find REACT_APP_BACKEND_URL in frontend/.env")

# Base URL for API requests
BASE_URL = f"{get_backend_url()}/api"
print(f"Using backend URL: {BASE_URL}")

# Test results tracking
test_results = {
    "passed": 0,
    "failed": 0,
    "tests": []
}

def log_test_result(test_name: str, passed: bool, details: str = ""):
    """Log test results for reporting"""
    status = "PASSED" if passed else "FAILED"
    print(f"[{status}] {test_name}")
    if details:
        print(f"  Details: {details}")
    
    test_results["tests"].append({
        "name": test_name,
        "passed": passed,
        "details": details
    })
    
    if passed:
        test_results["passed"] += 1
    else:
        test_results["failed"] += 1

def test_root_endpoint():
    """Test the root API endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"] == "Google Maps Scraper API"
        log_test_result("Root API Endpoint", True)
        return True
    except Exception as e:
        log_test_result("Root API Endpoint", False, str(e))
        return False

def test_status_endpoint():
    """Test the status check endpoints"""
    try:
        # Create a status check
        client_name = f"Test Client {int(time.time())}"
        response = requests.post(
            f"{BASE_URL}/status", 
            json={"client_name": client_name}
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["client_name"] == client_name
        
        # Get status checks
        response = requests.get(f"{BASE_URL}/status")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Verify our test client is in the list
        found = False
        for status in data:
            if status["client_name"] == client_name:
                found = True
                break
        assert found, f"Could not find our test client '{client_name}' in status checks"
        
        log_test_result("Status Check Endpoints", True)
        return True
    except Exception as e:
        log_test_result("Status Check Endpoints", False, str(e))
        return False

def test_search_endpoint(query: str = "restaurants", location: str = "Toronto, ON", 
                        radius: int = 10000, min_rating: Optional[float] = None,
                        has_website: Optional[bool] = None):
    """Test the search endpoint with various parameters"""
    try:
        # Build request payload
        payload = {
            "query": query,
            "location": location,
            "radius": radius
        }
        
        if min_rating is not None:
            payload["min_rating"] = min_rating
            
        if has_website is not None:
            payload["has_website"] = has_website
        
        # Make the request
        response = requests.post(f"{BASE_URL}/search", json=payload)
        assert response.status_code == 200, f"Search failed with status {response.status_code}: {response.text}"
        
        data = response.json()
        assert "leads" in data
        assert "total_count" in data
        assert "search_center" in data
        assert data["total_count"] == len(data["leads"])
        
        # Verify search center contains expected fields
        assert "lat" in data["search_center"]
        assert "lng" in data["search_center"]
        assert "address" in data["search_center"]
        assert data["search_center"]["address"] == location
        
        # Verify lead structure if any leads were found
        if data["leads"]:
            lead = data["leads"][0]
            required_fields = ["id", "name", "address", "google_maps_url", "has_website", 
                              "latitude", "longitude", "created_at"]
            for field in required_fields:
                assert field in lead, f"Field '{field}' missing from lead"
            
            # Verify filters were applied
            if min_rating is not None and lead.get("rating") is not None:
                assert lead["rating"] >= min_rating
                
            if has_website is not None:
                assert lead["has_website"] == has_website
        
        test_name = f"Search Endpoint ({query} in {location})"
        if min_rating is not None:
            test_name += f", min_rating={min_rating}"
        if has_website is not None:
            test_name += f", has_website={has_website}"
            
        log_test_result(test_name, True, f"Found {data['total_count']} leads")
        return True, data
    except Exception as e:
        test_name = f"Search Endpoint ({query} in {location})"
        log_test_result(test_name, False, str(e))
        return False, None

def test_invalid_location():
    """Test search with an invalid location"""
    try:
        payload = {
            "query": "restaurants",
            "location": "ThisIsNotARealLocationXYZ123",
            "radius": 10000
        }
        
        response = requests.post(f"{BASE_URL}/search", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Location not found" in data["detail"]
        
        log_test_result("Invalid Location Handling", True)
        return True
    except Exception as e:
        log_test_result("Invalid Location Handling", False, str(e))
        return False

def test_leads_endpoints():
    """Test getting and clearing leads"""
    try:
        # First, make sure we have some leads by doing a search
        success, _ = test_search_endpoint("coffee shops", "New York, NY", 5000)
        if not success:
            raise Exception("Failed to create test leads for leads endpoint test")
        
        # Get leads
        response = requests.get(f"{BASE_URL}/leads")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        initial_count = len(data)
        assert initial_count > 0, "No leads found after search"
        
        # Verify lead structure
        if data:
            lead = data[0]
            required_fields = ["id", "name", "address", "google_maps_url", "has_website", 
                              "latitude", "longitude", "created_at"]
            for field in required_fields:
                assert field in lead, f"Field '{field}' missing from lead"
        
        # Clear leads
        response = requests.delete(f"{BASE_URL}/leads")
        assert response.status_code == 200
        data = response.json()
        assert "deleted_count" in data
        assert data["deleted_count"] >= initial_count
        
        # Verify leads are cleared
        response = requests.get(f"{BASE_URL}/leads")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0
        
        log_test_result("Leads Management Endpoints", True)
        return True
    except Exception as e:
        log_test_result("Leads Management Endpoints", False, str(e))
        return False

def run_all_tests():
    """Run all tests and print summary"""
    print("\n===== STARTING BACKEND API TESTS =====\n")
    
    # Basic API tests
    test_root_endpoint()
    test_status_endpoint()
    
    # Search tests with different parameters
    test_search_endpoint("restaurants", "Toronto, ON")
    test_search_endpoint("coffee shops", "New York, NY", 5000)
    test_search_endpoint("hotels", "London, UK", 15000, 4.0)
    test_search_endpoint("bakery", "Paris, France", 8000, None, True)
    
    # Invalid input test
    test_invalid_location()
    
    # Leads management tests
    test_leads_endpoints()
    
    # Print summary
    print("\n===== TEST SUMMARY =====")
    print(f"Total tests: {test_results['passed'] + test_results['failed']}")
    print(f"Passed: {test_results['passed']}")
    print(f"Failed: {test_results['failed']}")
    
    if test_results["failed"] > 0:
        print("\nFailed tests:")
        for test in test_results["tests"]:
            if not test["passed"]:
                print(f"- {test['name']}: {test['details']}")
    
    return test_results["failed"] == 0

if __name__ == "__main__":
    run_all_tests()