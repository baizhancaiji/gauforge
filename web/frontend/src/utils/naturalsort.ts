/**
 * 文件名自然序排序（m1-plan M1.1，与后端 web/src/parse/naturalsort.py 同规则）：
 * 文件名切分为 [字母|数字] 块序列；字母块 casefold 字典序、数字块数值序、
 * 字母块先于数字块（A–Z 先于 0–9）；其余字符仅作分隔不参与键。
 */

type Block = { kind: 0 | 1; num: number; str: string };

const TOKEN = /[A-Za-z]+|[0-9]+/g;

function naturalKey(name: string): Block[] {
  const blocks: Block[] = [];
  for (const m of name.matchAll(TOKEN)) {
    const s = m[0];
    if (s[0] >= "0" && s[0] <= "9") blocks.push({ kind: 1, num: parseInt(s, 10), str: "" });
    else blocks.push({ kind: 0, num: 0, str: s.toLowerCase() });
  }
  return blocks;
}

/** 按码点比较（与 Python 字符串字典序一致，不用 localeCompare 避免环境差异）。 */
function cmpStr(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

export function naturalCompare(a: string, b: string): number {
  const ka = naturalKey(a);
  const kb = naturalKey(b);
  const n = Math.min(ka.length, kb.length);
  for (let i = 0; i < n; i++) {
    const x = ka[i];
    const y = kb[i];
    if (x.kind !== y.kind) return x.kind - y.kind;
    if (x.kind === 1) {
      if (x.num !== y.num) return x.num - y.num;
    } else {
      const c = cmpStr(x.str, y.str);
      if (c !== 0) return c;
    }
  }
  return ka.length - kb.length;
}
