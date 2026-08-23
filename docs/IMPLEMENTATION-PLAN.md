# ListenForge — Kế hoạch triển khai

> Trạng thái: đã chốt, chưa bắt đầu code.
> Nguồn spec: [require-plan.md](require-plan.md) (CLI contract) + [lesson-format-prompt.md](lesson-format-prompt.md) (input contract).

---

## 1. Context

Thư mục project hiện chỉ có 2 file spec, chưa có code. Mục tiêu: build CLI tool `listenforge` biến file Markdown bài học tiếng Anh thành 1 file MP3 nghe được trên máy MP3 rẻ tiền / thẻ microSD.

Hai spec chia vai rõ ràng:

| File | Vai trò |
|---|---|
| `require-plan.md` | **CLI contract** — lệnh, cờ, quy tắc path, output. Không được thay đổi. |
| `lesson-format-prompt.md` | **Input contract** — format Markdown, validation. |

### Xung đột spec đã giải quyết

`require-plan.md` §6 mô tả format cũ `[CONTEXT_VI]` / `[ENGLISH]` / `[VOCABULARY]`.
`lesson-format-prompt.md` mô tả format `## Context` / `## Listening` / `## Vocabulary` + frontmatter bắt buộc có `schema_version`, `language` — và §11 **cấm** alias `## English`.

**Quyết định:** chỉ implement format `## Heading` (schema_version `"1.0"`). File dạng `[CONTEXT_VI]` sẽ báo lỗi rõ ràng kèm gợi ý.

Đây là **sai lệch duy nhất** so với `require-plan.md` §6 — mọi phần CLI / path / output của nó giữ nguyên 100%.

---

## 2. Quyết định kỹ thuật

| Hạng mục | Chọn | Lý do |
|---|---|---|
| Ngôn ngữ | Python ≥3.11, quản lý bằng `uv` | máy có `uv` 0.11.16; system python 3.9.6 quá cũ (không có `tomllib`), `uv` tự cài 3.12 |
| CLI | `typer` (kéo theo `rich`, `shellingham`) | auto-generate `--help` cho từng lệnh (§11), bảng cho `list` |
| TTS | `edge-tts` 7.2.8 | miễn phí, không API key, giọng `vi-VN-*` + nhiều `en-*`, có `rate="-30%"` **native** nên bản Slow nghe tự nhiên (không kéo chậm méo tiếng) |
| Audio | **ffmpeg** (yêu cầu cài hệ thống) | quyết định của user |
| Frontmatter | `pyyaml` | |
| ID3 tag | `mutagen` | ghi ID3v2.3/UTF-16 **+ ID3v1** — máy MP3 rẻ hay hiện mojibake với ID3v2.4/UTF-8 |
| Cache dir | `platformdirs` | |
| Test | `pytest` + `pytest-asyncio` + fake TTS provider | |

Dependency set đã verify resolve sạch bằng `uv pip compile`:
`typer 0.27.1` · `edge-tts 7.2.8` · `pyyaml 6.0.3` · `mutagen 1.48.1` · `platformdirs 4.11.3`

### ⚠️ Blocker môi trường

Máy chưa có `ffmpeg` / `ffprobe`. Bước đầu tiên phải chạy:

```bash
brew install ffmpeg
```

---

## 3. Kiến trúc audio

`edge-tts` **luôn** trả về đúng một format cố định: `audio-24khz-48kbitrate-mono-mp3` (24kHz, mono, 48kbps CBR).

Vì mọi mảnh audio đồng nhất tham số, đường đi tối ưu là **concat demuxer + `-c copy`**, hoàn toàn không re-encode:

```bash
ffmpeg -f concat -safe 0 -i list.txt -c copy -write_xing 1 -id3v2_version 3 out.tmp
```

An toàn vì MP3 không có container header toàn cục và tự phân định theo frame — chính `edge-tts` cũng đã nối byte các chunk >4096 bytes theo cách này trong `save()`.

### Không dùng `filter_complex` + `asplit` cho pipeline mặc định

Hai lỗi đã xác định trong cách tiếp cận đó:

1. `asplit` nạp vào `concat` filter gây **deadlock split→sequential-filter**. `concat` là tuần tự: nó phải drain segment *k* tới EOF trước khi đọc segment *k+1*, nên `asplit` buộc phải buffer toàn bộ stream → `Buffer queue overflow, dropping` → **audio bị cắt âm thầm** + RAM không giới hạn.
2. `anullsrc` là source **vô hạn**, không bao giờ tới EOF → phải chặn bằng `-t <duration>`.

