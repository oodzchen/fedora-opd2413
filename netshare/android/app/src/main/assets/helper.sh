#!/system/bin/sh
# OPD2413 cross-device network share root helper (runs on rooted Android via su)
set -u

PATH="/system/bin:/system/xbin:/vendor/bin:${PATH:-}"
IPT="iptables -w 2"
STATE_IPFWD="/dev/.opdlink_ipfwd_orig"
STATE_P2P_IF="/dev/.opdlink_p2p_if"
STATE_OUT_IF="/dev/.opdlink_out_if"
STATE_TABLE="/dev/.opdlink_table_id"

log_err() {
    echo "ERR: $*" >&2
}

lookup_rt_table() {
    target="$1"
    [ -n "$target" ] || return 1
    [ -r /data/misc/net/rt_tables ] || return 1
    while read -r tid tname _rest; do
        case "$tid" in
            ""|\#*) continue ;;
        esac
        if [ "$tname" = "$target" ]; then
            echo "$tid"
            return 0
        fi
    done < /data/misc/net/rt_tables
    return 1
}

find_table_def_dev() {
    tid="$1"
    [ -n "$tid" ] || return 1
    ip -4 route show table "$tid" 2>/dev/null | while read -r line; do
        case "$line" in
            default\ *)
                prev=""
                for tok in $line; do
                    if [ "$prev" = "dev" ]; then
                        echo "$tok"
                        return 0
                    fi
                    prev="$tok"
                done
                ;;
        esac
    done
    return 1
}

resolve_upstream() {
    req="$1"
    [ -n "$req" ] && [ "$req" != "none" ] || return 1

    # Prefer 464XLAT stacked interface when present (IPv6-only cellular networks)
    case "$req" in
        v4-*) ;;
        *)
            v4cand="v4-${req}"
            tid="$(lookup_rt_table "$v4cand" || true)"
            if [ -n "$tid" ]; then
                defdev="$(find_table_def_dev "$tid" || true)"
                if [ -n "$defdev" ]; then
                    echo "$defdev $tid"
                    return 0
                fi
            fi
            ;;
    esac

    tid="$(lookup_rt_table "$req" || true)"
    if [ -z "$tid" ]; then
        case "$req" in
            v4-*)
                tid="$(lookup_rt_table "${req#v4-}" || true)"
                ;;
        esac
    fi
    if [ -n "$tid" ]; then
        defdev="$(find_table_def_dev "$tid" || true)"
        if [ -n "$defdev" ]; then
            echo "$defdev $tid"
            return 0
        fi
        # Some Android versions route default via main/per-netid without 'dev' repeated
        if ip -4 route show table "$tid" 2>/dev/null | grep -q '^default '; then
            echo "$req $tid"
            return 0
        fi
    fi
    return 1
}

find_p2p_ip() {
    ip -o -4 addr show 2>/dev/null | while read -r _idx ifc _fam cidr _rest; do
        case "$cidr" in
            192.168.49.*)
                echo "$ifc ${cidr%%/*}"
                return 0
                ;;
        esac
    done
}

clear_rules_and_chains() {
    while ip rule del pref 9996 >/dev/null 2>&1; do :; done
    while ip rule del pref 9997 >/dev/null 2>&1; do :; done

    $IPT -D tetherctrl_FORWARD -j opdlink_fwd >/dev/null 2>&1 || true
    $IPT -F opdlink_fwd >/dev/null 2>&1 || true
    $IPT -X opdlink_fwd >/dev/null 2>&1 || true

    $IPT -t nat -D tetherctrl_nat_POSTROUTING -j opdlink_nat >/dev/null 2>&1 || true
    $IPT -t nat -F opdlink_nat >/dev/null 2>&1 || true
    $IPT -t nat -X opdlink_nat >/dev/null 2>&1 || true
}

apply_nat() {
    p2p_if="$1"
    upstream_req="$2"

    resolved="$(resolve_upstream "$upstream_req" || true)"
    if [ -z "$resolved" ]; then
        # No physical upstream yet: keep P2P link alive without stale NAT rules
        clear_rules_and_chains
        echo "none" > "$STATE_OUT_IF"
        echo "" > "$STATE_TABLE"
        echo "none"
        return 0
    fi

    out_if="${resolved%% *}"
    table_id="${resolved##* }"

    clear_rules_and_chains

    $IPT -N opdlink_fwd >/dev/null 2>&1 || true
    $IPT -F opdlink_fwd
    $IPT -A opdlink_fwd -i "$p2p_if" -o "$out_if" -j ACCEPT
    $IPT -A opdlink_fwd -i "$out_if" -o "$p2p_if" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
    $IPT -I tetherctrl_FORWARD 1 -j opdlink_fwd

    $IPT -t nat -N opdlink_nat >/dev/null 2>&1 || true
    $IPT -t nat -F opdlink_nat
    $IPT -t nat -A opdlink_nat -s 192.168.49.0/24 -o "$out_if" -j MASQUERADE
    $IPT -t nat -I tetherctrl_nat_POSTROUTING 1 -j opdlink_nat

    ip rule add pref 9996 to 192.168.49.0/24 lookup main
    ip rule add pref 9997 from 192.168.49.0/24 lookup "$table_id"

    echo "$out_if" > "$STATE_OUT_IF"
    echo "$table_id" > "$STATE_TABLE"
    echo "$out_if"
    return 0
}

