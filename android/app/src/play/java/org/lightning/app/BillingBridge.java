package org.lightning.app;

import android.app.Activity;
import com.android.billingclient.api.BillingClient;
import com.android.billingclient.api.BillingClientStateListener;
import com.android.billingclient.api.BillingFlowParams;
import com.android.billingclient.api.BillingResult;
import com.android.billingclient.api.PendingPurchasesParams;
import com.android.billingclient.api.ProductDetails;
import com.android.billingclient.api.Purchase;
import com.android.billingclient.api.QueryProductDetailsParams;
import com.android.billingclient.api.QueryPurchasesParams;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Themes sold with Google Play Billing, in the Play build only (src/play; NF-11B3). Python (AndroidBilling in
 * lightning_android.py) asks for prices, starts a purchase and reads what the person owns; it sends each purchase
 * token to the store's redeem-play function, which asks Google, acknowledges it and returns the signed licence the
 * app keeps as today. Product ids are the theme ids (papyrus, dendera, ...). A purchase carries the buying profile's id
 * as Play's obfuscated profile id, for the record only: one purchase per person (NF-10H), so every profile opened with
 * that Google account gets its own licence from the same purchase, up to 10. Nothing here decides
 * ownership: only the store's signed licence does. Calls from Python wait at most a few seconds for Play.
 */
public final class BillingBridge {
    private static final long WAIT_MS = 4000;
    private static volatile BillingClient client;
    private static final Map<String, ProductDetails> products = new ConcurrentHashMap<>();
    private static volatile List<Purchase> owned = Collections.emptyList();
    private static volatile String lastResult = "";

    private BillingBridge() {}

    private static synchronized BillingClient ready(Activity activity) throws InterruptedException {
        BillingClient current = client;
        if (current != null && current.isReady()) return current;
        if (current == null) {
            current = BillingClient.newBuilder(activity.getApplicationContext())
                    .setListener(BillingBridge::updated)
                    .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build())
                    .build();
            client = current;
        }
        CountDownLatch connected = new CountDownLatch(1);
        current.startConnection(new BillingClientStateListener() {
            @Override
            public void onBillingSetupFinished(BillingResult result) {
                connected.countDown();
            }

            @Override
            public void onBillingServiceDisconnected() {
                // The next call connects again.
            }
        });
        connected.await(WAIT_MS, TimeUnit.MILLISECONDS);
        return current;
    }

    /** Whether Play Billing answers on this phone (a phone without the Play Store has none). */
    public static boolean available() {
        Activity activity = MainActivity.current;
        if (activity == null) return false;
        try {
            return ready(activity).isReady();
        } catch (InterruptedException stopped) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    /** Play's own price for each product id, formatted in the person's currency: JSON {"papyrus": "EGP 99.99"}. */
    public static String prices(String idsJson) {
        JSONObject out = new JSONObject();
        Activity activity = MainActivity.current;
        if (activity == null) return out.toString();
        try {
            JSONArray ids = new JSONArray(idsJson);
            List<QueryProductDetailsParams.Product> list = new ArrayList<>();
            for (int i = 0; i < ids.length(); i++) {
                list.add(QueryProductDetailsParams.Product.newBuilder().setProductId(ids.getString(i))
                        .setProductType(BillingClient.ProductType.INAPP).build());
            }
            BillingClient billing = ready(activity);
            if (!billing.isReady() || list.isEmpty()) return out.toString();
            CountDownLatch done = new CountDownLatch(1);
            billing.queryProductDetailsAsync(QueryProductDetailsParams.newBuilder().setProductList(list).build(),
                    (result, details) -> {
                        if (result.getResponseCode() == BillingClient.BillingResponseCode.OK) {
                            for (ProductDetails item : details.getProductDetailsList()) products.put(item.getProductId(), item);
                        }
                        done.countDown();
                    });
            done.await(WAIT_MS, TimeUnit.MILLISECONDS);
            for (int i = 0; i < ids.length(); i++) {
                ProductDetails item = products.get(ids.getString(i));
                if (item != null && item.getOneTimePurchaseOfferDetails() != null) {
                    out.put(item.getProductId(), item.getOneTimePurchaseOfferDetails().getFormattedPrice());
                }
            }
        } catch (JSONException | InterruptedException ignored) {
            // No price: Settings says the store is not answering.
        }
        return out.toString();
    }

    /** Opens Play's purchase sheet for one theme, for this profile. False when Play cannot show it now. */
    public static boolean buy(String productId, String profileId) {
        Activity activity = MainActivity.current;
        ProductDetails item = products.get(productId);
        if (activity == null || item == null || client == null || !client.isReady()) return false;
        BillingFlowParams params = BillingFlowParams.newBuilder()
                .setProductDetailsParamsList(Collections.singletonList(
                        BillingFlowParams.ProductDetailsParams.newBuilder().setProductDetails(item).build()))
                .setObfuscatedProfileId(profileId)
                .build();
        activity.runOnUiThread(() -> client.launchBillingFlow(activity, params));
        return true;
    }

    /** What Play says this Google account owns (bought, or still pending): JSON [{product, token, state}]. */
    public static String purchases() {
        Activity activity = MainActivity.current;
        if (activity != null) {
            try {
                BillingClient billing = ready(activity);
                if (billing.isReady()) {
                    CountDownLatch done = new CountDownLatch(1);
                    billing.queryPurchasesAsync(QueryPurchasesParams.newBuilder()
                            .setProductType(BillingClient.ProductType.INAPP).build(), (result, list) -> {
                                if (result.getResponseCode() == BillingClient.BillingResponseCode.OK) owned = list;
                                done.countDown();
                            });
                    done.await(WAIT_MS, TimeUnit.MILLISECONDS);
                }
            } catch (InterruptedException stopped) {
                Thread.currentThread().interrupt();
            }
        }
        JSONArray out = new JSONArray();
        for (Purchase purchase : owned) {
            for (String product : purchase.getProducts()) {
                try {
                    out.put(new JSONObject().put("product", product).put("token", purchase.getPurchaseToken())
                            .put("state", purchase.getPurchaseState() == Purchase.PurchaseState.PURCHASED ? "purchased"
                                    : purchase.getPurchaseState() == Purchase.PurchaseState.PENDING ? "pending" : "unknown"));
                } catch (JSONException ignored) {
                    // never for these plain strings
                }
            }
        }
        return out.toString();
    }

    /** How the last purchase sheet ended: "ok", "cancelled", "error" or "" (none since the last call). */
    public static String takeResult() {
        String result = lastResult;
        lastResult = "";
        return result;
    }

    private static void updated(BillingResult result, List<Purchase> list) {
        int code = result.getResponseCode();
        lastResult = code == BillingClient.BillingResponseCode.OK ? "ok"
                : code == BillingClient.BillingResponseCode.USER_CANCELED ? "cancelled" : "error";
        if (code == BillingClient.BillingResponseCode.OK && list != null) {
            List<Purchase> merged = new ArrayList<>(owned);
            merged.addAll(list);
            owned = merged;
        }
        Activity activity = MainActivity.current;
        if (activity instanceof MainActivity) ((MainActivity) activity).openPath("/settings?play=1");  // unlock now
    }
}
