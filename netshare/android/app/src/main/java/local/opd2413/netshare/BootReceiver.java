package local.opd2413.netshare;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) {
            return;
        }
        String action = intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            return;
        }
        if (NetSharePrefs.isEnabled(context) && !NetSharePrefs.getTargetMac(context).isEmpty()) {
            Intent svc = new Intent(context, NetShareService.class);
            svc.setAction(NetSharePrefs.ACTION_START_LISTEN);
            try {
                context.startForegroundService(svc);
            } catch (Exception e) {
                NetSharePrefs.appendLog("Boot start failed: " + e.getMessage());
            }
        }
    }
}
