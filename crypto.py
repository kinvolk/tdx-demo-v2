from cryptography.fernet import Fernet

def new_key():
    return Fernet.generate_key()

def encrypt_val(key, text):
    f = Fernet(key)
    text_bytes = bytes(text, 'utf-8')
    cipher_text = f.encrypt(text_bytes)
    cipher_text = str(cipher_text.decode('ascii'))
    return cipher_text

def decrypt_val(key, cipher_text):
    f = Fernet(key)
    text = f.decrypt(cipher_text.encode()).decode()
    return text