Có cờ `--reencode` dự phòng dùng graph đã sửa (nhân bản input thay vì `asplit`, `aformat` từng nhánh, `-t` trên mọi `anullsrc`) cho trường hợp sau này thêm TTS provider khác sample rate.

### Ba tầng, mỗi tầng cache riêng theo content-hash

```
1. TTS từng dòng thoại              → mp3 segment trong cache
2. concat các dòng (+ pause câu)    → vi.mp3, en_normal.mp3, en_slow.mp3 trong cache
3. concat cuối (§8):
     vi → pause → en_normal → pause → en_normal → pause → en_slow
```

**`en_normal` chỉ synth 1 lần, dùng lại 2 lần** — tiết kiệm 1/3 số TTS call.

**Silence:** pre-render 1 lần cho mỗi độ dài vào cache (`anullsrc=r=24000:cl=mono` + `-t D` + `libmp3lame -b:a 48k`) để khớp tham số với TTS output, cho phép `-c copy`.

---

## 4. Cấu trúc project

```
listen-flow/
├── pyproject.toml            # hatchling, entry: listenforge = listenforge.cli:app
├── listenforge.toml          # config mặc định (pause, speed, voices)
├── input/  output/           # thư mục mặc định (§1)
├── src/listenforge/
│   ├── cli.py                # Typer app: generate, generate-all, list, doctor, init
│   ├── config.py             # TOML + env LISTENFORGE_* + defaults
│   ├── paths.py              # resolve_paths() §3/§14 + validate §13
│   ├── models.py             # Lesson, LessonMeta, Segment(speaker,text), VocabItem
│   ├── parser.py             # Markdown → Lesson (strict, §11)
│   ├── errors.py             # LessonError với file/id/section/problem (§14)
│   ├── pipeline.py           # Pipeline protocol + StubPipeline + RealPipeline
│   ├── cache.py              # cache key + manifest staleness
│   ├── tts/{base,edge,fake}.py
│   ├── audio/{engine,ffmpeg,silence,tags}.py
│   └── io/atomic.py          # atomic write cross-filesystem + writability probe
└── tests/
```

---

## 5. Config (`listenforge.toml`)

Theo `lesson-format-prompt.md` §16: tham số TTS **không** nằm trong file bài học.

```toml
[paths]
input  = "./input"
output = "./output"

[pauses]
after_context = 2.0
after_english = 2.5
between_lines = 0.6

[speed]
normal = "+0%"
slow   = "-30%"

[repeat]
normal_times = 2

[voices]
vietnamese    = "vi-VN-HoaiMyNeural"
english       = ["en-US-GuyNeural", "en-US-AriaNeural"]
multi_speaker = true

[tts]
provider    = "edge"
concurrency = 4
cache       = true

[audio]
bitrate     = "48k"
sample_rate = 24000
ffmpeg      = ""   # "" = tìm trong PATH
```

**Precedence:** cờ CLI → `--config` → `./listenforge.toml` → `~/.config/listenforge/config.toml` → default.

---

## 6. CLI surface

```
listenforge generate <FILE>  [--input P] [--output P] [--force] [--refresh-tts] [--dry-run] [--config P]
listenforge generate-all     [--input P] [--output P] [--force] [--refresh-tts] [--dry-run] [--jobs N]
listenforge list             [--input P] [--output P] [--json]
listenforge doctor           # kiểm tra ffmpeg + libmp3lame + ffprobe + kết nối edge-tts
listenforge init             # tạo input/ output/ listenforge.toml + bài mẫu
```

`resolve_paths()` dùng chung cho **mọi** lệnh (§14).

**Exit code:** `0` OK · `1` lỗi một phần khi batch · `2` lỗi path/validation.

### Giải nghĩa tham số `<FILE>` của `generate`

Spec không định nghĩa — chốt tường minh:

- đường dẫn tuyệt đối hoặc có dấu phân cách → dùng nguyên trạng, **bỏ qua** `--input`
- tên trần → ghép vào `INPUT`
- chấp nhận có/không hậu tố `.md`
- từ chối `..` traversal (`lesson-format-prompt.md` §2)

