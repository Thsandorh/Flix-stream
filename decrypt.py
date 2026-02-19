import base64
import hashlib
from Crypto.Cipher import AES

def decrypt_key_file(base64_content, master_key_str):
    data = base64.b64decode(base64_content.replace(" ", ""))
    if len(data) <= 28:
        return None

    iv = data[:12]
    tag = data[12:28]
    ciphertext = data[28:]

    key = hashlib.sha256(master_key_str.encode('utf-8')).digest()

    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    try:
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)
        return decrypted.decode('utf-8')
    except Exception as e:
        print(f"Error during GCM decryption: {e}")
        return None

def decrypt_link(link_base64, key_str):
    try:
        decoded_str = base64.b64decode(link_base64).decode('utf-8')
        a, r = decoded_str.split(':')

        iv = base64.b64decode(a)
        ciphertext = base64.b64decode(r)

        # Key needs to be padded to 32 bytes with null chars
        key_bytes = key_str.encode('utf-8')
        if len(key_bytes) < 32:
            key_bytes = key_bytes.ljust(32, b'\0')
        else:
            key_bytes = key_bytes[:32]

        cipher = AES.new(key_bytes, AES.MODE_CBC, iv=iv)
        decrypted = cipher.decrypt(ciphertext)

        # PKCS7 unpadding
        padding_len = decrypted[-1]
        return decrypted[:-padding_len].decode('utf-8')
    except Exception as e:
        # print(f"Error during CBC decryption: {e}")
        return None

master_key = "b3f2a9d4c6e1f8a7b"
key_file_content = "Y9gqGtThwuAaYMbqxe3+fJv4hNF9qF8uGL5u9YSZeUXfKM4aWVwKzeg/BCCbcVcP"

real_key = decrypt_key_file(key_file_content, master_key)
print(f"Real Key: {real_key}")

link = "amxreWlnbHRkSjA2Rm1IT1BvZFVEZz09Ok4vcWp1Z3Vub3pFWjg0RG1ETGhuVWVjamxnMWpnSVIzcEhodEVGR2hSSXI5SlZlcjlQdjhXUVVVdzdxUXhxR3NkTjRhT1Via0k3R2srOERONjRPTzZRPT0="
if real_key:
    video_url = decrypt_link(link, real_key)
    print(f"Video URL: {video_url}")
