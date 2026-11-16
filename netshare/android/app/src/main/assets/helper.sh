#!/system/bin/sh
# OPD2413 cross-device network share root helper (runs on rooted Android via su)
set -u

PATH="/system/bin:/system/xbin:/vendor/bin:${PATH:-}"
IPT="iptables -w 2"
IP6T="ip6tables -w 2"
STATE_IPFWD="/dev/.opdlink_ipfwd_orig"
STATE_IP6FWD="/dev/.opdlink_ip6fwd_orig"
STATE_P2P_IF="/dev/.opdlink_p2p_if"
STATE_OUT_IF="/dev/.opdlink_out_if"
STATE_TABLE="/dev/.opdlink_table_id"
STATE_V6_OUT_IF="/dev/.opdlink_v6_out_if"
STATE_V6_TABLE="/dev/.opdlink_v6_table_id"
STATE_V6_ADDR="/dev/.opdlink_v6_addr"
STATE_TABLET_LL="/dev/.opdlink_tablet_ll"
STATE_V4_DIRTY="/dev/.opdlink_v4_dirty"
STATE_V6_DIRTY="/dev/.opdlink_v6_dirty"
STATE_V6NAT="/dev/.opdlink_v6nat_ok"

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

scan_p2p_ip_lines() {
    while read -r _idx ifc _fam cidr _rest; do
        case "$cidr" in
            192.168.49.*)
                echo "$ifc ${cidr%%/*}"
                return 0
                ;;
        esac
    done
    return 1
}

find_p2p_ip() {
    res="$(ip -o -4 addr show dev p2p0 2>/dev/null | scan_p2p_ip_lines || true)"
    if [ -n "$res" ]; then
        echo "$res"
        return 0
    fi
    res="$(ip -o -4 addr show 2>/dev/null | scan_p2p_ip_lines || true)"
    if [ -n "$res" ]; then
        echo "$res"
        return 0
    fi
    return 1
}

find_table_v6_def_dev() {
    tid="$1"
    [ -n "$tid" ] || return 1
    ip -6 route show table "$tid" 2>/dev/null | while read -r line; do
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

resolve_v6_upstream() {
    req="${1#v4-}"
    [ -n "$req" ] && [ "$req" != "none" ] || return 1
    tid="$(lookup_rt_table "$req" || true)"
    if [ -n "$tid" ]; then
        defdev="$(find_table_v6_def_dev "$tid" || true)"
        if [ -n "$defdev" ]; then
            echo "$defdev $tid"
            return 0
        fi
        if ip -6 route show table "$tid" 2>/dev/null | grep -q '^default '; then
            echo "$req $tid"
            return 0
        fi
    fi
    return 1
}

find_p2p_v6_ll() {
    ifc="$1"
    [ -n "$ifc" ] || return 1
    ip -o -6 addr show dev "$ifc" scope link 2>/dev/null | while read -r line; do
        case "$line" in
            *tentative*) continue ;;
        esac
        for tok in $line; do
            case "$tok" in
                fe80:*)
                    echo "${tok%%/*}"
                    return 0
                    ;;
            esac
        done
    done
    return 1
}

wait_p2p_v6_ll() {
    ifc="$1"
    j=0
    while [ "$j" -lt 20 ]; do
        ll="$(find_p2p_v6_ll "$ifc" || true)"
        if [ -n "$ll" ]; then
            echo "$ll"
            return 0
        fi
        j=$((j + 1))
        sleep 0.05
    done
    return 1
}

get_sta_freq() {
    # Do not fall back to wpa_cli: SELinux blocks hal_wifi_supplicant_default replies
    # to su contexts and makes every wpa_cli call hang for ~10s until timeout.
    if command -v iw >/dev/null 2>&1; then
        f="$(iw dev wlan0 link 2>/dev/null | sed -n 's/.*freq:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n1)"
        if [ -n "$f" ] && [ "$f" -ge 2400 ] 2>/dev/null; then
            echo "$f"
            return 0
        fi
    fi
    return 1
}

get_p2p_cur_state() {
    dumpsys wifip2p 2>/dev/null | sed -n 's/.*curState=\([A-Za-z0-9_]*\).*/\1/p' | head -n1
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
    rm -f "$STATE_V4_DIRTY"
}

