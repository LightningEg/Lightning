package org.lightning.app;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import java.util.ArrayList;

/** Runs one user-initiated dictation on the main thread. Audio stays in the device recognizer. */
final class ExpenseSpeech {
    static final int PERMISSION = 73;
    private final MainActivity activity;
    private SpeechRecognizer recognizer;
    private String request;
    private String language;

    ExpenseSpeech(MainActivity activity) { this.activity = activity; }

    static void deliver(android.webkit.WebView web, String id, String text, String reason) {
        String args = org.json.JSONObject.quote(id) + "," + org.json.JSONObject.quote(text) + "," + org.json.JSONObject.quote(reason);
        web.evaluateJavascript("window.lightningVoiceResult?.(" + args + ")", null);
    }

    boolean available() {
        return Build.VERSION.SDK_INT >= 31 && SpeechRecognizer.isOnDeviceRecognitionAvailable(activity);
    }

    void start(String id, String lang) {
        if (id == null || !id.matches("[a-zA-Z0-9-]{1,64}")) return;
        cancel();
        request = id;
        language = "ar-EG".equals(lang) ? lang : "en-US";
        if (!available()) { cancel(); return; }
        if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            activity.requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, PERMISSION);
        } else permission(true);
    }

    void permission(boolean granted) {
        if (request == null) return;
        if (!granted || Build.VERSION.SDK_INT < 31) { finish(request, "", "permission"); return; }
        final String id = request;
        try {
            recognizer = SpeechRecognizer.createOnDeviceSpeechRecognizer(activity);
            recognizer.setRecognitionListener(new RecognitionListener() {
                public void onReadyForSpeech(Bundle b) {}
                public void onBeginningOfSpeech() {}
                public void onRmsChanged(float f) {}
                public void onBufferReceived(byte[] bytes) {}
                public void onEndOfSpeech() {}
                public void onPartialResults(Bundle b) {}
                public void onEvent(int type, Bundle b) {}
                public void onError(int code) {
                    String reason = "retry";
                    if (code == SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED
                            || code == SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE) reason = "language";
                    if (code == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS) reason = "permission";
                    finish(id, "", reason);
                }
                public void onResults(Bundle b) {
                    ArrayList<String> words = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    finish(id, words == null || words.isEmpty() ? "" : words.get(0), "");
                }
            });
            Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, language);
            intent.putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true);
            recognizer.startListening(intent);
        } catch (RuntimeException unavailable) { cancel(); }
    }

    void cancel() { if (request != null) finish(request, "", "retry"); }

    private void finish(String id, String text, String reason) {
        if (!id.equals(request)) return;
        request = null;
        if (recognizer != null) {
            recognizer.destroy();
            recognizer = null;
        }
        activity.voiceResult(id, text, reason);
    }
}
