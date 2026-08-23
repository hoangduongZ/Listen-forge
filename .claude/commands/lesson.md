---
description: Tạo một bài nghe ListenForge mới từ mô tả cuộc hội thoại, rồi build MP3
argument-hint: [mô tả cuộc hội thoại mong muốn]
allowed-tools: Read, Write, Glob, Bash(uv run listenforge:*), Bash(ls:*)
---

Người dùng muốn một bài nghe mới. Yêu cầu của họ:

<yeu_cau>
$ARGUMENTS
</yeu_cau>

Tạo một file lesson hợp lệ trong `input/`, rồi build ra MP3.

## Bước 1 — Đọc yêu cầu

Rút ra từ `<yeu_cau>`: chủ đề, bối cảnh, số người nói, trình độ, độ dài, kiểu bài
(TOEIC / IELTS / hội thoại đời thường / độc thoại kỹ thuật).

Thiếu gì thì tự chọn mặc định hợp lý, **không hỏi lại**:

| Thiếu | Mặc định |
|---|---|
| trình độ | `B1` |
| độ dài | hội thoại 7–9 lượt, hoặc độc thoại 120–160 từ |
| số người nói | 2 |
| `language` | `en-US` |

Nếu yêu cầu nhắc tới IELTS thì đặt `language: "en-GB"`; TOEIC thì `en-US`.

## Bước 2 — Chọn id và tên file

Liệt kê `input/` để tìm id lớn nhất, dùng số kế tiếp, giữ 3 chữ số (`004`, `005`...).
Tên file: `NNN-slug-tieng-anh.md`, slug kebab-case không dấu.

## Bước 3 — Viết file

Format là hợp đồng nghiêm ngặt — parser không đoán. Bản đầy đủ ở
`docs/INPUT_FORMAT.md`; đọc file đó nếu gặp trường hợp lạ. Các ràng buộc bắt buộc:

```markdown
---
schema_version: "1.0"
id: "004"
title: "Tiêu đề tiếng Anh ngắn"
level: "B1"
topic: "free text"
language: "en-US"
---

## Context

## Listening

## Vocabulary

## Notes
```

- Sáu trường front matter đều bắt buộc, không được rỗng. `schema_version` luôn là `"1.0"`.
- `level` thuộc `A1 A2 B1 B2 C1 C2`.
- Heading phải đúng chính tả: `## Context`, `## Listening`, `## Vocabulary`, `## Notes`.
  `## English`, `## Situation`, `## Words` đều là lỗi, không phải từ đồng nghĩa.
- `## Context` và `## Listening` bắt buộc; có mà rỗng cũng là lỗi.
- **KHÔNG** đặt voice, speed, pause hay repeat vào front matter. Đó là việc của
  `config/listenforge.toml`.

**`## Context`** — tiếng Việt, 2–4 câu. Dựng bối cảnh: ai đang nói, ở đâu, vì sao.
Không dịch từng câu của phần Listening, không tiết lộ nội dung chi tiết — người học phải
tự nghe ra.

**`## Listening`** — chỉ tiếng Anh, viết như người bản xứ nói thật. Viết sao đọc vậy,
không có ai sửa ngữ pháp hay đơn giản hoá sau đó.

Hội thoại dùng `Speaker: text`, mỗi lượt một đoạn, cách nhau một dòng trống:

```markdown
Woman: Have you seen the schedule for the renovation?

Man: That's earlier than I expected.
```

Nhãn không được đọc lên, nó chỉ để chọn giọng, gán theo thứ tự xuất hiện đầu tiên.
Parser chỉ nhận nhãn khi bằng chứng đủ mạnh: **từ hai nhãn khác nhau trở lên**, hoặc mọi
đoạn đều có nhãn. Hội thoại một người nói sẽ không được nhận là hội thoại — nếu chỉ có
một người, viết dạng độc thoại không nhãn.

Cẩn thận câu có dấu hai chấm ở đầu, ví dụ `There was one thing we missed: the index.` —
viết lại để tránh bị hiểu nhầm thành tên người nói.

**`## Vocabulary`** — 5–8 mục, từ khó trong bài. Bullet, cụm tiếng Anh trước, nghĩa tiếng
Việt sau, ngăn bằng **em dash `—`**, không phải gạch nối `-`:

```markdown
- `contractor` — nhà thầu
- `run long` — kéo dài hơn dự kiến
```

Phần này không vào MP3.

**`## Notes`** — tiếng Việt, một dòng ghi chú. Không vào MP3.

Tránh `**bold**` và `_italic_` trong prose; parser strip được nhưng plain text vẫn hơn.

## Bước 4 — Kiểm tra rồi build

```bash
uv run listenforge generate NNN --dry-run   # parser phải pass
uv run listenforge generate NNN             # gọi TTS thật, tốn mạng
```

`--dry-run` fail thì sửa file rồi chạy lại, đừng build tiếp.

## Bước 5 — Báo cáo

Nói ngắn gọn: đường dẫn file lesson, đường dẫn MP3, thời lượng
(`ffprobe -v error -show_entries format=duration -of csv=p=0 FILE`), số người nói và
giọng được gán. Nhắc rằng bài sẽ được đọc 2 lượt tốc độ thường + 1 lượt chậm, theo
`[repeat]` trong config.