v4_rules_maybe_dirty() {
    if [ -f "$STATE_V4_DIRTY" ]; then
        return 0
    fi
    if [ -f "$STATE_OUT_IF" ] && [ "$(cat "$STATE_OUT_IF" 2>/dev/null || echo none)" != "none" ]; then
        return 0
    fi
    return 1
}

apply_nat() {
    p2p_if="$1"
    upstream_req="$2"

    resolved="$(resolve_upstream "$upstream_req" || true)"
    if [ -z "$resolved" ]; then
        # No physical upstream yet: keep P2P link alive without stale NAT rules
        if v4_rules_maybe_dirty; then
            clear_rules_and_chains
        fi
        echo "none" > "$STATE_OUT_IF"
        echo "" > "$STATE_TABLE"
        echo "none"
        return 0
    fi

    out_if="${resolved%% *}"
    table_id="${resolved##* }"

    if v4_rules_maybe_dirty; then
        clear_rules_and_chains
    fi
    : > "$STATE_V4_DIRTY"

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

clear_v6_rules_and_chains() {
    while ip -6 rule del pref 9996 >/dev/null 2>&1; do :; done
    while ip -6 rule del pref 9997 >/dev/null 2>&1; do :; done

    if [ -f "$STATE_V6_ADDR" ]; then
        old_v6="$(cat "$STATE_V6_ADDR" 2>/dev/null || true)"
        if [ -n "$old_v6" ]; then
            ip -6 route del "${old_v6}/128" table main >/dev/null 2>&1 || true
            if [ -f "$STATE_V6_OUT_IF" ]; then
                old_out="$(cat "$STATE_V6_OUT_IF" 2>/dev/null || true)"
                if [ -n "$old_out" ] && [ "$old_out" != "none" ]; then
                    ip -6 neigh del proxy "$old_v6" dev "$old_out" >/dev/null 2>&1 || true
                fi
            fi
        fi
    fi

    $IP6T -D tetherctrl_FORWARD -j opdlink_fwd6 >/dev/null 2>&1 || true
    $IP6T -D FORWARD -j opdlink_fwd6 >/dev/null 2>&1 || true
    $IP6T -F opdlink_fwd6 >/dev/null 2>&1 || true
    $IP6T -X opdlink_fwd6 >/dev/null 2>&1 || true

    $IP6T -t nat -D POSTROUTING -j opdlink_nat6 >/dev/null 2>&1 || true
    $IP6T -t nat -F opdlink_nat6 >/dev/null 2>&1 || true
    $IP6T -t nat -X opdlink_nat6 >/dev/null 2>&1 || true

    $IP6T -t mangle -D FORWARD -j opdlink_mangle6 >/dev/null 2>&1 || true
    $IP6T -t mangle -F opdlink_mangle6 >/dev/null 2>&1 || true
    $IP6T -t mangle -X opdlink_mangle6 >/dev/null 2>&1 || true
    rm -f "$STATE_V6_DIRTY"
}

v6_rules_maybe_dirty() {
    if [ -f "$STATE_V6_DIRTY" ]; then
        return 0
    fi
    if [ -f "$STATE_V6_OUT_IF" ] && [ "$(cat "$STATE_V6_OUT_IF" 2>/dev/null || echo none)" != "none" ]; then
        return 0
    fi
    return 1
}

apply_v6() {
    p2p_if="$1"
    v6_upstream_req="$2"
    tablet_v6="$3"
    tablet_ll="$4"

    if [ -z "$v6_upstream_req" ] || [ "$v6_upstream_req" = "none" ] \
        || [ -z "$tablet_v6" ] || [ "$tablet_v6" = "none" ]; then
        if v6_rules_maybe_dirty; then
            clear_v6_rules_and_chains
        fi
        echo "none" > "$STATE_V6_OUT_IF"
        echo "" > "$STATE_V6_TABLE"
        echo "" > "$STATE_V6_ADDR"
        echo "none"
        return 0
    fi

    resolved="$(resolve_v6_upstream "$v6_upstream_req" || true)"
    if [ -z "$resolved" ]; then
        if v6_rules_maybe_dirty; then
            clear_v6_rules_and_chains
        fi
        echo "none" > "$STATE_V6_OUT_IF"
        echo "" > "$STATE_V6_TABLE"
        echo "" > "$STATE_V6_ADDR"
        echo "none"
        return 0
    fi

    if v6_rules_maybe_dirty; then
        clear_v6_rules_and_chains
    fi
    : > "$STATE_V6_DIRTY"

    v6_out_if="${resolved%% *}"
    v6_table_id="${resolved##* }"

    echo 0 > "/proc/sys/net/ipv6/conf/${p2p_if}/disable_ipv6" 2>/dev/null || true
    echo 2 > "/proc/sys/net/ipv6/conf/${v6_out_if}/accept_ra" 2>/dev/null || true
    if [ ! -f "$STATE_IP6FWD" ]; then
        cat /proc/sys/net/ipv6/conf/all/forwarding > "$STATE_IP6FWD" 2>/dev/null || echo 0 > "$STATE_IP6FWD"
    fi
    echo 1 > /proc/sys/net/ipv6/conf/all/forwarding 2>/dev/null || true
    echo 1 > "/proc/sys/net/ipv6/conf/${p2p_if}/forwarding" 2>/dev/null || true
    echo 1 > "/proc/sys/net/ipv6/conf/${v6_out_if}/forwarding" 2>/dev/null || true

    $IP6T -N opdlink_fwd6 >/dev/null 2>&1 || true
    $IP6T -F opdlink_fwd6
    $IP6T -A opdlink_fwd6 -i "$p2p_if" -o "$v6_out_if" -j ACCEPT
    $IP6T -A opdlink_fwd6 -i "$v6_out_if" -o "$p2p_if" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
    $IP6T -A opdlink_fwd6 -i "$v6_out_if" -o "$p2p_if" -p ipv6-icmp -j ACCEPT
    if $IP6T -L tetherctrl_FORWARD -n >/dev/null 2>&1; then
        $IP6T -I tetherctrl_FORWARD 1 -j opdlink_fwd6
    else
        $IP6T -I FORWARD 1 -j opdlink_fwd6
    fi

    if $IP6T -t mangle -N opdlink_mangle6 >/dev/null 2>&1 || $IP6T -t mangle -L opdlink_mangle6 -n >/dev/null 2>&1; then
        $IP6T -t mangle -F opdlink_mangle6 >/dev/null 2>&1 || true
        if $IP6T -t mangle -A opdlink_mangle6 -o "$v6_out_if" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu >/dev/null 2>&1; then
            $IP6T -t mangle -I FORWARD 1 -j opdlink_mangle6 >/dev/null 2>&1 || true
        fi
    fi

    nat6_ok=0
    v6nat_cached="$(cat "$STATE_V6NAT" 2>/dev/null || true)"
    if [ "$v6nat_cached" != "0" ]; then
        if $IP6T -t nat -N opdlink_nat6 >/dev/null 2>&1 || $IP6T -t nat -L opdlink_nat6 -n >/dev/null 2>&1; then
            if $IP6T -t nat -F opdlink_nat6 >/dev/null 2>&1 \
                && $IP6T -t nat -A opdlink_nat6 -s "${tablet_v6}/128" -o "$v6_out_if" -j MASQUERADE >/dev/null 2>&1 \
                && $IP6T -t nat -I POSTROUTING 1 -j opdlink_nat6 >/dev/null 2>&1; then
                nat6_ok=1
                echo 1 > "$STATE_V6NAT" 2>/dev/null || true
            else
                $IP6T -t nat -D POSTROUTING -j opdlink_nat6 >/dev/null 2>&1 || true
                $IP6T -t nat -F opdlink_nat6 >/dev/null 2>&1 || true
                $IP6T -t nat -X opdlink_nat6 >/dev/null 2>&1 || true
                echo 0 > "$STATE_V6NAT" 2>/dev/null || true
            fi
        else
            echo 0 > "$STATE_V6NAT" 2>/dev/null || true
        fi
    fi

    if [ "$nat6_ok" -eq 0 ]; then
        echo 1 > "/proc/sys/net/ipv6/conf/${v6_out_if}/proxy_ndp" 2>/dev/null || true
        ip -6 neigh replace proxy "$tablet_v6" dev "$v6_out_if" >/dev/null 2>&1 || true
    fi

    if [ -n "$tablet_ll" ] && [ "$tablet_ll" != "none" ]; then
        ip -6 route replace "${tablet_v6}/128" via "$tablet_ll" dev "$p2p_if" table main
    else
        ip -6 route replace "${tablet_v6}/128" dev "$p2p_if" table main
    fi
    ip -6 rule add pref 9996 to "${tablet_v6}/128" lookup main
    ip -6 rule add pref 9997 iif "$p2p_if" lookup "$v6_table_id"

    echo "$v6_out_if" > "$STATE_V6_OUT_IF"
    echo "$v6_table_id" > "$STATE_V6_TABLE"
    echo "$tablet_v6" > "$STATE_V6_ADDR"
    echo "${tablet_ll:-none}" > "$STATE_TABLET_LL"
    echo "$v6_out_if"
    return 0
}

cmd_cancel() {
    cmd wifip2p cancel-connect >/dev/null 2>&1 || true
    cmd wifip2p remove-group >/dev/null 2>&1 || true
}

cmd_down() {
    clear_rules_and_chains
    clear_v6_rules_and_chains
    if [ -f "$STATE_IPFWD" ]; then
        orig="$(cat "$STATE_IPFWD" 2>/dev/null || echo 0)"
        if [ "$orig" = "0" ] || [ "$orig" = "1" ]; then
            echo "$orig" > /proc/sys/net/ipv4/ip_forward 2>/dev/null || true
        fi
    fi
    if [ -f "$STATE_IP6FWD" ]; then
        orig6="$(cat "$STATE_IP6FWD" 2>/dev/null || echo 0)"
        if [ "$orig6" = "0" ] || [ "$orig6" = "1" ]; then
            echo "$orig6" > /proc/sys/net/ipv6/conf/all/forwarding 2>/dev/null || true
        fi
    fi
    rm -f "$STATE_IPFWD" "$STATE_IP6FWD" "$STATE_P2P_IF" "$STATE_OUT_IF" "$STATE_TABLE" \
          "$STATE_V6_OUT_IF" "$STATE_V6_TABLE" "$STATE_V6_ADDR" "$STATE_TABLET_LL"
    cmd_cancel
    echo "OK down"
}

ensure_p2p_ready() {
    if [ -d /proc/sys/net/ipv6/conf/p2p0 ]; then
        echo 0 > /proc/sys/net/ipv6/conf/p2p0/disable_ipv6 2>/dev/null || true
        echo 0 > /proc/sys/net/ipv6/conf/p2p0/dad_transmits 2>/dev/null || true
        echo 0 > /proc/sys/net/ipv6/conf/p2p0/accept_dad 2>/dev/null || true
    fi
    st="$(get_p2p_cur_state || true)"
    case "$st" in
        ""|P2pDisabledState|P2pDisablingState|P2pEnablingState)
            cmd wifip2p init >/dev/null 2>&1 || true
            w=0
            while [ "$w" -lt 15 ]; do
                sleep 0.15
                st="$(get_p2p_cur_state || true)"
                case "$st" in
                    ""|P2pDisabledState|P2pDisablingState|P2pEnablingState) ;;
                    *) break ;;
                esac
                w=$((w + 1))
            done
            ;;
    esac
    if [ "$st" != "InactiveState" ]; then
        cmd wifip2p cancel-connect >/dev/null 2>&1 || true
        cmd wifip2p remove-group >/dev/null 2>&1 || true
        w=0
        while [ "$w" -lt 10 ]; do
            st="$(get_p2p_cur_state || true)"
            case "$st" in
                OngoingGroupRemovalState|GroupCreatedState)
                    sleep 0.12
                    ;;
                *)
                    break
                    ;;
            esac
            w=$((w + 1))
        done
    fi
}

