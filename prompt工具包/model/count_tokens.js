// count_tokens.js：gen_tiers.py 用的 token 計數器（Qwen2.5、Gemma3、o200k 三種取最大）。
// 安裝（在任一個空資料夾）：npm install @lenml/tokenizer-qwen2_5 @lenml/tokenizer-gemma3 gpt-tokenizer
// 把這個檔複製到那個資料夾，然後在 prompt工具包/ 執行：TOKCOUNT=<那個資料夾>/count_tokens.js python3 model/gen_tiers.py
// 沒裝的話 gen_tiers.py 會用估算（偏保守）。
// stdin: JSON array of strings → stdout: JSON array of {qwen2_5, gemma3, o200k, max}
const { fromPreTrained: qwen } = require('@lenml/tokenizer-qwen2_5');
const { fromPreTrained: gemma } = require('@lenml/tokenizer-gemma3');
const { encode: o200k } = require('gpt-tokenizer/encoding/o200k_base');
const tq = qwen(), tg = gemma();
let buf = '';
process.stdin.on('data', d => buf += d);
process.stdin.on('end', () => {
  const out = JSON.parse(buf).map(t => {
    const q = tq.encode(t, { add_special_tokens: false }).length;
    const g = tg.encode(t, { add_special_tokens: false }).length;
    const o = o200k(t).length;
    return { qwen2_5: q, gemma3: g, o200k: o, max: Math.max(q, g, o) };
  });
  process.stdout.write(JSON.stringify(out));
});
