#!/bin/sh
# 假 cubegen（第 N 次调用失败形态，B18 fixture）：调用计数落 cwd 状态
# 文件（子进程 cwd = 执行目录，天然隔离）；CUBEGEN_FAIL_ON 指定失败
# 次序，未命中则正常产出。
count_file="cubegen-invocations.state"
[ -f "$count_file" ] || echo 0 > "$count_file"
n=$(cat "$count_file")
n=$((n + 1))
echo "$n" > "$count_file"
if [ -n "$CUBEGEN_FAIL_ON" ] && [ "$n" = "$CUBEGEN_FAIL_ON" ]; then
    echo "boom on call $n" >&2
    exit 3
fi
printf "cube\n" > "$4"
