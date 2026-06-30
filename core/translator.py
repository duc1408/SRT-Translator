"""
translator.py — Parallel SRT translation engine (v4 — Mandatory Translation).

Architecture:
  - Split blocks into N chunks (one per API key)
  - Run N ThreadPoolExecutor workers simultaneously
  - Each worker sends batches of blocks to OpenRouter
  - **Layer 1**: Batch Validation — after each API response, check for
    missing or identical (untranslated) blocks → retry immediately
  - **Layer 2**: Content-Change Detection — compare source vs output text
    to flag blocks that were returned unchanged
  - **Layer 3**: Multi-Pass Self-Healing — after all workers finish, scan
    for remaining untranslated blocks, retry with rotating keys (max 3 rounds)
  - **Layer 4**: Fallback Model Cascade — if blocks still remain after Layer 3,
    automatically switch through free fallback models one by one until 100%
    blocks are translated. Translation is MANDATORY — will not give up.
  - Merge results in original order
"""

import json
import re
import time
import urllib.request
import urllib.error
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Set, Tuple

from core.srt_parser import SrtBlock

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AIBOX_URL = "https://api.ai-box.vn/v1/chat/completions"

SKIP_RE = re.compile(
    r"^\s*([\u266a\u266b]+|\[Music\]|\[Applause\]|\(Music\)|\[.*?\]|\(.*?\)|\.\.\.|-{2,}|\u2013{2,})\s*$",
    re.IGNORECASE,
)

# Regex patterns for detecting untranslated text (source language remains)
CHINESE_RE  = re.compile(r"[\u4e00-\u9fff]")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff]")   # hiragana + katakana
KOREAN_RE   = re.compile(r"[\uac00-\ud7af]")
ARABIC_RE   = re.compile(r"[\u0600-\u06ff]")
THAI_RE     = re.compile(r"[\u0e00-\u0e7f]")
CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")

# Map target language → which scripts should NOT remain in the output
# (e.g. translating FROM Chinese → target is Indonesian → Chinese chars = bad)
# We detect source language from the input blocks automatically.
SCRIPT_DETECTORS = {
    "chinese":   CHINESE_RE,
    "japanese":  JAPANESE_RE,
    "korean":    KOREAN_RE,
    "arabic":    ARABIC_RE,
    "thai":      THAI_RE,
    "russian":   CYRILLIC_RE,
}

LANG_NAMES = {
    "indonesian":  "Indonesian",
    "thai":        "Thai",
    "vietnamese":  "Vietnamese",
    "hindi":       "Hindi",
    "korean":      "Korean",
    "spanish":     "Spanish (Latin America)",
    "french":      "French",
    "german":      "German",
    "portuguese":  "Portuguese (Brazil)",
    "english":     "English",
    "turkish":     "Turkish",
    "filipino":    "Filipino/Tagalog",
    "russian":     "Russian",
    "japanese":    "Japanese",
    "chinese":     "Chinese (Simplified)",
    "arabic":      "Arabic",
}

CONTENT_LABELS = {
    "auto":         "general",
    "film":         "drama/film",
    "anime":        "anime",
    "wuxia":        "wuxia/martial arts",
    "news":         "news",
    "documentary":  "documentary",
}

# Self-healing constants
# ⚡ Optimized for quota efficiency (A+B plan):
#   - HEAL_BATCH_SIZE 40: larger heal batches → system prompt overhead ~50% less
#   - MAX_HEAL_ROUNDS 2:  round 3 rarely helps; saves wasted API calls
#   - BATCH_RETRY_ATTEMPTS 3: 3 retries sufficient; 4th rarely succeeds
MAX_HEAL_ROUNDS       = 2    # maximum self-healing passes with primary model
HEAL_BATCH_SIZE       = 40   # larger batches → less system-prompt overhead per token
BATCH_RETRY_ATTEMPTS  = 3    # retries per individual batch
HEAL_RETRY_ATTEMPTS   = 3    # retries per self-healing batch

