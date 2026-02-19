const crypto = require('crypto');

const MASTER_KEY = "b3f2a9d4c6e1f8a7b";

function decryptKey(base64Data) {
    try {
        const data = Buffer.from(base64Data, 'base64');
        if (data.length <= 28) return null;

        const iv = data.slice(0, 12);
        const tag = data.slice(12, 28);
        const ciphertext = data.slice(28);

        const key = crypto.createHash('sha256').update(MASTER_KEY).digest();
        const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
        decipher.setAuthTag(tag);

        let decrypted = decipher.update(ciphertext, 'binary', 'utf8');
        decrypted += decipher.final('utf8');
        return decrypted;
    } catch (e) {
        console.error('GCM Decrypt error:', e.message);
        return null;
    }
}

function decryptLink(linkBase64, keyStr) {
    try {
        const decoded = Buffer.from(linkBase64, 'base64').toString('utf8');
        const [ivB64, cipherB64] = decoded.split(':');

        const iv = Buffer.from(ivB64, 'base64');
        const ciphertext = Buffer.from(cipherB64, 'base64');

        const key = Buffer.alloc(32, 0);
        key.write(keyStr, 'utf8');

        const decipher = crypto.createDecipheriv('aes-256-cbc', key, iv);
        // Node handles PKCS7 padding by default
        let decrypted = decipher.update(ciphertext, 'binary', 'utf8');
        decrypted += decipher.final('utf8');
        return decrypted;
    } catch (e) {
        // console.error('CBC Decrypt error:', e.message);
        return null;
    }
}

module.exports = { decryptKey, decryptLink };