cmd_up() {
    ssid="${1:-}"
    psk="${2:-}"
    freq="${3:-2462}"
    upstream_req="${4:-none}"
    v6_upstream_req="${5:-none}"
    tablet_v6="${6:-none}"
    tablet_ll="${7:-none}"

    if [ -z "$ssid" ] || [ -z "$psk" ]; then
        log_err "missing ssid or psk"
        exit 2
    fi

    if v4_rules_maybe_dirty; then
        clear_rules_and_chains
    fi
    if v6_rules_maybe_dirty; then
        clear_v6_rules_and_chains
    fi
    ensure_p2p_ready

    if ! conn_out="$(cmd wifip2p connect-with-config "$ssid" "$psk" "$freq" false 2>&1)"; then
        sta_freq="$(get_sta_freq || echo 0)"
        log_err "wifip2p connect-with-config failed (sta_freq=${sta_freq}): ${conn_out}"
        cmd_cancel
        exit 1
    fi

    p2p_info=""
    seen_negotiating=0
    early_fail=""
    start_s="$(date +%s 2>/dev/null || echo 0)"
    i=0
    while [ "$i" -lt 140 ]; do
        p2p_info="$(find_p2p_ip || true)"
        if [ -n "$p2p_info" ]; then
            break
        fi
        now_s="$(date +%s 2>/dev/null || echo 0)"
        elapsed=0
        if [ "$start_s" -gt 0 ] 2>/dev/null && [ "$now_s" -ge "$start_s" ] 2>/dev/null; then
            elapsed=$((now_s - start_s))
        fi
        if [ "$elapsed" -ge 16 ]; then
            break
        fi
        if [ "$i" -ge 8 ] && [ $((i % 8)) -eq 0 ]; then
            cur_state="$(get_p2p_cur_state || true)"
            case "$cur_state" in
                GroupNegotiationState|ProvisionDiscoveryState|OngoingGroupRemovalState|FrequencyConflictState)
                    seen_negotiating=1
                    ;;
                InactiveState|P2pDisabledState)
                    if [ "$seen_negotiating" -eq 1 ] || [ "$elapsed" -ge 5 ] || [ "$i" -ge 35 ]; then
                        early_fail="$cur_state"
                        break
                    fi
                    ;;
            esac
        fi
        i=$((i + 1))
        if [ "$i" -le 25 ]; then
            sleep 0.06
        else
            sleep 0.15
        fi
    done

    if [ -z "$p2p_info" ]; then
        sta_freq="$(get_sta_freq || echo 0)"
        if [ -n "$early_fail" ]; then
            log_err "p2p group formation failed (state=${early_fail}, freq=${freq}, sta_freq=${sta_freq})"
        else
            log_err "timed out waiting for 192.168.49.x on p2p (freq=${freq}, sta_freq=${sta_freq})"
        fi
        cmd_cancel
        exit 1
    fi

    p2p_if="${p2p_info%% *}"
    p2p_ip="${p2p_info##* }"
    echo "$p2p_if" > "$STATE_P2P_IF"

    iw dev "$p2p_if" set power_save off >/dev/null 2>&1 || true
    echo 0 > "/proc/sys/net/ipv4/conf/${p2p_if}/rp_filter" 2>/dev/null || true
    echo 0 > "/proc/sys/net/ipv6/conf/${p2p_if}/dad_transmits" 2>/dev/null || true
    echo 0 > "/proc/sys/net/ipv6/conf/${p2p_if}/accept_dad" 2>/dev/null || true

    if [ ! -f "$STATE_IPFWD" ]; then
        cat /proc/sys/net/ipv4/ip_forward > "$STATE_IPFWD"
    fi
    echo 1 > /proc/sys/net/ipv4/ip_forward

    out_if="$(apply_nat "$p2p_if" "$upstream_req")"
    p2p_v6_ll="$(wait_p2p_v6_ll "$p2p_if" || true)"
    v6_out="$(apply_v6 "$p2p_if" "$v6_upstream_req" "$tablet_v6" "$tablet_ll")"
    echo "OK ${p2p_ip} ${out_if} ${p2p_v6_ll:-none} ${v6_out:-none}"
}