# Fallback model cascade — tried in order when primary model fails to translate all blocks
# ⚡ Removed deepseek-v4-pro (3x more expensive than flash, marginal quality gain for subtitles)
FALLBACK_MODELS = [
    "deepseek-v4-flash",
]

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_system_prompt(target_lang: str, content_type: str,
                         glossary: dict = None) -> str:
    """
    Build system prompt for the translation API call.
    ⚡ Quota-optimized: compressed from ~1100 to ~550 tokens (~50% savings per request).
    """
    lang_name     = LANG_NAMES.get(target_lang.lower(), target_lang)
    content_label = CONTENT_LABELS.get(content_type, content_type)

    # Build optional glossary block
    glossary_section = ""
    if glossary:
        lines = [f"  {src} → {tgt}" for src, tgt in glossary.items() if src and tgt]
        if lines:
            glossary_section = "GLOSSARY (apply consistently):\n" + "\n".join(lines) + "\n\n"

    return f"""You are an expert {content_label} subtitle translator. Translate the SRT batch into {lang_name} for TTS dubbing.

RULES:
1. PACING: Text is for TTS voiceover — match block duration. Compress aggressively: shortest natural expression, no fillers, no redundant words.
   - Alphabetic (Indonesian/English/French/Spanish/German/Turkish): use contractions, short synonyms.
   - CJK (Chinese/Japanese/Korean): target 2.5–3.5 syllables/sec of block duration.
   - Abugida (Thai/Vietnamese/Hindi): direct phrasing, avoid long compounds.
   - RTL (Arabic): high semantic density, correct punctuation.

2. STRICT 1-TO-1 MAPPING: Translate ONLY text inside each block. NO word-shifting between blocks. Count blocks before responding — output count MUST equal input count. Mid-thought blocks: end with `...`; continuing blocks: start with `...`.

3. 100% {lang_name} OUTPUT — ZERO SOURCE CHARACTERS: Every single word MUST be in {lang_name} only. Absolutely NO Chinese (汉字/Hanzi), Japanese (かな/Kanji), Korean (한글), Arabic (عربي), Thai (ไทย), or Cyrillic (кирилл) characters are allowed in the output — not even in parentheses or as notes. If a proper name cannot be translated, write it phonetically in {lang_name} letters only. Example: 北京 → "Beijing", not "北京" or "Beijing (北京)".

4. REGISTER: Natural spoken {lang_name} as heard in {content_label}. Match original tone (casual/formal).

5. OUTPUT FORMAT:
   - Wrap result in `<TRANSLATE_TEXT>` tags.
   - Valid SRT only: index → timestamp → translated text → blank line.
   - No markdown, no explanations, no comments.

{glossary_section}Translate the following SRT batch into {lang_name} inside `<TRANSLATE_TEXT>` tags."""


# ---------------------------------------------------------------------------
# Source language detection
# ---------------------------------------------------------------------------

def _detect_source_scripts(blocks: List[SrtBlock]) -> List[re.Pattern]:
    """
    Scan a sample of blocks to detect which script(s) the source text uses.
    Returns a list of regex patterns that match the source script.
    """
    sample_text = " ".join(
        b.text for b in blocks[:50] if b.text and not SKIP_RE.match(b.text)
    )
    detected = []
    for _name, pattern in SCRIPT_DETECTORS.items():
        # If >=5 characters of this script appear, the source uses it
        if len(pattern.findall(sample_text)) >= 5:
            detected.append(pattern)
    return detected


