#!/bin/bash
# EC2 claude-host status for waybar: cpu/mem/load via one ssh call, offline-aware.

out=$(ssh -o ConnectTimeout=4 -o BatchMode=yes claude-host bash -s 2>/dev/null <<'EOF'
cpu=$( (grep '^cpu ' /proc/stat; sleep 0.5; grep '^cpu ' /proc/stat) | \
  awk '{t=$2+$3+$4+$5+$6+$7+$8; i=$5+$6} NR==1{t1=t;i1=i} NR==2{printf "%d", (1-(i-i1)/(t-t1))*100}')
mem=$(free -m | awk '/^Mem:/{printf "%d|%d|%d", $3/$2*100, $3, $2}')
load=$(cut -d' ' -f1-3 /proc/loadavg)
up=$(uptime -p | sed 's/^up //')
echo "$cpu|$mem|$load|$up"
EOF
)

if [ -z "$out" ]; then
    printf '{"text":"󰒋 offline","class":"offline","tooltip":"claude-host unreachable"}\n'
    exit 0
fi

IFS='|' read -r cpu mempct memused memtot load up <<< "$out"

class="healthy"
[ "$cpu" -ge 70 ] || [ "$mempct" -ge 70 ] && class="warning"
[ "$cpu" -ge 90 ] || [ "$mempct" -ge 90 ] && class="critical"

printf '{"text":"󰒋 %s%% 󰍛 %s%%","class":"%s","tooltip":"claude-host (EC2)\\nstatus: %s\\ncpu: %s%%\\nmem: %s/%s MB (%s%%)\\nload: %s\\nup: %s"}\n' \
    "$cpu" "$mempct" "$class" "$class" "$cpu" "$memused" "$memtot" "$mempct" "$load" "$up"
