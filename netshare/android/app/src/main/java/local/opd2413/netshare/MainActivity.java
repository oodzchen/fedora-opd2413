package local.opd2413.netshare;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.TypedValue;
import android.view.ViewGroup;
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
import java.util.Set;
import java.util.concurrent.TimeUnit;

public class MainActivity extends Activity {
    private static final int REQ_PERMS = 101;

    private TextView statusView;
    private TextView targetView;
    private TextView envView;
    private TextView logView;
    private Switch enableSwitch;
    private boolean updatingSwitch = false;
    private String rootCheckText = "未检测";

    private final BroadcastReceiver stateReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            refreshUi();
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildLayout();
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
        if (NetSharePrefs.isEnabled(this)
                && !NetSharePrefs.getTargetMac(this).isEmpty()
                && hasRequiredPermissions()
                && NetSharePrefs.STATE_DISABLED.equals(NetSharePrefs.getState())) {
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

    private int dp(int v) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics()));
    }

    private void buildLayout() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(16);
        root.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("OPD 跨设备网络共享 (手机端)");
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        title.setTypeface(null, Typeface.BOLD);
        root.addView(title);

        statusView = new TextView(this);
        statusView.setPadding(0, dp(10), 0, dp(6));
        statusView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        root.addView(statusView);

        targetView = new TextView(this);
        targetView.setPadding(0, dp(2), 0, dp(6));
        root.addView(targetView);

        envView = new TextView(this);
        envView.setPadding(0, dp(2), 0, dp(10));
        root.addView(envView);

        enableSwitch = new Switch(this);
        enableSwitch.setText("自动跨设备网络共享监听");
        enableSwitch.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        enableSwitch.setPadding(0, dp(8), 0, dp(8));
        enableSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            if (updatingSwitch) {
                return;
            }
            onToggleChanged(isChecked);
        });
        root.addView(enableSwitch);

        Button pickBtn = new Button(this);
        pickBtn.setText("选择已配对平板");
        pickBtn.setOnClickListener(v -> showBondedDevicePicker());
        root.addView(pickBtn);

        Button rootBtn = new Button(this);
        rootBtn.setText("检测 Root (KernelSU) 权限");
        rootBtn.setOnClickListener(v -> checkRootAsync(true));
        root.addView(rootBtn);

        Button batBtn = new Button(this);
        batBtn.setText("打开电池优化白名单设置");
        batBtn.setOnClickListener(v -> openBatterySettings());
        root.addView(batBtn);

        Button discBtn = new Button(this);
        discBtn.setText("断开当前 P2P 会话");
        discBtn.setOnClickListener(v -> {
            if (!NetSharePrefs.STATE_DISABLED.equals(NetSharePrefs.getState())) {
                Intent svc = new Intent(this, NetShareService.class);
                svc.setAction(NetSharePrefs.ACTION_DISCONNECT_SESSION);
                startService(svc);
            }
        });
        root.addView(discBtn);

        TextView logHeader = new TextView(this);
        logHeader.setText("运行日志:");
        logHeader.setTypeface(null, Typeface.BOLD);
        logHeader.setPadding(0, dp(12), 0, dp(4));
        root.addView(logHeader);

        logView = new TextView(this);
        logView.setTypeface(Typeface.MONOSPACE);
        logView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        logView.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));
        root.addView(logView);

        scroll.addView(root);
        setContentView(scroll);
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
                    .setMessage("请先在系统蓝牙设置中与平板配对，然后再回来选择。")
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
                boolean ok = p.waitFor(8, TimeUnit.SECONDS) && p.exitValue() == 0 && out.toString().contains("uid=0");
                resText = ok ? "已授权 (" + out + ")" : "未授权 (" + out + ")";
            } catch (Exception e) {
                resText = "失败: " + e.getMessage();
            }
            String finalText = resText;
            runOnUiThread(() -> {
                rootCheckText = finalText;
                refreshUi();
                if (showToast) {
                    Toast.makeText(this, "Root: " + finalText, Toast.LENGTH_LONG).show();
                }
            });
        }).start();
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

    private void refreshUi() {
        boolean enabled = NetSharePrefs.isEnabled(this);
        updatingSwitch = true;
        enableSwitch.setChecked(enabled);
        updatingSwitch = false;

        String st = NetSharePrefs.getState();
        String detail = NetSharePrefs.getDetail();
        String p2p = NetSharePrefs.getP2pIp();
        String up = NetSharePrefs.getUpstream();
        statusView.setText("状态: " + st + " - " + detail
                + (p2p.isEmpty() ? "" : ("\nP2P IP: " + p2p))
                + (up.isEmpty() ? "" : (" | 物理出口: " + up)));

        String mac = NetSharePrefs.getTargetMac(this);
        String name = NetSharePrefs.getTargetName(this);
        targetView.setText("目标平板: " + (mac.isEmpty() ? "未选择" : (name + " (" + mac + ")")));

        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        boolean batExempt = pm != null && pm.isIgnoringBatteryOptimizations(getPackageName());
        envView.setText("权限: " + (hasRequiredPermissions() ? "已授予" : "未授予")
                + " | Root: " + rootCheckText
                + " | 电池白名单: " + (batExempt ? "已放行" : "未放行"));

        logView.setText(NetSharePrefs.getLogsText());
    }
}
