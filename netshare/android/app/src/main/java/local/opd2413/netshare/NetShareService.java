package local.opd2413.netshare;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothSocket;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.companion.AssociationInfo;
import android.companion.CompanionDeviceManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.RouteInfo;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.ParcelUuid;
import android.os.PowerManager;
import android.os.SystemClock;
import android.service.quicksettings.TileService;
import android.util.Log;
import android.content.ComponentName;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class NetShareService extends Service {
    private static final String TAG = "OPDNetShare";
    private static final String CHANNEL_ID = "opd_netshare";
    private static final int NOTIF_ID = 2413;
    private static final int BLE_SCAN_REQ_CODE = 2414;

    private static final Pattern SAFE_TOKEN = Pattern.compile("^[A-Za-z0-9._-]{1,64}$");
    private static final Pattern SAFE_PSK = Pattern.compile("^[A-Za-z0-9._-]{8,63}$");
    private static final Pattern SAFE_V6 = Pattern.compile("^[0-9a-fA-F:]{2,64}$");
    private static final Pattern STA_FREQ_PAT = Pattern.compile("sta_freq=(\\d+)");

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService helperExecutor = Executors.newSingleThreadExecutor();
    private final ExecutorService netExecutor = Executors.newCachedThreadPool();

    private BluetoothManager btManager;
    private BluetoothAdapter btAdapter;
    private BluetoothLeScanner bleScanner;
    private CompanionDeviceManager companionManager;
    private ConnectivityManager connManager;
    private NotificationManager notifManager;
    private PowerManager powerManager;

    private final Object netLock = new Object();
    private final Object writerLock = new Object();
    private final Map<Network, PhysNet> physNets = new LinkedHashMap<>();
    private String currentBestUpstream = "none";
    private String currentBestV6If = "none";
    private String currentBestTabletV6 = "";
    private boolean currentBestIsWifi = false;

    private volatile boolean scanning = false;
    private volatile boolean burstScanning = false;
    private volatile boolean connecting = false;
    private volatile boolean p2pActive = false;
    private volatile String activeOutIf = "";
    private volatile String activeP2pIp = "";
    private volatile String activeV6OutIf = "none";
    private volatile String activeV6Ip = "";
    private volatile String activeV6Ll = "";
    private volatile String activeTabletLl = "none";
    private volatile long lastAttemptMs = 0L;
    private volatile long lastScanRestartMs = 0L;
    private volatile String lastCompanionObservedMac = "";
    private volatile BluetoothSocket activeSocket = null;
    private volatile OutputStreamWriter activeWriter = null;
    private String helperPath = "";
    private final Runnable stopBurstScanTask = this::stopBurstBleScan;

    private static final class PhysNet {
        String iface = "";
        String v4Iface = "";
        String tabletV6 = "";
        boolean wifi;
        boolean cellular;
        boolean validated;
    }

    private static final class ExecResult {
        final int code;
        final String output;

        ExecResult(int code, String output) {
            this.code = code;
            this.output = output;
        }
    }

    private final BroadcastReceiver btStateReceiver = new BroadcastReceiver() {
        @SuppressLint("MissingPermission")
        @Override
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if (BluetoothAdapter.ACTION_STATE_CHANGED.equals(action)) {
                int st = intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, BluetoothAdapter.ERROR);
                if (st == BluetoothAdapter.STATE_OFF || st == BluetoothAdapter.STATE_TURNING_OFF) {
                    log("蓝牙已关闭，停止 BLE 扫描");
                    stopBleScan();
                    closeActiveSocket();
                } else if (st == BluetoothAdapter.STATE_ON) {
                    log("蓝牙已开启，恢复检查监听");
                    lastAttemptMs = 0L;
                    if (NetSharePrefs.isEnabled(NetShareService.this) && !isSessionBusy()) {
                        startBleScan();
                    }
                }
            } else if (BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(action)) {
                BluetoothDevice dev = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice.class);
                int bond = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.ERROR);
                String mac = (dev != null && dev.getAddress() != null)
                        ? dev.getAddress().trim().toUpperCase(Locale.ROOT)
                        : "";
                String targetMac = NetSharePrefs.getTargetMac(NetShareService.this);
                if (!mac.isEmpty() && mac.equals(targetMac)) {
                    if (bond == BluetoothDevice.BOND_BONDED) {
                        lastAttemptMs = 0L;
                        log("目标蓝牙已重新配对 (" + mac + ")，刷新 BLE 扫描");
                        if (NetSharePrefs.isEnabled(NetShareService.this) && !isSessionBusy()) {
                            stopBleScan();
                            startBleScan();
                        }
                    } else if (bond == BluetoothDevice.BOND_NONE) {
                        lastAttemptMs = 0L;
                        log("目标蓝牙配对已解除 (" + mac + ")");
                        closeActiveSocket();
                        if (NetSharePrefs.isEnabled(NetShareService.this) && !isSessionBusy()) {
                            updateStatus(NetSharePrefs.STATE_SCANNING, "目标蓝牙已取消配对，等待重新配对...", "", currentUpstreamLabel());
                        }
                    }
                } else if (bond == BluetoothDevice.BOND_BONDED) {
                    lastAttemptMs = 0L;
                }
            } else if (Intent.ACTION_SCREEN_ON.equals(action) || Intent.ACTION_USER_PRESENT.equals(action)) {
                if (Intent.ACTION_USER_PRESENT.equals(action)) {
                    lastAttemptMs = 0L;
                }
                if (NetSharePrefs.isEnabled(NetShareService.this) && !isSessionBusy()) {
                    log("屏幕唤醒/解锁，刷新 BLE 扫描以快速发现平板");
                    restartBleScanAndBurst();
                }
            }
        }
    };

    private final ScanCallback burstScanCallback = new ScanCallback() {
        @SuppressLint("MissingPermission")
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            if (result == null) {
                return;
            }
            BluetoothDevice dev = result.getDevice();
            if (dev == null || dev.getAddress() == null) {
                return;
            }
            String cleanMac = dev.getAddress().trim().toUpperCase(Locale.ROOT);
            String targetMac = NetSharePrefs.getTargetMac(NetShareService.this);
            if (!targetMac.isEmpty() && targetMac.equals(cleanMac)) {
                stopBurstBleScan();
                handleMatchedDevice(dev);
            }
        }

        @Override
        public void onScanFailed(int errorCode) {
            burstScanning = false;
        }
    };

    private final ConnectivityManager.NetworkCallback netCallback = new ConnectivityManager.NetworkCallback() {
        @Override
        public void onAvailable(Network network) {
            updateNetworkRecord(network);
        }

        @Override
        public void onCapabilitiesChanged(Network network, NetworkCapabilities caps) {
            updateNetworkRecord(network, caps, null);
        }

        @Override
        public void onLinkPropertiesChanged(Network network, LinkProperties lp) {
            updateNetworkRecord(network, null, lp);
        }

        @Override
        public void onLost(Network network) {
            synchronized (netLock) {
                physNets.remove(network);
                recomputeUpstreamLocked();
            }
        }
    };

    private PendingIntent getBleScanPendingIntent() {
        Intent i = new Intent(this, BleScanReceiver.class);
        i.setAction(NetSharePrefs.ACTION_BLE_MATCH);
        return PendingIntent.getBroadcast(
                this,
                BLE_SCAN_REQ_CODE,
                i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE
        );
    }

    @SuppressLint("MissingPermission")
    private synchronized void handleMatchedDevice(BluetoothDevice dev) {
        if (!NetSharePrefs.isEnabled(this)) {
            log("收到 BLE 匹配但监听已关闭，忽略");
            return;
        }
        if (isSessionBusy()) {
            log("收到 BLE 匹配但会话忙碌 (connecting=" + connecting + ", p2p=" + p2pActive + ")，忽略");
            return;
        }
        if (!hasBtPermissions()) {
            log("收到 BLE 匹配但缺少蓝牙权限");
            return;
        }
        if (dev == null || dev.getAddress() == null) {
            log("收到 BLE 匹配但设备地址为空");
            return;
        }
        String cleanMac = dev.getAddress().trim().toUpperCase(Locale.ROOT);
        String targetMac = NetSharePrefs.getTargetMac(this);
        if (targetMac.isEmpty() || !targetMac.equals(cleanMac)) {
            log("忽略非目标设备匹配: " + cleanMac + " != " + targetMac);
            return;
        }
        int bondState = dev.getBondState();
        if (bondState != BluetoothDevice.BOND_BONDED) {
            log("忽略未配对设备广播: " + cleanMac + " (bondState=" + bondState + ")");
            return;
        }
        long now = SystemClock.elapsedRealtime();
        long elapsed = now - lastAttemptMs;
        if (lastAttemptMs != 0L && elapsed < 4_000L) {
            log("距上次 RFCOMM 尝试仅 " + elapsed + "ms，退避等待");
            return;
        }
        lastAttemptMs = now;
        connecting = true;
        stopBurstBleScan();
        updateStatus(NetSharePrefs.STATE_CONNECTING, "发现平板唤醒广播，正在建立控制通道...", "", "");
        log("检测到平板 BLE 广播，连接 RFCOMM: " + cleanMac);
        netExecutor.execute(() -> runRfcommSession(dev));
    }

    @Override
    public void onCreate() {
        super.onCreate();
        btManager = (BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE);
        btAdapter = btManager != null ? btManager.getAdapter() : null;
        companionManager = getSystemService(CompanionDeviceManager.class);
        connManager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        notifManager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        powerManager = (PowerManager) getSystemService(Context.POWER_SERVICE);

        createNotificationChannel();
        helperPath = extractHelper();

        startForeground(
                NOTIF_ID,
                buildNotification("正在初始化..."),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
        );

        IntentFilter btFilter = new IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED);
        btFilter.addAction(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
        btFilter.addAction(Intent.ACTION_SCREEN_ON);
        btFilter.addAction(Intent.ACTION_USER_PRESENT);
        registerReceiver(
                btStateReceiver,
                btFilter,
                Context.RECEIVER_EXPORTED
        );

        if (connManager != null) {
            NetworkRequest req = new NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)
                    .build();
            connManager.registerNetworkCallback(req, netCallback);
            refreshAllPhysicalNets();
        }
        log("NetShareService 已创建");
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null ? intent.getAction() : NetSharePrefs.ACTION_START_LISTEN;
        if (NetSharePrefs.ACTION_STOP_ALL.equals(action)) {
            NetSharePrefs.setEnabled(this, false);
            stopEverythingAndExit();
            return START_NOT_STICKY;
        }
        if (NetSharePrefs.ACTION_DISCONNECT_SESSION.equals(action)) {
            disconnectCurrentSessionOnly();
            return START_STICKY;
        }
        if (NetSharePrefs.ACTION_BLE_MATCH.equals(action)) {
            if (!NetSharePrefs.isEnabled(this)) {
                stopEverythingAndExit();
                return START_NOT_STICKY;
            }
            BluetoothDevice dev = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice.class);
            if (!isSessionBusy() && !scanning) {
                startBleScan();
            }
            handleMatchedDevice(dev);
            return START_STICKY;
        }
        if (NetSharePrefs.ACTION_COMPANION_APPEARED.equals(action)) {
            if (!NetSharePrefs.isEnabled(this)) {
                stopEverythingAndExit();
                return START_NOT_STICKY;
            }
            String mac = intent != null ? intent.getStringExtra(NetSharePrefs.EXTRA_COMPANION_MAC) : "";
            if ((mac == null || mac.isEmpty())) {
                mac = NetSharePrefs.getTargetMac(this);
            }
            if (btAdapter != null && mac != null && !mac.isEmpty() && hasBtPermissions()) {
                try {
                    BluetoothDevice dev = btAdapter.getRemoteDevice(mac);
                    handleMatchedDevice(dev);
                } catch (IllegalArgumentException ignored) {
                }
            }
            if (!isSessionBusy() && !scanning) {
                startBleScan();
            }
            return START_STICKY;
        }

        if (!NetSharePrefs.isEnabled(this)) {
            stopEverythingAndExit();
            return START_NOT_STICKY;
        }

        if (!hasBtPermissions()) {
            updateStatus(NetSharePrefs.STATE_ERROR, "缺少蓝牙权限，请在主界面授权", "", "");
            log("缺少 BLUETOOTH_SCAN / BLUETOOTH_CONNECT 权限");
            return START_STICKY;
        }
        if (NetSharePrefs.getTargetMac(this).isEmpty()) {
            updateStatus(NetSharePrefs.STATE_ERROR, "未选择目标平板，请在主界面选择已配对平板", "", "");
            return START_STICKY;
        }
        ensureCompanionPresence();
        if (!isSessionBusy()) {
            restartBleScanAndBurst();
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        try {
            unregisterReceiver(btStateReceiver);
        } catch (Exception ignored) {
        }
        if (connManager != null) {
            try {
                connManager.unregisterNetworkCallback(netCallback);
            } catch (Exception ignored) {
            }
        }
        if (!NetSharePrefs.isEnabled(this)) {
            stopBleScan();
        }
        closeActiveSocket();
        try {
            Future<?> f = helperExecutor.submit(() -> runHelper("down"));
            f.get(8, TimeUnit.SECONDS);
        } catch (Exception ignored) {
        }
        helperExecutor.shutdownNow();
        netExecutor.shutdownNow();
        updateStatus(NetSharePrefs.STATE_DISABLED, "已停止", "", "");
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private boolean isSessionBusy() {
        return connecting || p2pActive || activeSocket != null;
    }

    private boolean hasBtPermissions() {
        return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private void createNotificationChannel() {
        if (notifManager == null) {
            return;
        }
        NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notif_channel_name),
                NotificationManager.IMPORTANCE_LOW
        );
        ch.setShowBadge(false);
        notifManager.createNotificationChannel(ch);
    }

    private Notification buildNotification(String content) {
        Intent openIntent = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(
                this,
                0,
                openIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Intent stopIntent = new Intent(this, NetShareService.class);
        stopIntent.setAction(NetSharePrefs.ACTION_STOP_ALL);
        PendingIntent stopPi = PendingIntent.getService(
                this,
                1,
                stopIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_opd_share)
                .setContentTitle("OPD 跨设备网络共享")
                .setContentText(content)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setContentIntent(pi)
                .addAction(new Notification.Action.Builder(null, "关闭", stopPi).build())
                .build();
    }

    private void updateStatus(String state, String detail, String p2pIp, String upstream) {
        NetSharePrefs.setStatus(state, detail, p2pIp, upstream);
        if (notifManager != null) {
            notifManager.notify(NOTIF_ID, buildNotification(detail));
        }
        Intent b = new Intent(NetSharePrefs.ACTION_STATE_CHANGED);
        b.setPackage(getPackageName());
        sendBroadcast(b);
        try {
            TileService.requestListeningState(this, new ComponentName(this, NetShareTileService.class));
        } catch (Exception ignored) {
        }
    }

    private void log(String msg) {
        Log.i(TAG, msg);
        NetSharePrefs.appendLog(msg);
        Intent b = new Intent(NetSharePrefs.ACTION_STATE_CHANGED);
        b.setPackage(getPackageName());
        sendBroadcast(b);
    }

    private String extractHelper() {
        File dst = new File(getFilesDir(), "helper.sh");
        try (InputStream in = getAssets().open("helper.sh");
             FileOutputStream out = new FileOutputStream(dst, false)) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            out.flush();
        } catch (IOException e) {
            log("释放 helper.sh 失败: " + e.getMessage());
            return "";
        }
        dst.setReadable(true, false);
        dst.setExecutable(true, false);
        return dst.getAbsolutePath();
    }

    private ExecResult runHelper(String... args) {
        if (helperPath.isEmpty()) {
            helperPath = extractHelper();
        }
        if (helperPath.isEmpty()) {
            return new ExecResult(1, "helper.sh missing");
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
            boolean finished = proc.waitFor(28, TimeUnit.SECONDS);
            if (!finished) {
                proc.destroyForcibly();
                reader.join(1000);
                return new ExecResult(124, "helper timeout");
            }
            reader.join(1000);
            return new ExecResult(proc.exitValue(), out.toString().trim());
        } catch (Exception e) {
            return new ExecResult(1, e.getMessage() == null ? "exec error" : e.getMessage());
        }
    }

    @SuppressLint("MissingPermission")
    private void ensureCompanionPresence() {
        if (companionManager == null || !hasBtPermissions()) {
            return;
        }
        String targetMac = NetSharePrefs.getTargetMac(this);
        if (targetMac.isEmpty()) {
            return;
        }
        try {
            List<AssociationInfo> list = companionManager.getMyAssociations();
            if (list == null) {
                return;
            }
            for (AssociationInfo info : list) {
                if (info == null || info.getDeviceMacAddress() == null) {
                    continue;
                }
                String mac = info.getDeviceMacAddress().toString().trim().toUpperCase(Locale.ROOT);
                if (targetMac.equals(mac)) {
                    companionManager.startObservingDevicePresence(mac);
                    if (!mac.equals(lastCompanionObservedMac)) {
                        lastCompanionObservedMac = mac;
                        log("已启用 CDM 系统伴侣后台监听: " + mac);
                    }
                    return;
                }
            }
        } catch (Exception e) {
            log("CDM 伴侣监听启用失败: " + e.getMessage());
        }
    }

    private synchronized void restartBleScanAndBurst() {
        long now = SystemClock.elapsedRealtime();
        if (scanning && burstScanning && (now - lastScanRestartMs) < 1_500L) {
            return;
        }
        lastScanRestartMs = now;
        stopBleScan();
        startBleScan();
        startBurstBleScan(20_000L);
    }

    @SuppressLint("MissingPermission")
    private synchronized void startBurstBleScan(long durationMs) {
        if (!NetSharePrefs.isEnabled(this) || isSessionBusy() || !hasBtPermissions()) {
            return;
        }
        if (btAdapter == null || !btAdapter.isEnabled()) {
            return;
        }
        BluetoothLeScanner scanner = bleScanner != null ? bleScanner : btAdapter.getBluetoothLeScanner();
        if (scanner == null) {
            return;
        }
        if (burstScanning) {
            mainHandler.removeCallbacks(stopBurstScanTask);
            mainHandler.postDelayed(stopBurstScanTask, durationMs);
            return;
        }
        ScanFilter filter = new ScanFilter.Builder()
                .setServiceUuid(new ParcelUuid(NetSharePrefs.ADV_UUID))
                .build();
        ScanSettings settings = new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .setCallbackType(ScanSettings.CALLBACK_TYPE_ALL_MATCHES)
                .setMatchMode(ScanSettings.MATCH_MODE_AGGRESSIVE)
                .setLegacy(false)
                .build();
        try {
            scanner.startScan(Collections.singletonList(filter), settings, burstScanCallback);
            burstScanning = true;
            mainHandler.removeCallbacks(stopBurstScanTask);
            mainHandler.postDelayed(stopBurstScanTask, durationMs);
            log("启动低延迟突击 BLE 扫描 (" + (durationMs / 1000L) + "s)");
        } catch (Exception e) {
            burstScanning = false;
        }
    }

    @SuppressLint("MissingPermission")
    private synchronized void stopBurstBleScan() {
        mainHandler.removeCallbacks(stopBurstScanTask);
        if (!burstScanning) {
            return;
        }
        burstScanning = false;
        if (btAdapter == null || !btAdapter.isEnabled() || !hasBtPermissions()) {
            return;
        }
        BluetoothLeScanner scanner = bleScanner != null ? bleScanner : btAdapter.getBluetoothLeScanner();
        if (scanner != null) {
            try {
                scanner.stopScan(burstScanCallback);
            } catch (Exception ignored) {
            }
        }
    }

    @SuppressLint("MissingPermission")
    private synchronized void startBleScan() {
        if (!NetSharePrefs.isEnabled(this)) {
            return;
        }
        if (scanning) {
            return;
        }
        if (!hasBtPermissions()) {
            updateStatus(NetSharePrefs.STATE_ERROR, "缺少蓝牙权限", "", "");
            return;
        }
        if (btAdapter == null || !btAdapter.isEnabled()) {
            updateStatus(NetSharePrefs.STATE_SCANNING, "等待手机蓝牙开启...", "", "");
            return;
        }
        bleScanner = btAdapter.getBluetoothLeScanner();
        if (bleScanner == null) {
            updateStatus(NetSharePrefs.STATE_ERROR, "BluetoothLeScanner 不可用", "", "");
            return;
        }
        ScanFilter filter = new ScanFilter.Builder()
                .setServiceUuid(new ParcelUuid(NetSharePrefs.ADV_UUID))
                .build();
        ScanSettings settings = new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_BALANCED)
                .setCallbackType(ScanSettings.CALLBACK_TYPE_ALL_MATCHES)
                .setMatchMode(ScanSettings.MATCH_MODE_AGGRESSIVE)
                .setLegacy(false)
                .build();
        try {
            int rc = bleScanner.startScan(Collections.singletonList(filter), settings, getBleScanPendingIntent());
            if (rc != 0 && rc != ScanCallback.SCAN_FAILED_ALREADY_STARTED) {
                scanning = false;
                updateStatus(NetSharePrefs.STATE_ERROR, "BLE 扫描启动失败 (" + rc + ")", "", "");
                log("PendingIntent startScan 失败: rc=" + rc);
                return;
            }
            scanning = true;
            String name = NetSharePrefs.getTargetName(this);
            String label = name.isEmpty() ? NetSharePrefs.getTargetMac(this) : name;
            updateStatus(NetSharePrefs.STATE_SCANNING, "低功耗待命监听中 (" + label + ")", "", currentUpstreamLabel());
            log("开始硬件过滤 PendingIntent BLE 监听 (rc=" + rc + ")");
        } catch (Exception e) {
            scanning = false;
            updateStatus(NetSharePrefs.STATE_ERROR, "BLE 启动异常: " + e.getMessage(), "", "");
            log("startScan 异常: " + e.getMessage());
        }
    }

    @SuppressLint("MissingPermission")
    private synchronized void stopBleScan() {
        scanning = false;
        stopBurstBleScan();
        if (btAdapter == null || !btAdapter.isEnabled() || !hasBtPermissions()) {
            return;
        }
        BluetoothLeScanner scanner = bleScanner != null ? bleScanner : btAdapter.getBluetoothLeScanner();
        if (scanner != null) {
            try {
                scanner.stopScan(getBleScanPendingIntent());
            } catch (Exception ignored) {
            }
        }
    }

    private String extractStackedV4(LinkProperties lp) {
        for (RouteInfo ri : lp.getRoutes()) {
            String routeIf = ri != null ? ri.getInterface() : null;
            if (routeIf != null && routeIf.startsWith("v4-") && SAFE_TOKEN.matcher(routeIf).matches()) {
                return routeIf;
            }
        }
        return "";
    }

    private String extractTabletV6(LinkProperties lp) {
        boolean hasV6Default = false;
        for (RouteInfo ri : lp.getRoutes()) {
            if (ri != null && ri.isDefaultRoute()
                    && ri.getDestination() != null
                    && ri.getDestination().getAddress() instanceof Inet6Address) {
                hasV6Default = true;
                break;
            }
        }
        if (!hasV6Default) {
            return "";
        }
        for (LinkAddress la : lp.getLinkAddresses()) {
            if (la == null) {
                continue;
            }
            InetAddress addr = la.getAddress();
            if (!(addr instanceof Inet6Address)) {
                continue;
            }
            if (addr.isLinkLocalAddress() || addr.isLoopbackAddress()
                    || addr.isMulticastAddress() || addr.isSiteLocalAddress()) {
                continue;
            }
            byte[] b = addr.getAddress();
            if (b == null || b.length != 16) {
                continue;
            }
            // Global Unicast 2000::/3 only (excludes ULA fc00::/7) so OS & Tailscale prefer IPv6.
            if ((b[0] & 0xe0) != 0x20) {
                continue;
            }
            byte[] out = new byte[16];
            System.arraycopy(b, 0, out, 0, 8);
            out[8] = 0x00;
            out[9] = 0x00;
            out[10] = 0x24;
            out[11] = 0x13;
            out[12] = 0x00;
            out[13] = 0x49;
            out[14] = 0x00;
            out[15] = 0x01;
            try {
                String host = InetAddress.getByAddress(out).getHostAddress();
                if (host != null && SAFE_V6.matcher(host).matches()) {
                    return host;
                }
            } catch (Exception ignored) {
            }
        }
        return "";
    }

    private void refreshAllPhysicalNets() {
        if (connManager == null) {
            return;
        }
        Network[] nets = connManager.getAllNetworks();
        synchronized (netLock) {
            physNets.clear();
            for (Network n : nets) {
                NetworkCapabilities caps = connManager.getNetworkCapabilities(n);
                LinkProperties lp = connManager.getLinkProperties(n);
                if (caps == null || lp == null) {
                    continue;
                }
                if (!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                        || !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)) {
                    continue;
                }
                String ifc = lp.getInterfaceName();
                if (ifc == null || ifc.isEmpty()) {
                    continue;
                }
                PhysNet p = new PhysNet();
                p.iface = ifc;
                p.v4Iface = extractStackedV4(lp);
                p.tabletV6 = extractTabletV6(lp);
                p.wifi = caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI);
                p.cellular = caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR);
                p.validated = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
                physNets.put(n, p);
            }
            recomputeUpstreamLocked();
        }
    }

    private void updateNetworkRecord(Network network) {
        if (connManager == null) {
            return;
        }
        updateNetworkRecord(
                network,
                connManager.getNetworkCapabilities(network),
                connManager.getLinkProperties(network)
        );
    }

    private void updateNetworkRecord(Network network, NetworkCapabilities capsIn, LinkProperties lpIn) {
        if (connManager == null) {
            return;
        }
        NetworkCapabilities caps = capsIn != null ? capsIn : connManager.getNetworkCapabilities(network);
        LinkProperties lp = lpIn != null ? lpIn : connManager.getLinkProperties(network);
        synchronized (netLock) {
            if (caps == null || lp == null
                    || !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    || !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)) {
                physNets.remove(network);
                recomputeUpstreamLocked();
                return;
            }
            String ifc = lp.getInterfaceName();
            if (ifc == null || ifc.isEmpty()) {
                physNets.remove(network);
                recomputeUpstreamLocked();
                return;
            }
            PhysNet p = new PhysNet();
            p.iface = ifc;
            p.v4Iface = extractStackedV4(lp);
            p.tabletV6 = extractTabletV6(lp);
            p.wifi = caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI);
            p.cellular = caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR);
            p.validated = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
            physNets.put(network, p);
            recomputeUpstreamLocked();
        }
    }

    private void writeJsonLine(OutputStreamWriter w, JSONObject obj) throws IOException {
        if (w == null || obj == null) {
            return;
        }
        synchronized (writerLock) {
            w.write(obj.toString() + "\n");
            w.flush();
        }
    }

    private void recomputeUpstreamLocked() {
        String best = "none";
        String bestV6If = "none";
        String bestTabletV6 = "";
        boolean bestIsWifi = false;
        int bestScore = -1;
        for (PhysNet p : physNets.values()) {
            String candidate = !p.v4Iface.isEmpty() ? p.v4Iface : p.iface;
            if (!SAFE_TOKEN.matcher(candidate).matches() || !SAFE_TOKEN.matcher(p.iface).matches()) {
                continue;
            }
            int score = 0;
            if (p.validated) {
                score += 100;
            }
            if (!p.v4Iface.isEmpty()) {
                score += 5;
            }
            if (!p.tabletV6.isEmpty()) {
                score += 3;
            }
            if (p.wifi) {
                score += 30;
            } else if (p.cellular) {
                score += 20;
            } else {
                score += 10;
            }
            if (score > bestScore) {
                bestScore = score;
                best = candidate;
                bestV6If = !p.tabletV6.isEmpty() ? p.iface : "none";
                bestTabletV6 = p.tabletV6;
                bestIsWifi = p.wifi;
            }
        }
        String prev = currentBestUpstream;
        String prevV6If = currentBestV6If;
        String prevV6Ip = currentBestTabletV6;
        currentBestUpstream = best;
        currentBestV6If = bestV6If;
        currentBestTabletV6 = bestTabletV6;
        currentBestIsWifi = bestIsWifi;
        boolean v4Changed = !best.equals(prev);
        boolean v6Changed = !bestV6If.equals(prevV6If) || !bestTabletV6.equals(prevV6Ip);
        boolean needRetryActiveNone = p2pActive && !"none".equals(best)
                && ("none".equals(activeOutIf) || activeOutIf.isEmpty());
        if (v4Changed || v6Changed || needRetryActiveNone) {
            if (v4Changed || v6Changed) {
                log("物理网络出口变化: " + prev + " -> " + best
                        + (bestTabletV6.isEmpty() ? " (无IPv6)" : " (IPv6=" + bestTabletV6 + ")"));
            }
            if (p2pActive) {
                final String target = best;
                final String targetV6If = bestV6If;
                final String targetV6Ip = bestTabletV6;
                final String targetTabletLl = activeTabletLl;
                helperExecutor.execute(() -> {
                    if (!p2pActive) {
                        return;
                    }
                    ExecResult res = runHelper(
                            "switch",
                            target,
                            targetV6If,
                            targetV6Ip.isEmpty() ? "none" : targetV6Ip,
                            targetTabletLl.isEmpty() ? "none" : targetTabletLl
                    );
                    if (res.code == 0 && res.output.startsWith("OK switch ")) {
                        String[] parts = res.output.split("\\s+");
                        String outIf = parts.length >= 3 ? parts[2] : target;
                        String v6Ll = (parts.length >= 4 && !"none".equals(parts[3])) ? parts[3] : "";
                        String v6Out = (parts.length >= 5 && !"none".equals(parts[4])) ? parts[4] : "none";
                        String v6Ip = (!"none".equals(v6Out) && !v6Ll.isEmpty() && !targetV6Ip.isEmpty())
                                ? targetV6Ip : "";
                        activeOutIf = outIf;
                        activeV6Ll = v6Ll;
                        activeV6OutIf = v6Out;
                        activeV6Ip = v6Ip;
                        log("已切换物理出口 -> " + outIf + (v6Ip.isEmpty() ? "" : " (v6=" + v6Ip + ")"));
                        updateStatus(
                                NetSharePrefs.STATE_CONNECTED,
                                "已连接共享 (" + activeP2pIp + " -> " + outIf + (v6Ip.isEmpty() ? "" : ", IPv6") + ")",
                                activeP2pIp,
                                outIf
                        );
                        OutputStreamWriter w = activeWriter;
                        if (w != null) {
                            try {
                                JSONObject upd = new JSONObject();
                                upd.put("event", "upstream_update");
                                upd.put("ip", activeP2pIp);
                                upd.put("upstream", outIf);
                                upd.put("v6_ll", v6Ll);
                                upd.put("v6_ip", v6Ip);
                                upd.put("v6_out", v6Out);
                                writeJsonLine(w, upd);
                            } catch (Exception ignored) {
                            }
                        }
                    } else {
                        log("切换物理出口失败: " + res.output);
                    }
                });
            }
        }
    }

    private String currentUpstreamLabel() {
        synchronized (netLock) {
            return currentBestUpstream;
        }
    }

    private boolean isCurrentUpstreamWifi() {
        synchronized (netLock) {
            return currentBestIsWifi;
        }
    }

    private static int parseStaFreq(String output) {
        if (output == null || output.isEmpty()) {
            return 0;
        }
        Matcher m = STA_FREQ_PAT.matcher(output);
        if (m.find()) {
            try {
                return Integer.parseInt(m.group(1));
            } catch (NumberFormatException ignored) {
            }
        }
        return 0;
    }

    @SuppressLint("MissingPermission")
    private void runRfcommSession(BluetoothDevice dev) {
        BluetoothSocket sock = null;
        PowerManager.WakeLock wl = null;
        boolean everConnected = false;
        boolean cleanStop = false;
        Runnable waitFallbackTimeout = null;
        try {
            if (powerManager != null) {
                wl = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "opd:netshare");
                wl.setReferenceCounted(false);
                wl.acquire(35_000L);
            }
            if (btAdapter != null && hasBtPermissions() && btAdapter.isDiscovering()) {
                btAdapter.cancelDiscovery();
            }
            sock = dev.createRfcommSocketToServiceRecord(NetSharePrefs.RFCOMM_UUID);
            sock.connect();
            activeSocket = sock;
            connecting = false;
            stopBleScan();
            log("RFCOMM 控制通道已连接");

            final BluetoothSocket activeSockRef = sock;
            waitFallbackTimeout = () -> {
                if (activeSocket == activeSockRef && !p2pActive) {
                    log("等待平板切换备用信道超时，关闭当前会话");
                    try {
                        activeSockRef.close();
                    } catch (IOException ignored) {
                    }
                }
            };

            BufferedReader br = new BufferedReader(
                    new InputStreamReader(sock.getInputStream(), StandardCharsets.UTF_8));
            OutputStreamWriter writer = new OutputStreamWriter(sock.getOutputStream(), StandardCharsets.UTF_8);
            activeWriter = writer;

            refreshAllPhysicalNets();
            int preStaFreq = 0;
            if (isCurrentUpstreamWifi()) {
                try {
                    Future<ExecResult> freqFut = helperExecutor.submit(() -> runHelper("sta-freq"));
                    ExecResult fr = freqFut.get(3, TimeUnit.SECONDS);
                    if (fr.code == 0 && !fr.output.isEmpty()) {
                        preStaFreq = Integer.parseInt(fr.output.trim());
                    }
                } catch (Exception ignored) {
                }
            }
            JSONObject hello = new JSONObject();
            hello.put("event", "hello");
            hello.put("sta_freq", preStaFreq);
            writeJsonLine(writer, hello);

            int failCount = 0;
            String line;
            while ((line = br.readLine()) != null) {
                mainHandler.removeCallbacks(waitFallbackTimeout);
                String trimmed = line.trim();
                if (trimmed.isEmpty()) {
                    continue;
                }
                JSONObject obj;
                try {
                    obj = new JSONObject(trimmed);
                } catch (Exception e) {
                    continue;
                }
                String cmd = obj.optString("cmd", "");
                if ("start".equals(cmd)) {
                    String ssid = obj.optString("ssid", "");
                    String psk = obj.optString("psk", "");
                    int freq = obj.optInt("freq", 2462);
                    String tabletLlRaw = obj.optString("v6_ll", "");
                    String tabletLl = SAFE_V6.matcher(tabletLlRaw).matches() ? tabletLlRaw : "none";
                    if (!SAFE_TOKEN.matcher(ssid).matches()
                            || !SAFE_PSK.matcher(psk).matches()
                            || freq < 2412 || freq > 5885) {
                        log("收到非法 AP 凭据，拒绝拉起");
                        break;
                    }
                    if (wl != null) {
                        wl.acquire(35_000L);
                    }
                    refreshAllPhysicalNets();
                    String upstream;
                    String v6If;
                    String tabletV6;
                    synchronized (netLock) {
                        upstream = currentBestUpstream;
                        v6If = currentBestV6If;
                        tabletV6 = currentBestTabletV6;
                    }
                    activeTabletLl = tabletLl;
                    log("正在拉起 P2P 连接 (" + ssid + ", freq=" + freq + ", upstream=" + upstream
                            + (tabletV6.isEmpty() ? "" : ", v6=" + tabletV6) + ")");

                    final String v6IpArg = tabletV6.isEmpty() ? "none" : tabletV6;
                    Future<ExecResult> fut = helperExecutor.submit(
                            () -> runHelper("up", ssid, psk, String.valueOf(freq), upstream, v6If, v6IpArg, tabletLl));
                    ExecResult res = fut.get(32, TimeUnit.SECONDS);

                    if (wl != null && wl.isHeld()) {
                        wl.release();
                    }

                    if (res.code != 0 || !res.output.startsWith("OK ")) {
                        if (res.code == 124) {
                            try {
                                helperExecutor.submit(() -> runHelper("cancel")).get(5, TimeUnit.SECONDS);
                            } catch (Exception ignored) {
                            }
                        }
                        failCount++;
                        int staFreq = parseStaFreq(res.output);
                        log("P2P 拉起失败 (#" + failCount + ", freq=" + freq + ", staFreq=" + staFreq + "): " + res.output);
                        if (failCount < 5) {
                            updateStatus(
                                    NetSharePrefs.STATE_CONNECTING,
                                    "信道 " + freq + " MHz 组网失败，请求平板切换备用信道...",
                                    "",
                                    ""
                            );
                            JSONObject failEvt = new JSONObject();
                            failEvt.put("event", "p2p_failed");
                            failEvt.put("freq", freq);
                            failEvt.put("sta_freq", staFreq);
                            writeJsonLine(writer, failEvt);
                            mainHandler.postDelayed(waitFallbackTimeout, 14_000L);
                            continue;
                        }
                        updateStatus(NetSharePrefs.STATE_ERROR, "P2P 拉起失败: " + res.output, "", "");
                        try {
                            writeJsonLine(writer, new JSONObject("{\"event\":\"stop_request\"}"));
                        } catch (Exception ignored) {
                        }
                        break;
                    }

                    String[] parts = res.output.split("\\s+");
                    String ip = parts.length >= 2 ? parts[1] : "";
                    String outIf = parts.length >= 3 ? parts[2] : upstream;
                    String v6Ll = (parts.length >= 4 && !"none".equals(parts[3])) ? parts[3] : "";
                    String v6Out = (parts.length >= 5 && !"none".equals(parts[4])) ? parts[4] : "none";
                    String v6Ip = (!"none".equals(v6Out) && !v6Ll.isEmpty() && !tabletV6.isEmpty()) ? tabletV6 : "";

                    activeP2pIp = ip;
                    activeOutIf = outIf;
                    activeV6Ll = v6Ll;
                    activeV6OutIf = v6Out;
                    activeV6Ip = v6Ip;
                    p2pActive = true;
                    everConnected = true;

                    updateStatus(
                            NetSharePrefs.STATE_CONNECTED,
                            "已连接共享 (" + ip + " -> " + outIf + (v6Ip.isEmpty() ? "" : ", IPv6") + ")",
                            ip,
                            outIf
                    );
                    log("P2P 共享已就绪: IP=" + ip + ", 物理出口=" + outIf
                            + (v6Ip.isEmpty() ? "" : ", IPv6=" + v6Ip));

                    JSONObject reply = new JSONObject();
                    reply.put("ip", ip);
                    reply.put("upstream", outIf);
                    reply.put("v6_ll", v6Ll);
                    reply.put("v6_ip", v6Ip);
                    reply.put("v6_out", v6Out);
                    writeJsonLine(writer, reply);
                } else if ("ping".equals(cmd)) {
                    // Keepalive received from daemon
                } else if ("stop".equals(cmd)) {
                    cleanStop = true;
                    log("收到平板停止指令，正在释放 P2P 共享");
                    break;
                }
            }
        } catch (Exception e) {
            log("RFCOMM 会话结束: " + (e.getMessage() == null ? "已断开" : e.getMessage()));
        } finally {
            if (waitFallbackTimeout != null) {
                mainHandler.removeCallbacks(waitFallbackTimeout);
            }
            if (wl != null && wl.isHeld()) {
                try {
                    wl.release();
                } catch (Exception ignored) {
                }
            }
            if (cleanStop) {
                lastAttemptMs = 0L;
            } else if (!everConnected) {
                // Allow prompt retry on handshake failure without 4s lockout (2s anti-spin floor)
                lastAttemptMs = SystemClock.elapsedRealtime() - 2_000L;
            }
            connecting = false;
            p2pActive = false;
            activeP2pIp = "";
            activeOutIf = "";
            activeV6Ll = "";
            activeV6OutIf = "none";
            activeV6Ip = "";
            activeTabletLl = "none";
            activeWriter = null;
            activeSocket = null;
            if (sock != null) {
                try {
                    sock.close();
                } catch (IOException ignored) {
                }
            }
            try {
                Future<ExecResult> downFut = helperExecutor.submit(() -> runHelper("down"));
                ExecResult d = downFut.get(15, TimeUnit.SECONDS);
                if (d.code == 0) {
                    log("已清理 P2P 与防火墙规则");
                } else {
                    log("清理返回异常: " + d.output);
                }
            } catch (Exception e) {
                log("清理异常: " + e.getMessage());
            }

            if (NetSharePrefs.isEnabled(this)) {
                mainHandler.post(() -> {
                    if (NetSharePrefs.isEnabled(NetShareService.this) && !isSessionBusy()) {
                        startBleScan();
                    }
                });
            }
        }
    }

    private void closeActiveSocket() {
        BluetoothSocket sock = activeSocket;
        if (sock != null) {
            try {
                sock.close();
            } catch (IOException ignored) {
            }
        }
    }

    private void disconnectCurrentSessionOnly() {
        netExecutor.execute(() -> {
            BluetoothSocket sock = activeSocket;
            if (sock != null) {
                try {
                    OutputStreamWriter w = new OutputStreamWriter(sock.getOutputStream(), StandardCharsets.UTF_8);
                    w.write("{\"event\":\"stop_request\"}\n");
                    w.flush();
                } catch (IOException ignored) {
                }
                closeActiveSocket();
            }
        });
    }

    private void stopEverythingAndExit() {
        stopBleScan();
        disconnectCurrentSessionOnly();
        mainHandler.postDelayed(this::stopSelf, 300L);
    }
}
