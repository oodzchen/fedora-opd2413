package local.opd2413.netshare;

import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

public class NetShareTileService extends TileService {
    private final BroadcastReceiver stateReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            refreshTile();
        }
    };

    @Override
    public void onStartListening() {
        super.onStartListening();
        registerReceiver(
                stateReceiver,
                new IntentFilter(NetSharePrefs.ACTION_STATE_CHANGED),
                Context.RECEIVER_NOT_EXPORTED
        );
        refreshTile();
    }

    @Override
    public void onStopListening() {
        super.onStopListening();
        try {
            unregisterReceiver(stateReceiver);
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onClick() {
        super.onClick();
        if (NetSharePrefs.getTargetMac(this).isEmpty()) {
            Intent open = new Intent(this, MainActivity.class);
            open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            if (Build.VERSION.SDK_INT >= 34) {
                PendingIntent pi = PendingIntent.getActivity(
                        this,
                        0,
                        open,
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
                );
                startActivityAndCollapse(pi);
            } else {
                startActivityAndCollapse(open);
            }
            return;
        }
        boolean next = !NetSharePrefs.isEnabled(this);
        NetSharePrefs.setEnabled(this, next);
        Intent svc = new Intent(this, NetShareService.class);
        svc.setAction(next ? NetSharePrefs.ACTION_START_LISTEN : NetSharePrefs.ACTION_STOP_ALL);
        startForegroundService(svc);
        refreshTile();
    }

    private void refreshTile() {
        Tile tile = getQsTile();
        if (tile == null) {
            return;
        }
        boolean enabled = NetSharePrefs.isEnabled(this);
        String st = NetSharePrefs.getState();
        if (!enabled) {
            tile.setState(Tile.STATE_INACTIVE);
            tile.setSubtitle("已关闭");
        } else if (NetSharePrefs.STATE_CONNECTED.equals(st)) {
            tile.setState(Tile.STATE_ACTIVE);
            String up = NetSharePrefs.getUpstream();
            tile.setSubtitle(up.isEmpty() ? "已共享" : ("已共享: " + up));
        } else {
            tile.setState(Tile.STATE_ACTIVE);
            tile.setSubtitle("待命监听中");
        }
        tile.updateTile();
    }
}