cmd_down() {
    clear_rules_and_chains
    if [ -f "$STATE_IPFWD" ]; then
        orig="$(cat "$STATE_IPFWD" 2>/dev/null || echo 0)"
        if [ "$orig" = "0" ] || [ "$orig" = "1" ]; then
            echo "$orig" > /proc/sys/net/ipv4/ip_forward 2>/dev/null || true
        fi
    fi
    rm -f "$STATE_IPFWD" "$STATE_P2P_IF" "$STATE_OUT_IF" "$STATE_TABLE"
    cmd wifip2p remove-group >/dev/null 2>&1 || true
    cmd wifip2p deinit >/dev/null 2>&1 || true
    echo "OK down"
}

cmd_up() {
    ssid="${1:-}"
    psk="${2:-}"
    freq="${3:-2462}"
    upstream_req="${4:-none}"

    if [ -z "$ssid" ] || [ -z "$psk" ]; then
        log_err "missing ssid or psk"
        exit 2
    fi

    clear_rules_and_chains
    cmd wifip2p remove-group >/dev/null 2>&1 || true
    cmd wifip2p init >/dev/null 2>&1 || true
    sleep 0.25

    if ! conn_out="$(cmd wifip2p connect-with-config "$ssid" "$psk" "$freq" false 2>&1)"; then
        log_err "wifip2p connect-with-config failed: ${conn_out}"
        cmd_down >/dev/null 2>&1 || true
        exit 1
    fi

    p2p_info=""
    i=0
    while [ "$i" -lt 90 ]; do
        p2p_info="$(find_p2p_ip || true)"
        if [ -n "$p2p_info" ]; then
            break
        fi
        i=$((i + 1))
        sleep 0.2
    done

    if [ -z "$p2p_info" ]; then
        log_err "timed out waiting for 192.168.49.x on p2p"
        cmd_down >/dev/null 2>&1 || true
        exit 1
    fi

    p2p_if="${p2p_info%% *}"
    p2p_ip="${p2p_info##* }"
    echo "$p2p_if" > "$STATE_P2P_IF"

    iw dev "$p2p_if" set power_save off >/dev/null 2>&1 || true
    echo 0 > "/proc/sys/net/ipv4/conf/${p2p_if}/rp_filter" 2>/dev/null || true

    if [ ! -f "$STATE_IPFWD" ]; then
        cat /proc/sys/net/ipv4/ip_forward > "$STATE_IPFWD"
    fi
    echo 1 > /proc/sys/net/ipv4/ip_forward

    out_if="$(apply_nat "$p2p_if" "$upstream_req")"
    echo "OK ${p2p_ip} ${out_if}"
}

cmd_switch() {
    upstream_req="${1:-none}"
    p2p_if=""
    if [ -f "$STATE_P2P_IF" ]; then
        p2p_if="$(cat "$STATE_P2P_IF" 2>/dev/null || true)"
    fi
    if [ -z "$p2p_if" ]; then
        p2p_info="$(find_p2p_ip || true)"
        p2p_if="${p2p_info%% *}"
    fi
    if [ -z "$p2p_if" ]; then
        log_err "no active p2p interface"
        exit 1
    fi
    out_if="$(apply_nat "$p2p_if" "$upstream_req")"
    echo "OK switch ${out_if}"
}

cmd_status() {
    p2p_info="$(find_p2p_ip || true)"
    out_if="$(cat "$STATE_OUT_IF" 2>/dev/null || echo none)"
    tid="$(cat "$STATE_TABLE" 2>/dev/null || echo none)"
    fwd="$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo '?')"
    echo "p2p=${p2p_info:-none} out=${out_if} table=${tid} ip_forward=${fwd}"
}

case "${1:-}" in
    up)
        shift
        cmd_up "$@"
        ;;
    switch)
        shift
        cmd_switch "$@"
        ;;
    down)
        cmd_down
        ;;
    status)
        cmd_status
        ;;
    *)
        log_err "usage: helper.sh {up <ssid> <psk> <freq> <upstream>|switch <upstream>|down|status}"
        exit 2
        ;;
esac
