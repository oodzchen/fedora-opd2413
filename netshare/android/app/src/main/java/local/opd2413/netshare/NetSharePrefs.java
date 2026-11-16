package local.opd2413.netshare;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.Locale;
import java.util.UUID;

public final class NetSharePrefs {
    public static final UUID ADV_UUID = UUID.fromString("e4a10001-6f2d-4c8a-9b1e-4f8a2d000001");
    public static final UUID RFCOMM_UUID = UUID.fromString("e4a10002-6f2d-4c8a-9b1e-4f8a2d000001");

    public static final String ACTION_START_LISTEN = "local.opd2413.netshare.START_LISTEN";
    public static final String ACTION_STOP_ALL = "local.opd2413.netshare.STOP_ALL";
    public static final String ACTION_DISCONNECT_SESSION = "local.opd2413.netshare.DISCONNECT_SESSION";
    public static final String ACTION_STATE_CHANGED = "local.opd2413.netshare.STATE_CHANGED";
    public static final String ACTION_BLE_MATCH = "local.opd2413.netshare.BLE_MATCH";
    public static final String ACTION_COMPANION_APPEARED = "local.opd2413.netshare.COMPANION_APPEARED";
    public static final String EXTRA_COMPANION_MAC = "companion_mac";

    private static final String PREF_NAME = "opd_netshare";
    private static final String KEY_ENABLED = "enabled";
    private static final String KEY_TARGET_MAC = "target_mac";
    private static final String KEY_TARGET_NAME = "target_name";

    public static final String STATE_DISABLED = "DISABLED";
    public static final String STATE_SCANNING = "SCANNING";
    public static final String STATE_CONNECTING = "CONNECTING";
    public static final String STATE_CONNECTED = "CONNECTED";
    public static final String STATE_ERROR = "ERROR";

    private static final Object LOG_LOCK = new Object();
    private static final ArrayDeque<String> LOGS = new ArrayDeque<>();
    private static volatile String sState = STATE_DISABLED;
    private static volatile String sDetail = "未启动";
    private static volatile String sP2pIp = "";
    private static volatile String sUpstream = "";

    private NetSharePrefs() {}

    private static SharedPreferences prefs(Context ctx) {
        return ctx.getApplicationContext().getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
    }

    public static boolean isEnabled(Context ctx) {
        return prefs(ctx).getBoolean(KEY_ENABLED, false);
    }

    public static void setEnabled(Context ctx, boolean enabled) {
        prefs(ctx).edit().putBoolean(KEY_ENABLED, enabled).apply();
    }

    public static String getTargetMac(Context ctx) {
        String raw = prefs(ctx).getString(KEY_TARGET_MAC, "");
        return raw == null ? "" : raw.trim().toUpperCase(Locale.ROOT);
    }

    public static String getTargetName(Context ctx) {
        String raw = prefs(ctx).getString(KEY_TARGET_NAME, "");
        return raw == null ? "" : raw.trim();
    }

    public static void setTargetDevice(Context ctx, String mac, String name) {
        String cleanMac = mac == null ? "" : mac.trim().toUpperCase(Locale.ROOT);
        String cleanName = name == null ? "" : name.trim();
        prefs(ctx).edit()
                .putString(KEY_TARGET_MAC, cleanMac)
                .putString(KEY_TARGET_NAME, cleanName)
                .apply();
    }

    public static void setStatus(String state, String detail, String p2pIp, String upstream) {
        sState = state;
        sDetail = detail;
        sP2pIp = p2pIp == null ? "" : p2pIp;
        sUpstream = upstream == null ? "" : upstream;
    }

    public static String getState() {
        return sState;
    }

    public static String getDetail() {
        return sDetail;
    }

    public static String getP2pIp() {
        return sP2pIp;
    }

    public static String getUpstream() {
        return sUpstream;
    }

    public static void appendLog(String msg) {
        String ts = new SimpleDateFormat("HH:mm:ss", Locale.ROOT).format(new Date());
        Log.i("OPDNetShare", msg);
        synchronized (LOG_LOCK) {
            if (LOGS.size() >= 80) {
                LOGS.removeFirst();
            }
            LOGS.addLast(ts + " " + msg);
        }
    }

    public static String getLogsText() {
        synchronized (LOG_LOCK) {
            StringBuilder sb = new StringBuilder();
            for (String line : LOGS) {
                sb.append(line).append('\n');
            }
            return sb.toString();
        }
    }

    public static int getLogCount() {
        synchronized (LOG_LOCK) {
            return LOGS.size();
        }
    }

    public static void clearLogs() {
        synchronized (LOG_LOCK) {
            LOGS.clear();
        }
    }
}
