import cryptography.fernet
import time
key = cryptography.fernet.Fernet.generate_key()
print(f"密钥 (请妥善保存): \n{key.decode()}")
time.sleep(600)