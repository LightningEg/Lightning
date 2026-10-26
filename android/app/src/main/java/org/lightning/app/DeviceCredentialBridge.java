package org.lightning.app;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/** App-owned wrapping for transport keys. No exported components, UI or profile passwords.
 * The Keystore AES key is non-exportable. Python receives the transport key only
 * while loading a signing/TLS operation. Missing keys never trigger plaintext fallback.
 */
public final class DeviceCredentialBridge {
    private static final String ALIAS = "lightning-device-credentials-v1";
    private static final String PROVIDER = "AndroidKeyStore";
    private DeviceCredentialBridge() {}

    private static SecretKey key(boolean create) throws Exception {
        KeyStore store = KeyStore.getInstance(PROVIDER);
        store.load(null);
        if (store.containsAlias(ALIAS)) {
            return (SecretKey) store.getKey(ALIAS, null);
        }
        if (!create) throw new IllegalStateException("Device wrapping key unavailable");
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER);
        generator.init(new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build());
        return generator.generateKey();
    }

    private static byte[] decode(String value, int limit) {
        if (value == null || value.length() > limit * 2) throw new IllegalArgumentException();
        byte[] bytes = Base64.decode(value, Base64.NO_WRAP);
        if (bytes.length == 0 || bytes.length > limit) throw new IllegalArgumentException();
        return bytes;
    }

    private static String result(byte[] data) throws Exception {
        return new JSONObject().put("data", Base64.encodeToString(data, Base64.NO_WRAP)).toString();
    }

    public static synchronized String protect(String plaintext, String binding) {
        byte[] bytes = null;
        try {
            bytes = decode(plaintext, 16384);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key(true));
            cipher.updateAAD(decode(binding, 1024));
            byte[] encrypted = cipher.doFinal(bytes);
            byte[] wrapped = new byte[12 + encrypted.length];
            if (cipher.getIV().length != 12) throw new IllegalStateException();
            System.arraycopy(cipher.getIV(), 0, wrapped, 0, 12);
            System.arraycopy(encrypted, 0, wrapped, 12, encrypted.length);
            return result(wrapped);
        } catch (Exception failed) {
            return "{\"error\":\"unavailable\"}";
        } finally {
            if (bytes != null) Arrays.fill(bytes, (byte) 0);
        }
    }

    public static synchronized String unprotect(String ciphertext, String binding) {
        byte[] plaintext = null;
        try {
            byte[] wrapped = decode(ciphertext, 32768);
            if (wrapped.length < 29) throw new IllegalArgumentException();
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(false), new GCMParameterSpec(128, wrapped, 0, 12));
            cipher.updateAAD(decode(binding, 1024));
            plaintext = cipher.doFinal(wrapped, 12, wrapped.length - 12);
            return result(plaintext);
        } catch (Exception failed) {
            return "{\"error\":\"unavailable\"}";
        } finally {
            if (plaintext != null) Arrays.fill(plaintext, (byte) 0);
        }
    }
}