---

## 7. Các phase

Nhỏ, kiểm chứng độc lập, xếp theo thứ tự rủi ro giảm dần.

### P0 — Môi trường + scaffold

`brew install ffmpeg`. `pyproject.toml`, src layout, `uv sync`.

**Verify:** `uv run listenforge --help` in ra help; `ffmpeg -encoders | grep libmp3lame` có kết quả.

---

### P0.5 — Spike walking-skeleton *(bỏ đi sau khi xong)*

~40 dòng: synth 2 câu edge-tts → assemble `vi + pause + en + pause + en + pause + en_slow` → **nghe thử trên đúng máy MP3 mục tiêu**.

**Lý do:** đây là quyết định rủi ro nhất và khó đảo nhất (encoder / ID3 / máy có đọc được không). Parser + config + CLI là plumbing rủi ro thấp, không thể gây bất ngờ. Không để nó rơi vào P5 sau 4 phase đã cam kết.

**Verify:** file MP3 phát được trên thiết bị thật.

---

### P1 — Parser + models

`models.py`, `parser.py`, `errors.py`.

- Strict, không fuzzy-alias (§11)
- Frontmatter validate cả 6 field (§14.1–8)
- Section rỗng → invalid (§13)
- Vocabulary parse `` - `phrase` — nghĩa `` thành struct, báo lỗi kèm số dòng (§14.11)
- `## Notes` → `notes: str`
- Strip `**` / `_` trước khi tới TTS (§12)

**Speaker regex phải neo chặt.** Không dùng `^(\w+):` — nó khớp sai với narration kiểu `"There's one thing: the API is slow."` Quy tắc: nhãn ở đầu paragraph, `[A-Z][\w .'\-]{0,30}`, không chứa dấu kết câu, và yêu cầu ≥2 nhãn phân biệt trong section hoặc có marker hội thoại rõ. Không có nhãn → toàn bộ là narration (§6).

**Verify:** `pytest tests/test_parser.py` — 4 fixture hợp lệ (hội thoại, narration, không vocabulary, có Notes) + ~8 fixture lỗi.

---

### P2 — Config + path precedence

`config.py`, `paths.py`. `resolve_paths()` là một hàm thuần, testable.

**Verify:** test phủ cả 4 case §3, path tuyệt đối §12, và 3 thông điệp lỗi §13 khớp từng chữ.

---

### P3 — CLI đầy đủ + `list` (chưa cần TTS)

Dựng CLI **dựa trên `Pipeline` protocol** mà bản stub chỉ ghi ra MP3 giả cố định. Nhờ đó path precedence, `--force`, skip-existing, validation, exit code và **cả 4 lệnh trong §12** test được ngay ở đây — không cần mạng, không cần audio.

`list` in bảng `ID / TITLE / LEVEL / STATUS` (§10). Phát hiện trùng `id` trong batch (§14.12) và trùng tên file output.

**Verify:** chạy thật cả 4 lệnh §12 + `--output /Volumes/…`; `listenforge list` ra đúng bảng.

---

### P4a — TTS client

`tts/base.py` (Protocol), `tts/edge.py`, `tts/fake.py`. Một dòng → bytes.

Ba điểm phải phòng vệ với `edge-tts`:

1. Nó gọi endpoint Microsoft không chính thức, gửi token `Sec-MS-GEC` **dẫn xuất từ đồng hồ hệ thống** — máy lệch giờ sẽ 403 dai dẳng. Thông điệp lỗi phải nêu thẳng khả năng lệch đồng hồ.
2. Chặn concurrency ở 3–5 kết nối (cao hơn bị reset / 429).
3. Text rỗng/toàn khoảng trắng trả về **0 byte không kèm lỗi** — segment 0 byte sẽ làm hỏng concat, phải guard.

**Voice rotation theo thứ tự xuất hiện đầu tiên trong bài**, không hash tên speaker (hash gây trùng giọng — đúng thứ mà tính năng này sinh ra để tránh).

**Verify:** synth 1 câu thật ra mp3 nghe được; test parser↔TTS bằng `FakeTTS`.

---

### P4b — Cache

Cache key gồm: **text đã normalize + voice id + rate string + version `edge-tts` + tham số encoder**. Thiếu bất kỳ thành phần nào sẽ phát lại segment cũ khi đổi giọng.

