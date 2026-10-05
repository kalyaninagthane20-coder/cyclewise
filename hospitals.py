"""Static directory of hospitals, grouped by city.

Kept as plain data so it is easy to extend. A later version could move it to a database table.
"""

HOSPITALS = {
    "Mumbai": [
        {"name": "KEM Hospital",              "address": "Acharya Donde Marg, Parel",          "phone": "022-24136051", "type": "Government"},
        {"name": "Cama & Albless Hospital",   "address": "Mahapalika Marg, Fort",              "phone": "022-22620684", "type": "Government"},
        {"name": "Wadia Hospital for Women",  "address": "Acharya Donde Marg, Parel",          "phone": "022-24129929", "type": "Government"},
        {"name": "Hinduja Hospital",          "address": "Veer Savarkar Marg, Mahim",          "phone": "022-24452222", "type": "Private"},
        {"name": "Lilavati Hospital",         "address": "A-791 Bandra Reclamation, Bandra",   "phone": "022-26751000", "type": "Private"},
    ],
    "Pune": [
        {"name": "Sassoon General Hospital",  "address": "Jai Prakash Narayan Road, Pune",     "phone": "020-26128000", "type": "Government"},
        {"name": "Jehangir Hospital",         "address": "32 Sassoon Road, Sangamvadi",        "phone": "020-66810000", "type": "Private"},
        {"name": "Ruby Hall Clinic",          "address": "40 Sassoon Road, Pune",              "phone": "020-66455100", "type": "Private"},
        {"name": "Deenanath Mangeshkar",      "address": "Erandwane, Pune",                    "phone": "020-49150300", "type": "Private"},
        {"name": "Aundh District Hospital",   "address": "Aundh, Pune",                        "phone": "020-25880151", "type": "Government"},
    ],
    "Kolhapur": [
        {"name": "Kolhapur Civil Hospital",   "address": "Tarabai Park, Kolhapur",             "phone": "0231-2521137", "type": "Government"},
        {"name": "Sahyadri Hospital",         "address": "Near Bus Stand, Kolhapur",           "phone": "0231-2522222", "type": "Private"},
        {"name": "Chhatrapati Pramila Raje",  "address": "CPR Road, Kolhapur",                 "phone": "0231-2543022", "type": "Government"},
    ],
    "Nagpur": [
        {"name": "AIIMS Nagpur",              "address": "Plot No 2, Sector 20, MIHAN",        "phone": "0712-2807700", "type": "Government"},
        {"name": "Wockhardt Hospital",        "address": "Trimurti Nagar, Nagpur",             "phone": "0712-6116116", "type": "Private"},
        {"name": "Orange City Hospital",      "address": "Wathoda Road, Nagpur",               "phone": "0712-6604999", "type": "Private"},
        {"name": "Government Medical College","address": "Hanuman Nagar, Nagpur",              "phone": "0712-2748888", "type": "Government"},
    ],
    "Nashik": [
        {"name": "Dr Zakir Hussain Hospital", "address": "Nashik Road, Nashik",                "phone": "0253-2465001", "type": "Government"},
        {"name": "Wockhardt Hospital Nashik", "address": "Bombay Naka, Nashik",                "phone": "0253-6633333", "type": "Private"},
        {"name": "Bharat Agro Hospital",      "address": "College Road, Nashik",               "phone": "0253-2317777", "type": "Private"},
    ],
    "Aurangabad": [
        {"name": "Government Medical College","address": "Aurangabad, Maharashtra",            "phone": "0240-2402412", "type": "Government"},
        {"name": "Kamalnayan Bajaj Hospital", "address": "Satara Parisar, Aurangabad",         "phone": "0240-2352222", "type": "Private"},
    ],
    "Delhi": [
        {"name": "AIIMS Delhi (OBG dept)",    "address": "Ansari Nagar East, New Delhi",       "phone": "011-26588500", "type": "Government"},
        {"name": "Safdarjung Hospital",       "address": "Ansari Nagar West, New Delhi",       "phone": "011-26165060", "type": "Government"},
        {"name": "Fortis La Femme",           "address": "Greater Kailash, New Delhi",         "phone": "011-42007777", "type": "Private"},
    ],
    "Bangalore": [
        {"name": "Bangalore Medical College", "address": "Fort Road, Bangalore",               "phone": "080-22867400", "type": "Government"},
        {"name": "Manipal Hospital",          "address": "98 HAL Airport Road, Bangalore",     "phone": "080-25024444", "type": "Private"},
        {"name": "Cloudnine Hospital",        "address": "Bellandur, Bangalore",               "phone": "080-40182929", "type": "Private"},
    ],
    "Hyderabad": [
        {"name": "Niloufer Hospital",         "address": "Red Hills, Hyderabad",               "phone": "040-23320401", "type": "Government"},
        {"name": "KIMS Hospital",             "address": "Minister Road, Secunderabad",        "phone": "040-44885000", "type": "Private"},
        {"name": "Rainbow Hospital",          "address": "Banjara Hills, Hyderabad",           "phone": "040-44555333", "type": "Private"},
    ],
}


def find_hospitals(city: str = "", hospital_type: str = ""):
    """Filter by city (empty means all cities) and by type ("Government" / "Private")."""
    if city and city in HOSPITALS:
        results = list(HOSPITALS[city])
    else:
        results = [h for group in HOSPITALS.values() for h in group]
    if hospital_type:
        results = [h for h in results if h["type"] == hospital_type]
    return results
