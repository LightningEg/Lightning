package org.lightning.app;

import android.os.Build;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyPermanentlyInvalidatedException;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.KeyStore;
import java.security.UnrecoverableKeyException;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Stay signed in on this phone (owner, 2026-11-01: "keep me logged in on the phone until I log out, not every time I
 * close it"). Python's lightning.security.biometric.FingerprintUnlock runs it, adapted as AndroidStay in
 * lightning_android.py: the same slot file and checks as fingerprint unlock, with this bridge in place of the prompt.
 *
 * The profile's data key is wrapped by an Android Keystore AES-256-GCM key (alias lightning-stay-PROFILE) that needs
 * no fingerprint, but that Android releases only while the phone itself is unlocked (setUnlockedDeviceRequired): the
 * phone's own screen lock guards it. The key never leaves the Keystore. Lock (sign out) deletes the key and the slot.
 * API 28 and up; below that nothing is offered. Answers are JSON as in BiometricBridge.
 */
@android.annotation.TargetApi(28)  // every entry is guarded by available(), which is false below API 28
public final class StayBridge {
    private static final String PROVIDER = "AndroidKeyStore";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int TAG_BITS = 128;

    private StayBridge() {}

    public static boolean available() {
        return Build.VERSION.SDK_INT >= 28;
    }

    /** A fresh Keystore key for the profile, and `plaintextB64` wrapped under it. */
    public static String encrypt(String profileId, String plaintextB64, String aadB64) {
        if (!available()) return reply("unavailable", null, null);
        try {
            deleteKey(profileId);  // never reuse an older key
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, newKey(profileId));
            cipher.updateAAD(Base64.decode(aadB64, Base64.NO_WRAP));
            byte[] wrapped = cipher.doFinal(Base64.decode(plaintextB64, Base64.NO_WRAP));
            return reply("ok", cipher.getIV(), wrapped);
        } catch (GeneralSecurityException | RuntimeException failed) {
            deleteKey(profileId);
            return reply("unavailable", null, null);
        }
    }

    /** `ciphertextB64` unwrapped with the profile's Keystore key, while the phone is unlocked. */
    public static String decrypt(String profileId, String ivB64, String ciphertextB64, String aadB64) {
        if (!available()) return reply("unavailable", null, null);
        try {
            KeyStore store = KeyStore.getInstance(PROVIDER);
            store.load(null);
            Key key = store.getKey(alias(profileId), null);
            if (key == null) return reply("invalidated", null, null);  // the key is gone: the slot opens nothing
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, Base64.decode(ivB64, Base64.NO_WRAP)));
            cipher.updateAAD(Base64.decode(aadB64, Base64.NO_WRAP));
            return reply("ok", null, cipher.doFinal(Base64.decode(ciphertextB64, Base64.NO_WRAP)));
        } catch (KeyPermanentlyInvalidatedException | UnrecoverableKeyException | AEADBadTagException invalidated) {
            return reply("invalidated", null, null);
        } catch (GeneralSecurityException | java.io.IOException | RuntimeException failed) {
            return reply("unavailable", null, null);  // for example the phone is locked: the password screen shows
        }
    }

    /** Remove the profile's Keystore key; harmless when there is none. */
    public static void deleteKey(String profileId) {
        try {
            KeyStore store = KeyStore.getInstance(PROVIDER);
            store.load(null);
            store.deleteEntry(alias(profileId));
        } catch (GeneralSecurityException | java.io.IOException | RuntimeException ignored) {
            // An orphan key opens nothing: its slot file is already gone.
        }
    }

    private static String alias(String profileId) {
        return "lightning-stay-" + profileId;
    }

    private static SecretKey newKey(String profileId) throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER);
        generator.init(new KeyGenParameterSpec.Builder(alias(profileId),
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setUnlockedDeviceRequired(true)  // only while the phone is unlocked (API 28)
                .build());
        return generator.generateKey();
    }

    private static String reply(String status, byte[] iv, byte[] data) {
        try {
            JSONObject out = new JSONObject().put("status", status);
            if (iv != null) out.put("iv", Base64.encodeToString(iv, Base64.NO_WRAP));
            if (data != null) out.put("data", Base64.encodeToString(data, Base64.NO_WRAP));
            return out.toString();
        } catch (JSONException impossible) {
            return "{\"status\":\"unavailable\"}";
        }
    }
}
