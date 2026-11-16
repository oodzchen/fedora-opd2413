package local.opd2413.netshare;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.ScanFilter;
import android.companion.AssociationInfo;
import android.companion.AssociationRequest;
import android.companion.BluetoothDeviceFilter;
import android.companion.BluetoothLeDeviceFilter;
import android.companion.CompanionDeviceManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.IntentSender;
import android.content.pm.PackageManager;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.ParcelUuid;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.TypedValue;
import android.view.MotionEvent;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.TimeUnit;

public class MainActivity extends Activity {
    private static final int REQ_PERMS = 101;
    private static final int REQ_COMPANION = 102;

    private static final int ROOT_UNKNOWN = 0;
    private static final int ROOT_OK = 1;
    private static final int ROOT_DENIED = 2;

    private LinearLayout statusCard;
    private View statusDot;
    private TextView statusTitleView;
    private TextView statusBadgeView;
    private TextView statusDetailView;
    private LinearLayout statusMetaRow;
    private TextView p2pChip;
    private TextView upstreamChip;

    private TextView targetNameView;
    private TextView targetMacView;
    private Button pickBtn;
    private Button discBtn;

    private TextView envPermBadge;
    private TextView envRootBadge;
    private TextView envBatteryBadge;
    private TextView envCdmBadge;
    private Button rootBtn;
    private Button batBtn;
    private Button cdmBtn;

    private TextView logCountView;
    private Button clearLogBtn;
    private ScrollView logScroll;
    private TextView logView;
    private TextView logEmptyView;

    private Switch enableSwitch;
    private boolean updatingSwitch = false;
    private int rootState = ROOT_UNKNOWN;
    private String lastRenderedLogs = "";