cmd_switch() {
    upstream_req="${1:-none}"
    v6_upstream_req="${2:-none}"
    tablet_v6="${3:-none}"
    tablet_ll="${4:-none}"
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
    if [ "$tablet_ll" = "none" ] && [ -f "$STATE_TABLET_LL" ]; then
        tablet_ll="$(cat "$STATE_TABLET_LL" 2>/dev/null || echo none)"
    fi
    out_if="$(apply_nat "$p2p_if" "$upstream_req")"
    p2p_v6_ll="$(find_p2p_v6_ll "$p2p_if" || true)"
    v6_out="$(apply_v6 "$p2p_if" "$v6_upstream_req" "$tablet_v6" "$tablet_ll")"
    echo "OK switch ${out_if} ${p2p_v6_ll:-none} ${v6_out:-none}"
}

cmd_status() {
    p2p_info="$(find_p2p_ip || true)"
    out_if="$(cat "$STATE_OUT_IF" 2>/dev/null || echo none)"
    tid="$(cat "$STATE_TABLE" 2>/dev/null || echo none)"
    fwd="$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo '?')"
    v6_out="$(cat "$STATE_V6_OUT_IF" 2>/dev/null || echo none)"
    v6_addr="$(cat "$STATE_V6_ADDR" 2>/dev/null || echo none)"
    echo "p2p=${p2p_info:-none} out=${out_if} table=${tid} ip_forward=${fwd} v6_out=${v6_out} v6_addr=${v6_addr}"
}