def _is_untranslated(
    source_text: str,
    translated_text: str,
    source_patterns: List[re.Pattern],
    target_lang: str,
) -> bool:
    """
    Determine if a block was NOT actually translated.

    Returns True if:
      1. translated text is identical to source text (nothing changed), OR
      2. translated text still contains significant source-script characters
         (e.g. Chinese chars remain when translating to Indonesian)
    """
    if not translated_text or not translated_text.strip():
        return True

    # Normalize for comparison
    src_clean = source_text.strip().replace("\n", " ").lower()
    tgt_clean = translated_text.strip().replace("\n", " ").lower()

    # Check 1: Identical text (API echoed the input back)
    if src_clean == tgt_clean:
        return True

    # Check 2: Source script characters remain in the output
    # Skip this check if target language uses the same script as source
    target_scripts = set()
    for name, pat in SCRIPT_DETECTORS.items():
        if name == target_lang.lower():
            target_scripts.add(pat)

    # Special case: Japanese and Korean target languages can use Chinese characters (Kanji/Hanja)
    if target_lang.lower() in ("japanese", "korean", "chinese"):
        target_scripts.add(CHINESE_RE)

    for pat in source_patterns:
        if pat in target_scripts:
            continue  # Target lang uses same script, skip
        remain_chars = len(pat.findall(translated_text))
        # If any source-script characters remain in the translation, mark as untranslated
        if remain_chars > 0:
            return True

    return False


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _api_call(api_key: str, model: str, system_prompt: str, user_content: str,
              timeout: int = 90) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        "temperature": 0.25,
    }).encode("utf-8")

    req = urllib.request.Request(
        AIBOX_URL,
        data=payload,
        headers={
            "Authorization":  f"Bearer {api_key}",
            "Content-Type":   "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_response(text: str) -> dict:
    """
    Return {local_idx: translated_text} from LLM response.
    Primary: parse SRT blocks inside <TRANSLATE_TEXT> tags.
    Fallback: try JSON array, then [N] regex.
    """
    result = {}
    text = text.strip()

    # ── Primary: extract <TRANSLATE_TEXT> tag ──
    tag_m = re.search(r"<TRANSLATE_TEXT>(.*?)</TRANSLATE_TEXT>", text, re.DOTALL)
    srt_content = tag_m.group(1).strip() if tag_m else text

    # Strip markdown code fences if present
    if srt_content.startswith("```"):
        fence_m = re.search(r"```(?:srt|\w*)?\s*(.*?)\s*```", srt_content, re.DOTALL)
        if fence_m:
            srt_content = fence_m.group(1).strip()

    # Parse SRT blocks: idx\ntimestamp\ntext(s)\n\n
    for chunk in re.split(r"\n{2,}", srt_content):
        lines = [l for l in chunk.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        # lines[1] is timestamp — skip it if present, otherwise text starts at 1
        text_start = 2 if (len(lines) > 2 and "-->" in lines[1]) else 1
        translated = "\n".join(lines[text_start:]).strip()
        if translated:
            result[idx] = translated

    if result:
        return result

    # ── Fallback 1: JSON array ──
    try:
        raw = srt_content
        parsed = json.loads(raw)
        arr = parsed if isinstance(parsed, list) else parsed.get("translations", [])
        for item in arr:
            if "idx" in item and "text" in item:
                result[int(item["idx"])] = str(item["text"]).replace(" | ", "\n")
        if result:
            return result
    except Exception:
        pass

    # ── Fallback 2: [N] text pattern ──
    for line in srt_content.splitlines():
        m = re.match(r"^\[(\d+)\]\s*(.+)", line.strip())
        if m:
            result[int(m.group(1))] = m.group(2).strip().replace(" | ", "\n")

    return result


# ---------------------------------------------------------------------------
# Build user prompt from blocks
# ---------------------------------------------------------------------------

def _build_user_content(
    blocks: List[SrtBlock],
) -> Tuple[str, Dict[int, int], Dict[int, int]]:
    """
    Build SRT-format input from blocks, skipping music/empty.
    Uses local_i as block index for easy batch parsing.

    Returns:
      user_content  — SRT-formatted string wrapped in <INPUT> tags
      local_map     — {local_idx: position_in_batch}
      block_to_local — {position_in_batch: local_idx}
    """
    srt_parts: list = []
    local_map: Dict[int, int] = {}
    block_to_local: Dict[int, int] = {}

    local_i = 0
    for pos, blk in enumerate(blocks):
        if not blk.text or SKIP_RE.match(blk.text):
            continue
        # Full SRT block: index + timestamp + text
        srt_parts.append(str(local_i))
        srt_parts.append(blk.timestamp)
        srt_parts.append(blk.text)
        srt_parts.append("")   # blank line separator
        local_map[local_i] = pos
        block_to_local[pos] = local_i
        local_i += 1

    inner = "\n".join(srt_parts).strip()
    user_content = f"<INPUT>\n{inner}\n</INPUT>"
    return user_content, local_map, block_to_local


# ---------------------------------------------------------------------------
# Single API call with retry
# ---------------------------------------------------------------------------

def _call_with_retry(
    api_key: str,
    model: str,
    system_prompt: str,
    user_content: str,
    max_attempts: int,
    label: str,
    log_cb: Optional[Callable],
) -> dict:
    """
    Call the API with exponential backoff retry.
    Returns parsed {local_idx: text} dict (may be empty on total failure).
    """
    for attempt in range(1, max_attempts + 1):
        try:
            raw = _api_call(api_key, model, system_prompt, user_content)
            t_map = _parse_response(raw)
            if t_map:
                return t_map
            # Got a response but couldn't parse — retry
            if log_cb:
                log_cb(f"  {label}: response unparseable (attempt {attempt}), retrying...", "warn")
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503):
                # Add random jitter to prevent "thundering herd" concurrency stampede
                wait = (2 ** attempt * 2) + random.uniform(0.5, 2.5)
                if log_cb:
                    log_cb(f"  {label}: HTTP {exc.code} rate-limit, retry in {wait:.1f}s...", "warn")
                time.sleep(wait)
            else:
                if log_cb:
                    log_cb(f"  {label}: HTTP {exc.code}", "error")
                break
        except Exception as exc:
            if log_cb:
                log_cb(f"  {label}: {exc}", "error")
            time.sleep(3)

    return {}


# ---------------------------------------------------------------------------
# Worker: translate one chunk (Layer 1: Batch Validation)
# ---------------------------------------------------------------------------

def _translate_chunk(
    chunk_idx:        int,
    blocks:           List[SrtBlock],
    api_key:          str,
    model:            str,
    system_prompt:    str,
    batch_size:       int,
    source_patterns:  List[re.Pattern],
    target_lang:      str,
    progress_cb:      Optional[Callable],  # (chunk_idx, n_done)
    log_cb:           Optional[Callable],  # (msg, level)
) -> List[SrtBlock]:

    # Add a tiny staggered start delay to spread out requests over time
    if chunk_idx > 0:
        time.sleep(chunk_idx * 0.4)

    results: List[SrtBlock] = []
    total_batches = (len(blocks) + batch_size - 1) // batch_size

    for b_idx in range(total_batches):
        start = b_idx * batch_size
        batch = blocks[start : start + batch_size]

        user_content, local_map, block_to_local = _build_user_content(batch)

        # All skippable — copy as-is
        if not local_map:
            results.extend(batch)
            if progress_cb:
                progress_cb(chunk_idx, len(batch))
            continue

        label = f"Worker {chunk_idx+1} batch {b_idx+1}/{total_batches}"

        # ── LAYER 1: Call API with retry ──
        t_map = _call_with_retry(
            api_key, model, system_prompt, user_content,
            max_attempts=BATCH_RETRY_ATTEMPTS,
            label=label, log_cb=log_cb,
        )

        # ── LAYER 1b: Validate — check for missing or identical blocks ──
        missing_locals: List[int] = []
        for local_i, pos in local_map.items():
            translated = t_map.get(local_i)
            if translated is None:
                missing_locals.append(local_i)
            elif _is_untranslated(batch[pos].text, translated, source_patterns, target_lang):
                missing_locals.append(local_i)

        # If some blocks are missing/unchanged, retry just those
        if missing_locals and len(missing_locals) < len(local_map):
            if log_cb:
                log_cb(
                    f"  {label}: {len(missing_locals)}/{len(local_map)} blocks "
                    f"chưa dịch → retry ngay...", "warn"
                )
            # Build a mini-SRT-prompt with only the missing blocks
            retry_parts = []
            for li in missing_locals:
                pos = local_map[li]
                retry_parts.append(str(li))
                retry_parts.append(batch[pos].timestamp)
                retry_parts.append(batch[pos].text)
                retry_parts.append("")
            retry_inner = "\n".join(retry_parts).strip()
            retry_content = f"<INPUT>\n{retry_inner}\n</INPUT>"
            retry_map = _call_with_retry(
                api_key, model, system_prompt, retry_content,
                max_attempts=HEAL_RETRY_ATTEMPTS,
                label=f"{label} (retry)", log_cb=log_cb,
            )
            # Merge retry results into t_map
            for li, txt in retry_map.items():
                if not _is_untranslated(batch[local_map.get(li, 0)].text, txt, source_patterns, target_lang):
                    t_map[li] = txt

        elif missing_locals and len(missing_locals) == len(local_map):
            # Total failure — all blocks missing.
            # ⚡ Fix: retry immediately once (rate-limit cooldown) before deferring to self-heal.
            if log_cb:
                log_cb(f"  {label}: toàn bộ batch thất bại → đợi 5s rồi retry ngay...", "warn")
            time.sleep(5)
            retry_map = _call_with_retry(
                api_key, model, system_prompt, user_content,
                max_attempts=2,
                label=f"{label} (total-fail retry)", log_cb=log_cb,
            )
            if retry_map:
                for li, txt in retry_map.items():
                    pos = local_map.get(li)
                    if pos is not None and not _is_untranslated(
                        batch[pos].text, txt, source_patterns, target_lang
                    ):
                        t_map[li] = txt
                if log_cb:
                    log_cb(f"  {label}: retry ngay thành công {len(retry_map)} blocks", "ok")
            else:
                if log_cb:
                    log_cb(f"  {label}: retry ngay thất bại → sẽ xử lý ở vòng self-heal", "error")

        # ── Merge back into results ──
        for pos, blk in enumerate(batch):
            if pos in block_to_local:
                li = block_to_local[pos]
                new_text = t_map.get(li, blk.text)
            else:
                new_text = blk.text
            results.append(SrtBlock(blk.idx, blk.timestamp, new_text))

        if progress_cb:
            progress_cb(chunk_idx, len(batch))

    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def translate_file(
    blocks:        List[SrtBlock],
    api_keys:      List[str],
    model:         str,
    target_lang:   str,
    content_type:  str,
    batch_size:    int,
    glossary:      dict = None,
    progress_cb:   Optional[Callable] = None,
    log_cb:        Optional[Callable] = None,
) -> List[SrtBlock]:
    """
    Translate a list of SrtBlocks in parallel using multiple API keys.

    Three layers of protection:
      Layer 1: Batch Validation — immediate retry for missing/identical
      Layer 2: Content-Change Detection — flag unchanged text
      Layer 3: Multi-Pass Self-Healing — retry with rotating keys

    Returns sorted, translated blocks.
    """
    if not api_keys:
        raise ValueError("Cần ít nhất 1 API key.")

    n_workers = min(len(api_keys), 20, len(blocks))
    if n_workers == 0:
        return blocks

    # Detect source language script for untranslated detection
    source_patterns = _detect_source_scripts(blocks)
    if log_cb:
        detected_scripts = [
            name for name, pat in SCRIPT_DETECTORS.items() if pat in source_patterns
        ]
        if detected_scripts:
            log_cb(f"🔍 Phát hiện ngôn ngữ nguồn: {', '.join(detected_scripts)}", "info")

    # Divide blocks into equal chunks
    chunk_size = (len(blocks) + n_workers - 1) // n_workers
    chunks = [blocks[i : i + chunk_size] for i in range(0, len(blocks), chunk_size)]
    actual = len(chunks)

    system_prompt = _build_system_prompt(target_lang, content_type, glossary)

    if log_cb:
        log_cb(f"🚀 {actual} worker(s) song song | {len(blocks)} blocks | model: {model}", "info")

    results_map: dict = {}

    # ════════════════════════════════════════════════════════════════
    # MAIN PASS — parallel workers
    # ════════════════════════════════════════════════════════════════

    with ThreadPoolExecutor(max_workers=actual) as pool:
        futures = {
            pool.submit(
                _translate_chunk,
                i,
                chunks[i],
                api_keys[i % len(api_keys)],
                model,
                system_prompt,
                batch_size,
                source_patterns,
                target_lang,
                progress_cb,
                log_cb,
            ): i
            for i in range(actual)
        }
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                results_map[i] = fut.result()
                if log_cb:
                    log_cb(f"✅ Worker {i+1}/{actual} done ({len(results_map[i])} blocks)", "ok")
            except Exception as exc:
                if log_cb:
                    log_cb(f"❌ Worker {i+1} failed: {exc}", "error")
                results_map[i] = chunks[i]  # fallback original

    # Merge in order
    merged: List[SrtBlock] = []
    for i in range(actual):
        merged.extend(results_map.get(i, chunks[i]))
    merged.sort(key=lambda b: b.idx)

    # ════════════════════════════════════════════════════════════════
    # LAYER 3: Multi-Pass Self-Healing (with primary model)
    # ════════════════════════════════════════════════════════════════

    # Build a lookup of original source text for comparison
    source_text_map: Dict[int, str] = {b.idx: b.text for b in blocks}

    def _get_untranslated(block_list: List[SrtBlock]) -> List[SrtBlock]:
        """Return blocks that are still in source language."""
        result = []
        for b in block_list:
            src = source_text_map.get(b.idx, "")
            if not src or SKIP_RE.match(src):
                continue
            if _is_untranslated(src, b.text, source_patterns, target_lang):
                result.append(b)
        return result

    def _merge_healed(merged_list: List[SrtBlock], healed_list: List[SrtBlock]) -> Tuple[List[SrtBlock], int]:
        """Merge healed blocks into merged list. Returns (updated_list, n_improved)."""
        healed_map = {b.idx: b for b in healed_list}
        improved = 0
        for i, b in enumerate(merged_list):
            if b.idx in healed_map:
                healed_b = healed_map[b.idx]
                src = source_text_map.get(b.idx, "")
                if not _is_untranslated(src, healed_b.text, source_patterns, target_lang):
                    merged_list[i] = healed_b
                    improved += 1
        return merged_list, improved

    def _heal_parallel(blocks_to_heal: List[SrtBlock], current_model: str, current_prompt: str, current_batch_size: int, label_prefix: str) -> List[SrtBlock]:
        """Translate a batch of failed blocks in parallel using all available keys."""
        if not blocks_to_heal:
            return []
        
        # Determine active workers for self-heal
        heal_workers = min(len(api_keys), 20, len(blocks_to_heal))
        heal_chunk_size = (len(blocks_to_heal) + heal_workers - 1) // heal_workers
        heal_chunks = [blocks_to_heal[k : k + heal_chunk_size] for k in range(0, len(blocks_to_heal), heal_chunk_size)]
        actual_heal_workers = len(heal_chunks)
        
        healed_results_map: dict = {}
        with ThreadPoolExecutor(max_workers=actual_heal_workers) as pool:
            futures = {
                pool.submit(
                    _translate_chunk,
                    k,
                    heal_chunks[k],
                    api_keys[k % len(api_keys)],
                    current_model,
                    current_prompt,
                    current_batch_size,
                    source_patterns,
                    target_lang,
                    None,
                    log_cb,
                ): k
                for k in range(actual_heal_workers)
            }
            for fut in as_completed(futures):
                k = futures[fut]
                try:
                    healed_results_map[k] = fut.result()
                except Exception as exc:
                    if log_cb:
                        log_cb(f"   ❌ Self-heal Worker {k+1} failed: {exc}", "error")
                    healed_results_map[k] = heal_chunks[k]
                    
        healed_list = []
        for k in range(actual_heal_workers):
            healed_list.extend(healed_results_map.get(k, heal_chunks[k]))
        return healed_list

    # Self-heal with primary model first
    for heal_round in range(1, MAX_HEAL_ROUNDS + 1):
        untranslated = _get_untranslated(merged)
        if not untranslated:
            break

        if log_cb:
            log_cb(
                f"\n🔄 Self-Heal [{heal_round}/{MAX_HEAL_ROUNDS}] (model chính): "
                f"{len(untranslated)} blocks → dịch song song...", "warn"
            )

        healed = _heal_parallel(
            blocks_to_heal=untranslated,
            current_model=model,
            current_prompt=system_prompt,
            current_batch_size=min(HEAL_BATCH_SIZE, batch_size),
            label_prefix=f"Self-Heal {heal_round}"
        )

        merged, improved = _merge_healed(merged, healed)
        still_bad = len(untranslated) - improved
        if log_cb:
            log_cb(
                f"   ✅ Đã sửa {improved}, còn {still_bad} blocks",
                "ok" if still_bad == 0 else "warn",
            )
        if improved == 0:
            if log_cb:
                log_cb("   ↳ Không tiến triển với model chính, chuyển sang cascade...", "warn")
            break

    # ════════════════════════════════════════════════════════════════
    # LAYER 4: Fallback Model Cascade — MANDATORY translation
    # Try each fallback model until 0 untranslated blocks remain
    # ════════════════════════════════════════════════════════════════

    untranslated = _get_untranslated(merged)
    if untranslated:
        if log_cb:
            log_cb(
                f"\n⚡ FALLBACK CASCADE: {len(untranslated)} blocks vẫn chưa dịch "
                f"→ thử lần lượt {len(FALLBACK_MODELS)} model dự phòng...",
                "warn",
            )

        for fb_idx, fallback_model in enumerate(FALLBACK_MODELS):
            untranslated = _get_untranslated(merged)
            if not untranslated:
                break  # All done!

            if log_cb:
                log_cb(
                    f"\n🔀 Fallback [{fb_idx+1}/{len(FALLBACK_MODELS)}]: "
                    f"model={fallback_model} | {len(untranslated)} blocks",
                    "warn",
                )

            # Build fallback system prompt (same translation goal + glossary)
            fb_system_prompt = _build_system_prompt(target_lang, content_type, glossary)

            # Try multiple rounds with this fallback model
            for fb_round in range(1, MAX_HEAL_ROUNDS + 1):
                untranslated = _get_untranslated(merged)
                if not untranslated:
                    break

                if log_cb:
                    log_cb(
                        f"   ↳ Vòng {fb_round} (dịch song song): {len(untranslated)} blocks | {fallback_model}",
                        "dim",
                    )

                try:
                    healed = _heal_parallel(
                        blocks_to_heal=untranslated,
                        current_model=fallback_model,
                        current_prompt=fb_system_prompt,
                        current_batch_size=min(HEAL_BATCH_SIZE, batch_size),
                        label_prefix=f"Fallback {fb_idx+1} round {fb_round}"
                    )

                    merged, improved = _merge_healed(merged, healed)
                    still_bad = len(untranslated) - improved

                    if log_cb:
                        log_cb(
                            f"   ✅ {fallback_model}: sửa {improved} blocks, còn {still_bad}",
                            "ok" if still_bad == 0 else "warn",
                        )

                    if improved == 0:
                        if log_cb:
                            log_cb(f"   ↳ {fallback_model} không tiến triển → thử model tiếp theo", "warn")
                        break  # Move to next fallback model

                except Exception as exc:
                    if log_cb:
                        log_cb(f"   ❌ {fallback_model} lỗi: {exc} → thử model tiếp theo", "error")
                    break

    # ════════════════════════════════════════════════════════════════
    # Final report
    # ════════════════════════════════════════════════════════════════
    final_untranslated = len(_get_untranslated(merged))

    if log_cb:
        if final_untranslated > 0:
            log_cb(
                f"\n⚠️ Kết thúc: {len(merged)} blocks — "
                f"{final_untranslated} blocks không dịch được sau tất cả {len(FALLBACK_MODELS)+1} models",
                "error",
            )
        else:
            log_cb(
                f"\n🎉 Hoàn thành 100%: {len(merged)} blocks dịch xong — 0 lỗi!",
                "ok",
            )

    return merged
