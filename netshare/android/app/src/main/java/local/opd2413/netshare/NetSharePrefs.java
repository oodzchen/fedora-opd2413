package local.opd2413.netshare;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

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

    public static final class HelperExecResult {
        public final int code;
        public final String output;

        public HelperExecResult(int code, String output) {
            this.code = code;
            this.output = output;
        }
    }

    private static final Object HELPER_LOCK = new Object();

    public static String ensureHelperExtracted(Context ctx) {
        synchronized (HELPER_LOCK) {
            Context app = ctx.getApplicationContext();
            File filesDir = app.getFilesDir();
            File tmp = new File(filesDir, "helper.sh.tmp");
            File dst = new File(filesDir, "helper.sh");
            try (InputStream in = app.getAssets().open("helper.sh");
                 FileOutputStream out = new FileOutputStream(tmp, false)) {
                byte[] buf = new byte[4096];
                int n;
                while ((n = in.read(buf)) > 0) {
                    out.write(buf, 0, n);
                }
                out.flush();
            } catch (IOException e) {
                Log.e("OPDNetShare", "extract helper.sh failed", e);
                return "";
            }
            tmp.setReadable(true, false);
            tmp.setExecutable(true, false);
            if (!tmp.renameTo(dst)) {
                return "";
            }
            dst.setReadable(true, false);
            dst.setExecutable(true, false);
            return dst.getAbsolutePath();
        }
    }

    public static HelperExecResult runSuHelper(String helperPath, long timeoutSec, String... args) {
        if (helperPath == null || helperPath.isEmpty()) {
            return new HelperExecResult(1, "helper.sh missing");
        }
        StringBuilder cmd = new StringBuilder();
        cmd.append("/system/bin/sh '").append(helperPath.replace("'", "")).append("'");
        for (String a : args) {
            cmd.append(" '").append(a.replace("'", "")).append("'");
        }
        try {
            Process proc = new ProcessBuilder("su", "-c", cmd.toString())
                    .redirectErrorStream(true)
                    .start();
            StringBuilder out = new StringBuilder();
            Thread reader = new Thread(() -> {
                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(proc.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        if (out.length() > 0) {
                            out.append('\n');
                        }
                        out.append(line);
                    }
                } catch (IOException ignored) {
                }
            });
            reader.start();
            boolean finished = proc.waitFor(timeoutSec, TimeUnit.SECONDS);
            if (!finished) {
                proc.destroyForcibly();
                reader.join(1000);
                return new HelperExecResult(124, "helper timeout");
            }
            reader.join(1000);
            return new HelperExecResult(proc.exitValue(), out.toString().trim());
        } catch (Exception e) {
            return new HelperExecResult(1, e.getMessage() == null ? "exec error" : e.getMessage());
        }
    }
}
