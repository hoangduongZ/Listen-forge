"""Starter lessons and the default config file, written by `listenforge init`.

These double as the readable reference for the input format: a two-speaker interview, a
TOEIC-style three-speaker conversation, and a short everyday dialogue.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_CONFIG = """\
# ListenForge configuration.
# The lesson Markdown says WHAT to learn; this file says HOW to render the audio.

[paths]
input  = "./input"
output = "./output"

[pauses]
after_context = 2.0   # after the Vietnamese context
after_english = 2.5   # between the English passes
between_lines = 0.6   # between dialogue lines

[speed]
normal = "+0%"
slow   = "-30%"       # applied natively by the voice, not by time-stretching

[repeat]
normal_times = 2      # normal-speed passes before the slow pass

[voices]
vietnamese    = "vi-VN-HoaiMyNeural"
english       = ["en-US-GuyNeural", "en-US-AriaNeural"]
multi_speaker = true  # rotate voices across speakers, in first-appearance order

[tts]
provider    = "edge"
concurrency = 4
cache       = true

[audio]
bitrate     = "48k"
sample_rate = 24000
ffmpeg      = ""      # empty = look up on PATH
"""


LESSON_001 = """\
---
schema_version: "1.0"
id: "001"
title: "Java Backend Interview"
level: "B1"
topic: "career"
language: "en-US"
---

## Context

Bạn đang tham gia một buổi phỏng vấn cho vị trí Java Backend Developer.
Nhà tuyển dụng muốn tìm hiểu kinh nghiệm làm việc của bạn, trách nhiệm chính trong dự án
gần nhất, và cách bạn xử lý một vấn đề khó về hiệu năng.

## Listening

Interviewer: So, could you tell me a little bit about your experience with Java?

Candidate: Sure. I've been working with Java for about three years, mostly on backend
services. Most recently, I worked on a Spring Boot application for managing job
interviews.

Interviewer: What was your main responsibility on that project?

Candidate: I was mainly responsible for developing the REST APIs and working with the
database. I also helped review code from two junior developers.

Interviewer: What was the most difficult part of the project?

Candidate: The most difficult part was improving the performance of several database
queries. Some reports were taking almost thirty seconds to load.

Interviewer: And how did you solve that?

Candidate: I added the right indexes and rewrote a few queries to avoid loading data we
didn't need. After that, the reports finished in under two seconds.

## Vocabulary

- `experience` — kinh nghiệm
- `most recently` — gần đây nhất
- `be responsible for` — chịu trách nhiệm về
- `improve performance` — cải thiện hiệu năng
- `database query` — truy vấn cơ sở dữ liệu
- `review code` — rà soát mã nguồn

## Notes

Tập trung vào các cụm từ thường dùng khi mô tả trách nhiệm và kết quả công việc.
"""


LESSON_002 = """\
---
schema_version: "1.0"
id: "002"
title: "Office Renovation"
level: "B2"
topic: "business"
language: "en-US"
---

## Context

Đây là dạng bài TOEIC Part 3: một đoạn hội thoại ngắn giữa ba người trong công ty.
Họ đang bàn về việc sửa lại văn phòng: thời gian thi công, chỗ làm việc tạm cho nhân viên,
và chi phí phát sinh. Hãy chú ý các con số và mốc thời gian.

## Listening

Woman: Have you seen the schedule for the office renovation? They want to start on the
fifteenth.

Man: That's much earlier than I expected. Where is everyone supposed to sit while the
third floor is closed?

Woman: Facilities is setting up temporary desks in the training rooms. It should be about
four weeks in total.

Manager: Four weeks is optimistic. The contractor mentioned that the electrical work
alone could take two.

Man: If it runs long, we'll need to extend the desk rental, and that wasn't in the
original budget.

Manager: I'll raise it at the meeting on Thursday. Could you put together a rough
estimate before then?

Man: Sure. I'll send you the numbers by Wednesday afternoon.

## Vocabulary

- `renovation` — việc cải tạo, sửa chữa
- `facilities` — bộ phận cơ sở vật chất
- `temporary` — tạm thời
- `contractor` — nhà thầu
- `run long` — kéo dài hơn dự kiến
- `rough estimate` — bản dự toán sơ bộ
- `original budget` — ngân sách ban đầu

## Notes

Bài này có ba người nói, nên mỗi người sẽ được đọc bằng một giọng khác nhau.
"""


LESSON_003 = """\
---
schema_version: "1.0"
id: "003"
title: "Dinner Plans"
level: "A2"
topic: "daily life"
language: "en-US"
---

## Context

Hai người bạn cùng phòng đang nói chuyện vào buổi chiều muộn.
Một người vừa đi làm về và khá mệt, người kia đang nghĩ xem tối nay nên ăn gì.
Đây là hội thoại đời thường, tốc độ nói chậm và câu ngắn.

## Listening

Anna: Hey, you're home early today.

Ben: Yeah, the meeting finished sooner than I thought. I'm really hungry.

Anna: Me too. Do you want to cook, or should we order something?

Ben: Honestly, I'm too tired to cook. Let's order.

Anna: Okay. How about the noodle place near the station?

Ben: Sounds good. I had lunch there last week and it was really nice.

Anna: Great. I'll order in ten minutes. Do you want the usual?

Ben: Yes, please. And could you add some spring rolls this time?

## Vocabulary

- `sooner than I thought` — sớm hơn tôi tưởng
- `order something` — gọi đồ ăn
- `too tired to cook` — quá mệt để nấu ăn
- `how about` — hay là, còn nếu
- `the usual` — món quen, món thường gọi
"""


SAMPLES: dict[str, str] = {
    "001-java-backend-interview.md": LESSON_001,
    "002-toeic-part3-office-renovation.md": LESSON_002,
    "003-daily-conversation-dinner.md": LESSON_003,
}


def write_samples(input_dir: Path, *, force: bool = False) -> list[Path]:
    input_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in SAMPLES.items():
        target = input_dir / name
        if target.exists() and not force:
            continue
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written
