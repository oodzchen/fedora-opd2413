package local.opd2413.netshare;

import android.companion.AssociationInfo;
import android.companion.CompanionDeviceService;
import android.content.Intent;
import android.net.MacAddress;

import java.util.Locale;

/**
 * Receives system-managed CompanionDeviceManager presence callbacks (exempt from ColorOS background scan freeze).
 */
public class OpdCompanionService extends CompanionDeviceService {
    @Override
    public void onDeviceAppeared(AssociationInfo associationInfo) {
        super.onDeviceAppeared(associationInfo);
        if (!NetSharePrefs.isEnabled(this)) {
            return;
        }
        String targetMac = NetSharePrefs.getTargetMac(this);
        if (targetMac.isEmpty()) {
            return;
        }
        MacAddress macObj = associationInfo != null ? associationInfo.getDeviceMacAddress() : null;
        String appearedMac = macObj != null ? macObj.toString().trim().toUpperCase(Locale.ROOT) : "";
        if (!appearedMac.isEmpty() && !targetMac.equals(appearedMac)) {
            return;
        }
        NetSharePrefs.appendLog("CDM 系统伴侣服务唤醒: " + (appearedMac.isEmpty() ? targetMac : appearedMac));
        Intent svc = new Intent(this, NetShareService.class);
        svc.setAction(NetSharePrefs.ACTION_COMPANION_APPEARED);
        svc.putExtra(NetSharePrefs.EXTRA_COMPANION_MAC, appearedMac.isEmpty() ? targetMac : appearedMac);
        try {
            startForegroundService(svc);
        } catch (Exception e) {
            NetSharePrefs.appendLog("CDM 拉起前台服务失败: " + e.getMessage());
        }
    }

    @Override
    public void onDeviceDisappeared(AssociationInfo associationInfo) {
        super.onDeviceDisappeared(associationInfo);
        MacAddress macObj = associationInfo != null ? associationInfo.getDeviceMacAddress() : null;
        String mac = macObj != null ? macObj.toString().trim().toUpperCase(Locale.ROOT) : "";
        if (!mac.isEmpty()) {
            NetSharePrefs.appendLog("CDM 感知设备离开广播: " + mac);
        }
    }
}
