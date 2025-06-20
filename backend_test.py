#!/usr/bin/env python3
import requests
import json
import time
import os
import unittest
import re
from unittest import mock
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

def test_leads_endpoints_directly():
    """Test getting and clearing leads directly without relying on search"""
    try:
        # Get leads
        response = requests.get(f"{BASE_URL}/leads")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # If there are no leads, we'll skip some assertions
        if data:
            lead = data[0]
            required_fields = ["id", "name", "address", "google_maps_url", "has_website", 
                              "latitude", "longitude"]
            for field in required_fields:
                assert field in lead, f"Field '{field}' missing from lead"
        
        # Clear leads
        response = requests.delete(f"{BASE_URL}/leads")
        assert response.status_code == 200
        data = response.json()
        assert "deleted_count" in data
        
        # Verify leads are cleared
        response = requests.get(f"{BASE_URL}/leads")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0, "Leads were not properly cleared"
        
        log_test_result("Leads Management Endpoints", True)
        return True
    except Exception as e:
        log_test_result("Leads Management Endpoints", False, str(e))
        return False

def test_mock_business_search_basic():
    """Test basic mock business search functionality"""
    try:
        # Clear existing leads first
        requests.delete(f"{BASE_URL}/leads")
        
        # Test basic search with restaurants in Toronto
        payload = {
            "query": "restaurants",
            "location": "Toronto, ON"
        }
        
        response = requests.post(f"{BASE_URL}/search", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "leads" in data
        assert "total_count" in data
        assert "search_center" in data
        
        # Verify we got some results
        assert len(data["leads"]) > 0
        assert data["total_count"] > 0
        
        # Verify search center is for Toronto
        assert data["search_center"]["lat"] == 43.6532
        assert data["search_center"]["lng"] == -79.3832
        
        # Verify leads were saved to database
        response = requests.get(f"{BASE_URL}/leads")
        assert response.status_code == 200
        leads_data = response.json()
        assert len(leads_data) == len(data["leads"])
        
        log_test_result("Basic Mock Business Search", True, 
                       f"Generated {len(data['leads'])} restaurant leads in Toronto")
        return True
    except Exception as e:
        log_test_result("Basic Mock Business Search", False, str(e))
        return False

def test_mock_business_search_different_types():
    """Test mock business search with different business types"""
    try:
        # Clear existing leads first
        requests.delete(f"{BASE_URL}/leads")
        
        business_types = ["plumbers", "dentists", "lawyers"]
        results = {}
        
        for business_type in business_types:
            payload = {
                "query": business_type,
                "location": "Toronto, ON"
            }
            
            response = requests.post(f"{BASE_URL}/search", json=payload)
            assert response.status_code == 200
            data = response.json()
            
            # Verify we got some results
            assert len(data["leads"]) > 0
            
            # Store results for analysis
            results[business_type] = data["leads"]
            
            # Clear leads for next test
            requests.delete(f"{BASE_URL}/leads")
        
        # Verify business names are appropriate for each type
        for business_type, leads in results.items():
            # Check at least the first lead
            lead = leads[0]
            
            # For plumbers, check if name contains "Plumbing" or similar
            if business_type == "plumbers":
                plumbing_terms = ["Plumbing", "Drain", "Water", "Pipe"]
                has_relevant_term = any(term in lead["name"] for term in plumbing_terms)
                assert has_relevant_term, f"Plumber business name '{lead['name']}' doesn't contain relevant terms"
            
            # For dentists, check if name contains "Dental" or similar
            elif business_type == "dentists":
                dental_terms = ["Dental", "Dentist", "Smile", "Teeth", "Orthodontics"]
                has_relevant_term = any(term in lead["name"] for term in dental_terms)
                assert has_relevant_term, f"Dental business name '{lead['name']}' doesn't contain relevant terms"
            
            # For lawyers, check if name contains "Law" or similar
            elif business_type == "lawyers":
                law_terms = ["Law", "Legal", "Attorney", "Partners"]
                has_relevant_term = any(term in lead["name"] for term in law_terms)
                assert has_relevant_term, f"Law business name '{lead['name']}' doesn't contain relevant terms"
        
        log_test_result("Different Business Types Search", True, 
                       f"Successfully generated leads for {', '.join(business_types)}")
        return True
    except Exception as e:
        log_test_result("Different Business Types Search", False, str(e))
        return False

def test_location_recognition():
    """Test location recognition for major cities"""
    try:
        # Clear existing leads first
        requests.delete(f"{BASE_URL}/leads")
        
        test_locations = [
            {"location": "Toronto, ON", "expected_coords": (43.6532, -79.3832)},
            {"location": "Vancouver, BC", "expected_coords": (49.2827, -123.1207)},
            {"location": "New York, NY", "expected_coords": (40.7128, -74.0060)},
            {"location": "London, UK", "expected_coords": (51.5074, -0.1278)}
        ]
        
        for test_loc in test_locations:
            payload = {
                "query": "restaurants",
                "location": test_loc["location"]
            }
            
            response = requests.post(f"{BASE_URL}/search", json=payload)
            assert response.status_code == 200
            data = response.json()
            
            # Verify search center matches expected coordinates
            assert data["search_center"]["lat"] == test_loc["expected_coords"][0]
            assert data["search_center"]["lng"] == test_loc["expected_coords"][1]
            
            # Clear leads for next test
            requests.delete(f"{BASE_URL}/leads")
        
        log_test_result("Location Recognition", True, 
                       f"Successfully recognized coordinates for {len(test_locations)} cities")
        return True
    except Exception as e:
        log_test_result("Location Recognition", False, str(e))
        return False

def test_radius_filter():
    """Test radius filter for business search"""
    try:
        # Clear existing leads first
        requests.delete(f"{BASE_URL}/leads")
        
        # Test with different radius values
        radius_values = [5000, 10000, 20000]  # 5km, 10km, 20km
        results = {}
        
        for radius in radius_values:
            payload = {
                "query": "restaurants",
                "location": "Toronto, ON",
                "radius": radius
            }
            
            response = requests.post(f"{BASE_URL}/search", json=payload)
            assert response.status_code == 200
            data = response.json()
            
            # Store results for analysis
            results[radius] = data["leads"]
            
            # Clear leads for next test
            requests.delete(f"{BASE_URL}/leads")
        
        # Verify businesses are within the specified radius
        for radius, leads in results.items():
            center_lat, center_lng = 43.6532, -79.3832  # Toronto coordinates
            
            for lead in leads:
                # Calculate rough distance from center (this is an approximation)
                lat_diff = abs(lead["latitude"] - center_lat)
                lng_diff = abs(lead["longitude"] - center_lng)
                
                # Convert to approximate kilometers (very rough approximation)
                # 0.009 degrees is roughly 1km
                approx_distance_km = max(lat_diff, lng_diff) / 0.009
                
                # Convert radius from meters to km
                radius_km = radius / 1000
                
                assert approx_distance_km <= radius_km, f"Business at ({lead['latitude']}, {lead['longitude']}) is outside the {radius_km}km radius"
        
        log_test_result("Radius Filter", True, 
                       f"Successfully filtered businesses by radius: {', '.join(map(str, radius_values))} meters")
        return True
    except Exception as e:
        log_test_result("Radius Filter", False, str(e))
        return False

def test_min_rating_filter():
    """Test minimum rating filter for business search"""
    try:
        # Clear existing leads first
        requests.delete(f"{BASE_URL}/leads")
        
        # Test with different minimum rating values
        min_ratings = [3.0, 4.0, 4.5]
        
        for min_rating in min_ratings:
            payload = {
                "query": "restaurants",
                "location": "Toronto, ON",
                "min_rating": min_rating
            }
            
            response = requests.post(f"{BASE_URL}/search", json=payload)
            assert response.status_code == 200
            data = response.json()
            
            # Verify all businesses have at least the minimum rating
            for lead in data["leads"]:
                assert lead["rating"] >= min_rating, f"Business '{lead['name']}' has rating {lead['rating']} which is below minimum {min_rating}"
            
            # Clear leads for next test
            requests.delete(f"{BASE_URL}/leads")
        
        log_test_result("Minimum Rating Filter", True, 
                       f"Successfully filtered businesses by minimum ratings: {', '.join(map(str, min_ratings))}")
        return True
    except Exception as e:
        log_test_result("Minimum Rating Filter", False, str(e))
        return False

def test_has_website_filter():
    """Test has_website filter for business search"""
    try:
        # Clear existing leads first
        requests.delete(f"{BASE_URL}/leads")
        
        # Test with has_website = true
        payload = {
            "query": "restaurants",
            "location": "Toronto, ON",
            "has_website": True
        }
        
        response = requests.post(f"{BASE_URL}/search", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify all businesses have a website
        for lead in data["leads"]:
            assert lead["has_website"] == True, f"Business '{lead['name']}' has has_website=False when filter is True"
            assert lead["website"] is not None, f"Business '{lead['name']}' has no website URL when has_website=True"
        
        # Clear leads for next test
        requests.delete(f"{BASE_URL}/leads")
        
        # Test with has_website = false
        payload = {
            "query": "restaurants",
            "location": "Toronto, ON",
            "has_website": False
        }
        
        response = requests.post(f"{BASE_URL}/search", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify all businesses don't have a website
        for lead in data["leads"]:
            assert lead["has_website"] == False, f"Business '{lead['name']}' has has_website=True when filter is False"
            assert lead["website"] is None, f"Business '{lead['name']}' has a website URL when has_website=False"
        
        log_test_result("Has Website Filter", True, 
                       "Successfully filtered businesses by website availability")
        return True
    except Exception as e:
        log_test_result("Has Website Filter", False, str(e))
        return False

def test_business_data_quality():
    """Test the quality of generated business data"""
    try:
        # Clear existing leads first
        requests.delete(f"{BASE_URL}/leads")
        
        payload = {
            "query": "restaurants",
            "location": "Toronto, ON"
        }
        
        response = requests.post(f"{BASE_URL}/search", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify we got some results
        assert len(data["leads"]) > 0
        
        # Check data quality for each business
        for lead in data["leads"]:
            # Check business name
            assert len(lead["name"]) > 3, f"Business name '{lead['name']}' is too short"
            
            # Check address format
            address_pattern = r"^\d+ .+ St(reet)?|Ave(nue)?|Dr(ive)?|Ln|Rd|Blvd, .+"
            assert re.match(address_pattern, lead["address"]), f"Address '{lead['address']}' doesn't match expected format"
            
            # Check phone number format
            phone_pattern = r"^\(\d{3}\) \d{3}-\d{4}$"
            assert re.match(phone_pattern, lead["phone"]), f"Phone number '{lead['phone']}' doesn't match expected format"
            
            # Check website URL if has_website is true
            if lead["has_website"]:
                assert lead["website"].startswith("https://www."), f"Website URL '{lead['website']}' doesn't start with 'https://www.'"
                assert lead["website"].endswith(".com"), f"Website URL '{lead['website']}' doesn't end with '.com'"
            else:
                assert lead["website"] is None, f"Website URL is not None when has_website is False"
            
            # Check rating range
            assert 2.0 <= lead["rating"] <= 5.0, f"Rating {lead['rating']} is outside the expected range (2.0-5.0)"
            
            # Check review count
            assert 5 <= lead["review_count"] <= 500, f"Review count {lead['review_count']} is outside the expected range (5-500)"
            
            # Check coordinates
            assert -90 <= lead["latitude"] <= 90, f"Latitude {lead['latitude']} is outside valid range"
            assert -180 <= lead["longitude"] <= 180, f"Longitude {lead['longitude']} is outside valid range"
        
        log_test_result("Business Data Quality", True, 
                       f"Successfully verified data quality for {len(data['leads'])} businesses")
        return True
    except Exception as e:
        log_test_result("Business Data Quality", False, str(e))
        return False

def test_error_handling():
    """Test error handling for invalid inputs"""
    try:
        # Test with invalid location
        payload = {
            "query": "restaurants",
            "location": "NonexistentCity, XX"
        }
        
        response = requests.post(f"{BASE_URL}/search", json=payload)
        # Should still work with default coordinates
        assert response.status_code == 200
        
        # Test with empty query
        payload = {
            "query": "",
            "location": "Toronto, ON"
        }
        
        response = requests.post(f"{BASE_URL}/search", json=payload)
        # Should return an error or empty results
        if response.status_code == 200:
            data = response.json()
            # Either we get empty results or some default results
            pass
        else:
            # Or we get an error status code
            assert 400 <= response.status_code < 500
        
        log_test_result("Error Handling", True, 
                       "Successfully tested error handling for invalid inputs")
        return True
    except Exception as e:
        log_test_result("Error Handling", False, str(e))
        return False

def test_combined_filters():
    """Test combining multiple filters together"""
    try:
        # Clear existing leads first
        requests.delete(f"{BASE_URL}/leads")
        
        # Test with multiple filters
        payload = {
            "query": "restaurants",
            "location": "Toronto, ON",
            "radius": 15000,
            "min_rating": 4.0,
            "has_website": True
        }
        
        response = requests.post(f"{BASE_URL}/search", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify all filters are applied
        for lead in data["leads"]:
            # Check rating filter
            assert lead["rating"] >= 4.0, f"Business '{lead['name']}' has rating {lead['rating']} which is below minimum 4.0"
            
            # Check website filter
            assert lead["has_website"] == True, f"Business '{lead['name']}' has has_website=False when filter is True"
            assert lead["website"] is not None, f"Business '{lead['name']}' has no website URL when has_website=True"
            
            # Check radius filter (rough approximation)
            center_lat, center_lng = 43.6532, -79.3832  # Toronto coordinates
            lat_diff = abs(lead["latitude"] - center_lat)
            lng_diff = abs(lead["longitude"] - center_lng)
            approx_distance_km = max(lat_diff, lng_diff) / 0.009
            assert approx_distance_km <= 15, f"Business at ({lead['latitude']}, {lead['longitude']}) is outside the 15km radius"
        
        log_test_result("Combined Filters", True, 
                       f"Successfully applied multiple filters together")
        return True
    except Exception as e:
        log_test_result("Combined Filters", False, str(e))
        return False

def run_all_tests():
    """Run all tests and print summary"""
    print("\n===== STARTING BACKEND API TESTS =====\n")
    
    # Basic API tests
    test_root_endpoint()
    test_status_endpoint()
    
    # Test mock business search functionality
    test_mock_business_search_basic()
    test_mock_business_search_different_types()
    test_location_recognition()
    
    # Test search filters
    test_radius_filter()
    test_min_rating_filter()
    test_has_website_filter()
    test_combined_filters()
    
    # Test business data quality
    test_business_data_quality()
    
    # Test error handling
    test_error_handling()
    
    # Test leads management
    test_leads_endpoints_directly()
    
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