    private final BroadcastReceiver stateReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            refreshUi();
        }
    };

    private static final class StatusVisual {
        final String title;
        final String badge;
        final int bgColor;
        final int borderColor;
        final int accentColor;
        final int pillBgColor;

        StatusVisual(String title, String badge, int bgColor, int borderColor, int accentColor, int pillBgColor) {
            this.title = title;
            this.badge = badge;
            this.bgColor = bgColor;
            this.borderColor = borderColor;
            this.accentColor = accentColor;
            this.pillBgColor = pillBgColor;
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        bindViews();
        requestMissingPermissions();
        checkRootAsync(false);
    }

    @Override
    protected void onStart() {
        super.onStart();
        registerReceiver(
                stateReceiver,
                new IntentFilter(NetSharePrefs.ACTION_STATE_CHANGED),
                Context.RECEIVER_NOT_EXPORTED
        );
        ensureServiceRunningIfEnabled();
        refreshUi();
    }

    private void ensureServiceRunningIfEnabled() {
        String mac = NetSharePrefs.getTargetMac(this);
        String st = NetSharePrefs.getState();
        if (NetSharePrefs.isEnabled(this)
                && !mac.isEmpty()
                && hasRequiredPermissions()
                && (NetSharePrefs.STATE_DISABLED.equals(st) || NetSharePrefs.STATE_SCANNING.equals(st))) {
            if (isCompanionAssociated(mac)) {
                startCompanionPresence(mac);
            }
            Intent svc = new Intent(this, NetShareService.class);
            svc.setAction(NetSharePrefs.ACTION_START_LISTEN);
            try {
                startForegroundService(svc);
            } catch (Exception ignored) {
            }
        }
    }

    @Override
    protected void onStop() {
        super.onStop();
        try {
            unregisterReceiver(stateReceiver);
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        refreshUi();
    }

    private float dp(float v) {
        return TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    @SuppressLint("ClickableViewAccessibility")
    private void bindViews() {
        statusCard = findViewById(R.id.status_card);
        statusDot = findViewById(R.id.status_dot);
        statusTitleView = findViewById(R.id.status_title);
        statusBadgeView = findViewById(R.id.status_badge);
        statusDetailView = findViewById(R.id.status_detail);
        statusMetaRow = findViewById(R.id.status_meta_row);
        p2pChip = findViewById(R.id.p2p_chip);
        upstreamChip = findViewById(R.id.upstream_chip);

        targetNameView = findViewById(R.id.target_name);
        targetMacView = findViewById(R.id.target_mac);
        pickBtn = findViewById(R.id.btn_pick_device);
        discBtn = findViewById(R.id.btn_disconnect);

        envPermBadge = findViewById(R.id.env_perm_badge);
        envRootBadge = findViewById(R.id.env_root_badge);
        envBatteryBadge = findViewById(R.id.env_battery_badge);
        envCdmBadge = findViewById(R.id.env_cdm_badge);
        rootBtn = findViewById(R.id.btn_check_root);
        batBtn = findViewById(R.id.btn_battery);
        cdmBtn = findViewById(R.id.btn_companion);

        logCountView = findViewById(R.id.log_count);
        clearLogBtn = findViewById(R.id.btn_clear_log);
        logScroll = findViewById(R.id.log_scroll);
        logView = findViewById(R.id.log_text);
        logEmptyView = findViewById(R.id.log_empty);

        enableSwitch = findViewById(R.id.enable_switch);
        enableSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            if (updatingSwitch) {
                return;
            }
            onToggleChanged(isChecked);
        });

        pickBtn.setOnClickListener(v -> showBondedDevicePicker());
        discBtn.setOnClickListener(v -> {
            if (!NetSharePrefs.STATE_DISABLED.equals(NetSharePrefs.getState())) {
                Intent svc = new Intent(this, NetShareService.class);
                svc.setAction(NetSharePrefs.ACTION_DISCONNECT_SESSION);
                startService(svc);
            }
        });

        rootBtn.setOnClickListener(v -> checkRootAsync(true));
        batBtn.setOnClickListener(v -> openBatterySettings());
        cdmBtn.setOnClickListener(v -> requestCompanionAssociation());

        envPermBadge.setOnClickListener(v -> {
            if (!hasRequiredPermissions()) {
                requestMissingPermissions();
            }
        });
        envBatteryBadge.setOnClickListener(v -> openBatterySettings());
        envCdmBadge.setOnClickListener(v -> requestCompanionAssociation());

        clearLogBtn.setOnClickListener(v -> {
            NetSharePrefs.clearLogs();
            lastRenderedLogs = "";
            refreshUi();
        });

        // Allow independent vertical scrolling inside the embedded log box.
        logScroll.setOnTouchListener((v, event) -> {
            int action = event.getActionMasked();
            if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_MOVE) {
                v.getParent().requestDisallowInterceptTouchEvent(true);
            } else if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
                v.getParent().requestDisallowInterceptTouchEvent(false);
            }
            return false;
        });
    }

    private void onToggleChanged(boolean wantOn) {
        if (wantOn) {
            if (!hasRequiredPermissions()) {
                requestMissingPermissions();
                updatingSwitch = true;
                enableSwitch.setChecked(false);
                updatingSwitch = false;
                Toast.makeText(this, "请先授予蓝牙和通知权限", Toast.LENGTH_SHORT).show();
                return;
            }
            if (NetSharePrefs.getTargetMac(this).isEmpty()) {
                updatingSwitch = true;
                enableSwitch.setChecked(false);
                updatingSwitch = false;
                Toast.makeText(this, "请先选择已配对平板", Toast.LENGTH_SHORT).show();
                showBondedDevicePicker();
                return;
            }
            NetSharePrefs.setEnabled(this, true);
            Intent svc = new Intent(this, NetShareService.class);
            svc.setAction(NetSharePrefs.ACTION_START_LISTEN);
            startForegroundService(svc);
        } else {
            NetSharePrefs.setEnabled(this, false);
            if (!NetSharePrefs.STATE_DISABLED.equals(NetSharePrefs.getState())) {
                Intent svc = new Intent(this, NetShareService.class);
                svc.setAction(NetSharePrefs.ACTION_STOP_ALL);
                startService(svc);
            }
        }
        refreshUi();
    }

    private boolean hasRequiredPermissions() {
        return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private void requestMissingPermissions() {
        List<String> req = new ArrayList<>();
        if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
            req.add(Manifest.permission.BLUETOOTH_SCAN);
        }
        if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            req.add(Manifest.permission.BLUETOOTH_CONNECT);
        }
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            req.add(Manifest.permission.POST_NOTIFICATIONS);
        }
        if (!req.isEmpty()) {
            requestPermissions(req.toArray(new String[0]), REQ_PERMS);
        }
    }

    @SuppressLint("MissingPermission")
    private void showBondedDevicePicker() {
        if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            requestMissingPermissions();
            return;
        }
        BluetoothManager mgr = (BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter adapter = mgr != null ? mgr.getAdapter() : null;
        if (adapter == null) {
            Toast.makeText(this, "蓝牙不可用", Toast.LENGTH_SHORT).show();
            return;
        }
        Set<BluetoothDevice> bonded = adapter.getBondedDevices();
        if (bonded == null || bonded.isEmpty()) {
            new AlertDialog.Builder(this)
                    .setTitle("无已配对设备")
                    .setMessage("请先在系统蓝牙设置中与平板配对，再回来选择。")
                    .setPositiveButton("确定", null)
                    .show();
            return;
        }
        List<BluetoothDevice> devs = new ArrayList<>(bonded);
        String[] labels = new String[devs.size()];
        for (int i = 0; i < devs.size(); i++) {
            BluetoothDevice d = devs.get(i);
            String name = d.getName() == null ? "未知设备" : d.getName();
            labels[i] = name + "\n" + d.getAddress();
        }
        new AlertDialog.Builder(this)
                .setTitle("选择目标平板")
                .setItems(labels, (dialog, which) -> {
                    BluetoothDevice chosen = devs.get(which);
                    String name = chosen.getName() == null ? chosen.getAddress() : chosen.getName();
                    NetSharePrefs.setTargetDevice(this, chosen.getAddress(), name);
                    if (NetSharePrefs.isEnabled(this)) {
                        Intent svc = new Intent(this, NetShareService.class);
                        svc.setAction(NetSharePrefs.ACTION_START_LISTEN);
                        startForegroundService(svc);
                    }
                    refreshUi();
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void checkRootAsync(boolean showToast) {
        new Thread(() -> {
            boolean ok = false;
            String resText;
            try {
                Process p = new ProcessBuilder("su", "-c", "id").redirectErrorStream(true).start();
                StringBuilder out = new StringBuilder();
                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
                    String l;
                    while ((l = br.readLine()) != null) {
                        out.append(l);
                    }
                }
                ok = p.waitFor(8, TimeUnit.SECONDS) && p.exitValue() == 0 && out.toString().contains("uid=0");
                resText = ok ? "已授权 (" + out + ")" : "未授权 (" + out + ")";
            } catch (Exception e) {
                resText = "失败: " + e.getMessage();
            }
            final int nextState = ok ? ROOT_OK : ROOT_DENIED;
            final String finalText = resText;
            runOnUiThread(() -> {
                rootState = nextState;
                refreshUi();
                if (showToast) {
                    Toast.makeText(this, "Root: " + finalText, Toast.LENGTH_LONG).show();
                }
            });
        }).start();
    }

    private boolean isCompanionAssociated(String targetMac) {
        if (targetMac == null || targetMac.isEmpty()) {
            return false;
        }
        CompanionDeviceManager cdm = getSystemService(CompanionDeviceManager.class);
        if (cdm == null) {
            return false;
        }
        try {
            List<AssociationInfo> list = cdm.getMyAssociations();
            if (list == null) {
                return false;
            }
            for (AssociationInfo info : list) {
                if (info != null && info.getDeviceMacAddress() != null) {
                    String mac = info.getDeviceMacAddress().toString().trim().toUpperCase(Locale.ROOT);
                    if (targetMac.equals(mac)) {
                        return true;
                    }
                }
            }
        } catch (Exception ignored) {
        }
        return false;
    }

    @SuppressLint("MissingPermission")
    private void startCompanionPresence(String mac) {
        if (mac == null || mac.isEmpty() || !hasRequiredPermissions()) {
            return;
        }
        CompanionDeviceManager cdm = getSystemService(CompanionDeviceManager.class);
        if (cdm == null) {
            return;
        }
        try {
            cdm.startObservingDevicePresence(mac);
            NetSharePrefs.appendLog("CDM 已开启设备出现后台监听: " + mac);
        } catch (Exception e) {
            NetSharePrefs.appendLog("CDM 开启监听失败: " + e.getMessage());
        }
    }

    @SuppressLint("MissingPermission")
    private void requestCompanionAssociation() {
        if (!hasRequiredPermissions()) {
            requestMissingPermissions();
            Toast.makeText(this, "请先授予蓝牙权限", Toast.LENGTH_SHORT).show();
            return;
        }
        String targetMac = NetSharePrefs.getTargetMac(this);
        if (targetMac.isEmpty()) {
            Toast.makeText(this, "请先选择目标平板", Toast.LENGTH_SHORT).show();
            showBondedDevicePicker();
            return;
        }
        CompanionDeviceManager cdm = getSystemService(CompanionDeviceManager.class);
        if (cdm == null) {
            Toast.makeText(this, "系统不支持 CompanionDeviceManager", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isCompanionAssociated(targetMac)) {
            startCompanionPresence(targetMac);
            refreshUi();
            Toast.makeText(this, "已关联系统伴侣设备，后台监听已刷新", Toast.LENGTH_SHORT).show();
            return;
        }
        BluetoothDeviceFilter btFilter = new BluetoothDeviceFilter.Builder()
                .setAddress(targetMac)
                .build();
        BluetoothLeDeviceFilter bleFilter = new BluetoothLeDeviceFilter.Builder()
                .setScanFilter(new ScanFilter.Builder()
                        .setServiceUuid(new ParcelUuid(NetSharePrefs.ADV_UUID))
                        .build())
                .build();
        AssociationRequest req = new AssociationRequest.Builder()
                .addDeviceFilter(btFilter)
                .addDeviceFilter(bleFilter)
                .setSingleDevice(true)
                .build();
        Toast.makeText(this, "正在请求系统伴侣设备关联...", Toast.LENGTH_SHORT).show();
        cdm.associate(req, getMainExecutor(), new CompanionDeviceManager.Callback() {
            @Override
            public void onAssociationPending(IntentSender intentSender) {
                try {
                    startIntentSenderForResult(intentSender, REQ_COMPANION, null, 0, 0, 0);
                } catch (IntentSender.SendIntentException e) {
                    Toast.makeText(MainActivity.this, "弹出关联确认失败: " + e.getMessage(), Toast.LENGTH_LONG).show();
                }
            }

            @Override
            public void onAssociationCreated(AssociationInfo associationInfo) {
                String mac = (associationInfo != null && associationInfo.getDeviceMacAddress() != null)
                        ? associationInfo.getDeviceMacAddress().toString().trim().toUpperCase(Locale.ROOT)
                        : targetMac;
                startCompanionPresence(mac);
                if (NetSharePrefs.isEnabled(MainActivity.this)) {
                    Intent svc = new Intent(MainActivity.this, NetShareService.class);
                    svc.setAction(NetSharePrefs.ACTION_START_LISTEN);
                    startForegroundService(svc);
                }
                refreshUi();
                Toast.makeText(MainActivity.this, "系统伴侣关联成功", Toast.LENGTH_SHORT).show();
            }

            @Override
            public void onFailure(CharSequence error) {
                String msg = error == null ? "未发现平板广播" : error.toString();
                NetSharePrefs.appendLog("CDM 关联失败: " + msg);
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle("伴侣关联未找到设备")
                        .setMessage("系统在扫描周期内未收到平板广播 (" + msg + ")。\n\n请先在平板上开启「立即互联」（或断开平板 Wi-Fi 使其处于待连广播状态），再点击「伴侣关联」。")
                        .setPositiveButton("知道了", null)
                        .show();
                refreshUi();
            }
        });
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_COMPANION && resultCode == RESULT_OK) {
            String targetMac = NetSharePrefs.getTargetMac(this);
            AssociationInfo info = data != null
                    ? data.getParcelableExtra(CompanionDeviceManager.EXTRA_ASSOCIATION, AssociationInfo.class)
                    : null;
            String mac = (info != null && info.getDeviceMacAddress() != null)
                    ? info.getDeviceMacAddress().toString().trim().toUpperCase(Locale.ROOT)
                    : targetMac;
            startCompanionPresence(mac);
            if (NetSharePrefs.isEnabled(this)) {
                Intent svc = new Intent(this, NetShareService.class);
                svc.setAction(NetSharePrefs.ACTION_START_LISTEN);
                startForegroundService(svc);
            }
            refreshUi();
        }
    }

    private void openBatterySettings() {
        try {
            Intent i = new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS);
            startActivity(i);
        } catch (Exception e) {
            Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.fromParts("package", getPackageName(), null));
            startActivity(i);
        }
    }

    private StatusVisual resolveStatusVisual(String state) {
        if (NetSharePrefs.STATE_CONNECTED.equals(state)) {
            return new StatusVisual(
                    "已连接",
                    "CONNECTED",
                    getColor(R.color.state_connected_bg),
                    getColor(R.color.state_connected_border),
                    getColor(R.color.state_connected_accent),
                    getColor(R.color.state_connected_pill_bg)
            );
        }
        if (NetSharePrefs.STATE_CONNECTING.equals(state)) {
            return new StatusVisual(
                    "连接中",
                    "CONNECTING",
                    getColor(R.color.state_connecting_bg),
                    getColor(R.color.state_connecting_border),
                    getColor(R.color.state_connecting_accent),
                    getColor(R.color.state_connecting_pill_bg)
            );
        }
        if (NetSharePrefs.STATE_SCANNING.equals(state)) {
            return new StatusVisual(
                    "待命中",
                    "SCANNING",
                    getColor(R.color.state_scanning_bg),
                    getColor(R.color.state_scanning_border),
                    getColor(R.color.state_scanning_accent),
                    getColor(R.color.state_scanning_pill_bg)
            );
        }
        if (NetSharePrefs.STATE_ERROR.equals(state)) {
            return new StatusVisual(
                    "连接异常",
                    "ERROR",
                    getColor(R.color.state_error_bg),
                    getColor(R.color.state_error_border),
                    getColor(R.color.state_error_accent),
                    getColor(R.color.state_error_pill_bg)
            );
        }
        return new StatusVisual(
                "未开启",
                "IDLE",
                getColor(R.color.state_disabled_bg),
                getColor(R.color.state_disabled_border),
                getColor(R.color.state_disabled_accent),
                getColor(R.color.state_disabled_pill_bg)
        );
    }

    private void applyCardBackground(View view, int fillColor, int strokeColor) {
        GradientDrawable gd = new GradientDrawable();
        gd.setShape(GradientDrawable.RECTANGLE);
        gd.setCornerRadius(dp(14));
        gd.setColor(fillColor);
        gd.setStroke(Math.max(1, Math.round(dp(1.5f))), strokeColor);
        view.setBackground(gd);
    }

    private void applyDotColor(View view, int color) {
        GradientDrawable gd = new GradientDrawable();
        gd.setShape(GradientDrawable.OVAL);
        gd.setColor(color);
        view.setBackground(gd);
    }

    private void stylePill(TextView view, int bgColor, int textColor) {
        GradientDrawable gd = new GradientDrawable();
        gd.setShape(GradientDrawable.RECTANGLE);
        gd.setCornerRadius(dp(999));
        gd.setColor(bgColor);
        view.setBackground(gd);
        view.setTextColor(textColor);
    }

    private void styleEnvBadge(TextView view, boolean ok, boolean known, String text) {
        view.setText(text);
        if (!known) {
            stylePill(view, getColor(R.color.badge_neutral_bg), getColor(R.color.badge_neutral_text));
        } else if (ok) {
            stylePill(view, getColor(R.color.badge_ok_bg), getColor(R.color.badge_ok_text));
        } else {
            stylePill(view, getColor(R.color.badge_warn_bg), getColor(R.color.badge_warn_text));
        }
    }

    private void refreshUi() {
        boolean enabled = NetSharePrefs.isEnabled(this);
        updatingSwitch = true;
        enableSwitch.setChecked(enabled);
        updatingSwitch = false;

        String st = NetSharePrefs.getState();
        String detail = NetSharePrefs.getDetail();
        String p2p = NetSharePrefs.getP2pIp();
        String up = NetSharePrefs.getUpstream();

        StatusVisual vis = resolveStatusVisual(st);
        applyCardBackground(statusCard, vis.bgColor, vis.borderColor);
        applyDotColor(statusDot, vis.accentColor);
        statusTitleView.setText(vis.title);
        statusTitleView.setTextColor(vis.accentColor);
        statusBadgeView.setText(vis.badge);
        stylePill(statusBadgeView, vis.pillBgColor, vis.accentColor);
        statusDetailView.setText(detail.isEmpty() ? vis.title : detail);

        boolean hasP2p = !p2p.isEmpty();
        boolean hasUp = !up.isEmpty() && !"none".equals(up);
        if (hasP2p || hasUp) {
            statusMetaRow.setVisibility(View.VISIBLE);
            if (hasP2p) {
                p2pChip.setVisibility(View.VISIBLE);
                p2pChip.setText("P2P " + p2p);
                stylePill(p2pChip, vis.pillBgColor, vis.accentColor);
            } else {
                p2pChip.setVisibility(View.GONE);
            }
            if (hasUp) {
                upstreamChip.setVisibility(View.VISIBLE);
                upstreamChip.setText("出口 " + up);
                stylePill(upstreamChip, vis.pillBgColor, vis.accentColor);
            } else {
                upstreamChip.setVisibility(View.GONE);
            }
        } else {
            statusMetaRow.setVisibility(View.GONE);
        }

        boolean canDisconnect = !NetSharePrefs.STATE_DISABLED.equals(st);
        discBtn.setEnabled(canDisconnect);
        discBtn.setAlpha(canDisconnect ? 1.0f : 0.45f);

        String mac = NetSharePrefs.getTargetMac(this);
        String name = NetSharePrefs.getTargetName(this);
        if (mac.isEmpty()) {
            targetNameView.setText(R.string.label_target_none);
            targetMacView.setVisibility(View.GONE);
        } else {
            targetNameView.setText(name.isEmpty() ? mac : name);
            targetMacView.setText(mac);
            targetMacView.setVisibility(View.VISIBLE);
        }

        boolean permOk = hasRequiredPermissions();
        styleEnvBadge(envPermBadge, permOk, true, permOk ? "权限 已授权" : "权限 未授权");

        if (rootState == ROOT_UNKNOWN) {
            styleEnvBadge(envRootBadge, false, false, "Root 检测中");
        } else {
            styleEnvBadge(envRootBadge, rootState == ROOT_OK, true,
                    rootState == ROOT_OK ? "Root 正常" : "Root 未授权");
        }

        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        boolean batExempt = pm != null && pm.isIgnoringBatteryOptimizations(getPackageName());
        styleEnvBadge(envBatteryBadge, batExempt, true, batExempt ? "电池 已放行" : "电池 受限");

        boolean cdmOk = isCompanionAssociated(mac);
        styleEnvBadge(envCdmBadge, cdmOk, !mac.isEmpty(),
                mac.isEmpty() ? "伴侣 未选" : (cdmOk ? "伴侣 已关联" : "伴侣 未关联"));

        int count = NetSharePrefs.getLogCount();
        logCountView.setText(count > 0 ? "(" + count + ")" : "");
        clearLogBtn.setEnabled(count > 0);
        clearLogBtn.setAlpha(count > 0 ? 1.0f : 0.45f);

        String logs = NetSharePrefs.getLogsText();
        String displayLogs = logs.endsWith("\n") ? logs.substring(0, logs.length() - 1) : logs;
        if (displayLogs.isEmpty()) {
            logView.setText("");
            logEmptyView.setVisibility(View.VISIBLE);
            lastRenderedLogs = "";
        } else {
            logEmptyView.setVisibility(View.GONE);
            if (!displayLogs.equals(lastRenderedLogs)) {
                lastRenderedLogs = displayLogs;
                logView.setText(displayLogs);
                logScroll.post(() -> logScroll.fullScroll(View.FOCUS_DOWN));
            }
        }
    }
}