`--force` **không** xoá cache TTS — §9 chỉ nói regenerate *output file*; gộp hai việc làm mỗi lần retry thành một lần tải lại toàn bộ. Dùng cờ riêng `--refresh-tts`.

**Verify:** chạy 2 lần, lần 2 không có network call; đổi giọng trong config → cache miss.

---

### P5 — Audio engine + `doctor`

- `audio/ffmpeg.py` — resolve binary (config → PATH), probe `libmp3lame`
- `audio/silence.py`
- `audio/engine.py` — 3 tầng concat
- `audio/tags.py` — `mutagen`, `save(v2_version=3, v1=2)`

`doctor` đặt ở đây, không ở P3 — ở P3 nó chưa có gì để báo.

**Verify:** so `ffprobe` duration của output với tổng kỳ vọng (sai số <100ms); nghe thử.

---

### P6 — Cross-filesystem / thẻ SD

Không phải việc "polish" — spec §12 và §15 nêu rõ.

- `os.replace` **thất bại** giữa 2 filesystem (`EXDEV` — docs Python ghi rõ). Fix: `tempfile.mkstemp(dir=dest.parent)` — temp phải **cạnh đích**, không ở cache dir.
  *(Cache TTS thì vẫn ở `platformdirs.user_cache_dir` — không muốn cache churn trên thẻ nhớ chậm. Hai thư mục cho hai mục đích, không gộp.)*
- `mkstemp` tạo file mode `0600` → mọi MP3 sinh ra chỉ owner đọc được. Phải `chmod`, bọc `suppress(OSError)` vì FAT/exFAT có thể `EPERM`.
- Probe writability **một lần trước** khi chạy pipeline — macOS mount NTFS read-only; hỏng sau 30s TTS cho 20 bài là vô nghĩa. Map lỗi về đúng thông điệp §13.
- Skip `.*` tường minh, **không** chỉ glob `*.md`: macOS ghi `._001-job-interview.md` và `.DS_Store` lên FAT/exFAT, `generate-all` sẽ parse chúng và fail.
- Sanitize tên file cho FAT (`: ? * " < > | \`) và phát hiện đụng tên do APFS/FAT không phân biệt hoa-thường (`001.md` vs `001.MD`).

**Verify:** `generate-all --output /Volumes/<SD>/English` (hoặc DMG FAT32 giả lập) thành công, file mode `644`.

---

### P7 — Manifest staleness *(tốt hơn spec)*

Lưu manifest `hash(nội dung bài) + hash(config) → output path` trong **cache dir** (không phải dotfile trên thẻ SD), key theo output path tuyệt đối.

Cho phép regenerate bài **đã sửa** mà không cần `--force` — điều mà kiểm tra file-exists thuần không làm được.

`list` hiện `GENERATED` / `NOT GENERATED` (đúng §10) và gắn thêm hậu tố `(stale)`.

**Verify:** sửa 1 file `.md` → `list` báo stale → `generate` tự chạy lại.

---

### P8 — Hoàn thiện

Deliverable cụ thể, không phải "cái thùng":

- Test xác định tính ổn định của assembly (so cấu trúc + duration qua `ffprobe`, **không** so byte hash vì output phụ thuộc version ffmpeg)
- Exit code
- Progress bar `rich`
- `--jobs`
- `--dry-run`
- `README.md`
- `init` + 4 bài mẫu
- Smoke test đóng gói: `uv tool install .` rồi chạy `listenforge --help` từ **ngoài** repo

---

## 8. Xác minh tổng thể

```bash
uv run pytest                                          # toàn bộ unit + e2e (FakeTTS)
uv run listenforge doctor                              # ffmpeg + libmp3lame + endpoint
uv run listenforge init && uv run listenforge list
uv run listenforge generate 001-job-interview.md       # → ./output/001-job-interview.mp3
uv run listenforge generate 001 --input ./lessons --output ./audio
uv run listenforge generate-all                        # lần 2 phải SKIP hết
uv run listenforge generate-all --force
uv run listenforge generate-all --input ./lessons --output /Volumes/SDCARD/English
uv run listenforge generate-all --input ./nope         # → exit 2, lỗi §13
```

Cuối cùng: copy 1 file ra máy MP3 thật, xác nhận phát được và ID3 hiện tiếng Việt đúng.