cmd_sta_freq() {
    f="$(get_sta_freq || echo 0)"
    echo "${f:-0}"
}

clear_adb_fw() {
    while $IPT -D INPUT -p tcp --dport 5555 -j opdlink_adb >/dev/null 2>&1; do :; done
    $IPT -F opdlink_adb >/dev/null 2>&1 || true
    $IPT -X opdlink_adb >/dev/null 2>&1 || true
    while $IP6T -D INPUT -p tcp --dport 5555 -j opdlink_adb6 >/dev/null 2>&1; do :; done
    $IP6T -F opdlink_adb6 >/dev/null 2>&1 || true
    $IP6T -X opdlink_adb6 >/dev/null 2>&1 || true
}

cmd_adb_on() {
    clear_adb_fw
    $IPT -N opdlink_adb >/dev/null 2>&1 || true
    $IPT -F opdlink_adb
    $IPT -A opdlink_adb -i p2p+ -s 192.168.49.1 -j ACCEPT
    $IPT -A opdlink_adb -j DROP
    $IPT -I INPUT 1 -p tcp --dport 5555 -j opdlink_adb

    $IP6T -N opdlink_adb6 >/dev/null 2>&1 || true
    $IP6T -F opdlink_adb6
    $IP6T -A opdlink_adb6 -j DROP
    $IP6T -I INPUT 1 -p tcp --dport 5555 -j opdlink_adb6

    setprop service.adb.tcp.port 5555
    stop adbd
    start adbd
    echo "OK adb-on"
}

