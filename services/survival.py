from blockchain import pay_namecheap_with_sol

def ensure_alive():
    pay_hosting()

def pay_hosting():
    pay_namecheap_with_sol("arandompkey",0.1,"invoicebtcaddy") #placeholders for obvious reasons
    pass

import requests
import xml.etree.ElementTree as ET
from datetime import datetime

NAMECHEAP_API_USER = ""
NAMECHEAP_API_KEY = "" #placeholders for obvious reasons
CLIENT_IP = ""

def check_domain_expiry(domain: str):
    url = "https://api.namecheap.com/xml.response"

    params = {
        "ApiUser": NAMECHEAP_API_USER,
        "ApiKey": NAMECHEAP_API_KEY,
        "UserName": NAMECHEAP_API_USER,
        "ClientIp": CLIENT_IP,
        "Command": "namecheap.domains.getInfo",
        "DomainName": domain
    }

    response = requests.get(url, params=params)
    root = ET.fromstring(response.text)

    domain_info = root.find(".//DomainGetInfoResult")

    expiration_str = domain_info.attrib.get("ExpiredDate")

    expiration_date = datetime.strptime(expiration_str, "%m/%d/%Y")
    days_left = (expiration_date - datetime.utcnow()).days

    return {
        "expires_on": expiration_date,
        "days_left": days_left
    }
