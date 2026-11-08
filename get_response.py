import requests
import json
import cryptography.fernet

bili_cookie_key = "JnualxSbUQdjolVSXbDFTnj9UZf4leSEnoDkc3P6tNg="

x = requests.get(url="http://61.164.252.245:21979/getbilibilicookie", timeout=30.0).json()
encrypted_str: str = x['encrypted_cookie']
cipher_suite = cryptography.fernet.Fernet(bili_cookie_key)
decrypted_data = cipher_suite.decrypt(encrypted_str).decode('utf-8')
print(decrypted_data)