cmd_adb_off() {
    setprop service.adb.tcp.port -1
    stop adbd
    start adbd
    clear_adb_fw
    echo "OK adb-off"
}

cmd_adb_status() {
    port="$(getprop service.adb.tcp.port 2>/dev/null || true)"
    running="$(getprop init.svc.adbd 2>/dev/null || true)"
    fw="off"
    if $IPT -C INPUT -p tcp --dport 5555 -j opdlink_adb >/dev/null 2>&1; then
        fw="p2p-only"
    fi
    echo "port=${port:-unset} adbd=${running:-unknown} fw=${fw}"
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
    cancel)
        cmd_cancel
        echo "OK cancel"
        ;;
    status)
        cmd_status
        ;;
    sta-freq)
        cmd_sta_freq
        ;;
    adb-on)
        cmd_adb_on
        ;;
    adb-off)
        cmd_adb_off
        ;;
    adb-status)
        cmd_adb_status
        ;;
    *)
        log_err "usage: helper.sh {up <ssid> <psk> <freq> <upstream> [v6_upstream] [tablet_v6] [tablet_ll]|switch <upstream> [v6_upstream] [tablet_v6] [tablet_ll]|down|status|sta-freq|adb-on|adb-off|adb-status}"
        exit 2
        ;;
esac
