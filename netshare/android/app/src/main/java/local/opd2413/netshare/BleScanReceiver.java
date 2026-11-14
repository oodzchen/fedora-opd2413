package local.opd2413.netshare;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanResult;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

import java.util.ArrayList;
import java.util.Locale;

/**
 * Receives hardware-filtered BLE PendingIntent scan matches even if the app process was suspended or stopped.
 */
public class BleScanReceiver extends BroadcastReceiver {
    @Override
    @SuppressLint("MissingPermission")
    public void onReceive(Context context, Intent intent) {
        if (intent == null) {
            return;
        }
        int err = intent.getIntExtra(BluetoothLeScanner.EXTRA_ERROR_CODE, -1);
        if (err != -1) {
            NetSharePrefs.appendLog("PendingIntent BLE 错误: code=" + err);
            return;
        }
        if (!NetSharePrefs.isEnabled(context)) {
            return;
        }
        String targetMac = NetSharePrefs.getTargetMac(context);
        if (targetMac.isEmpty()) {
            return;
        }

        ArrayList<ScanResult> results = intent.getParcelableArrayListExtra(
                BluetoothLeScanner.EXTRA_LIST_SCAN_RESULT,
                ScanResult.class
        );
        if (results == null || results.isEmpty()) {
            return;
        }

        BluetoothDevice matched = null;
        for (ScanResult r : results) {
            if (r == null) {
                continue;
            }
            BluetoothDevice dev = r.getDevice();
            if (dev == null || dev.getAddress() == null) {
                continue;
            }
            String cleanMac = dev.getAddress().trim().toUpperCase(Locale.ROOT);
            if (!targetMac.equals(cleanMac)) {
                NetSharePrefs.appendLog("忽略非目标 UUID 设备: " + cleanMac + " (目标 " + targetMac + ")");
                continue;
            }
            matched = dev;
            break;
        }
        if (matched == null) {
            return;
        }

        NetSharePrefs.appendLog("BLE 硬件过滤命中平板: " + matched.getAddress());
        Intent svc = new Intent(context, NetShareService.class);
        svc.setAction(NetSharePrefs.ACTION_BLE_MATCH);
        svc.putExtra(BluetoothDevice.EXTRA_DEVICE, matched);
        try {
            context.startForegroundService(svc);
        } catch (Exception e) {
            NetSharePrefs.appendLog("BLE 唤醒前台服务失败: " + e.getMessage());
        }
    }
}
