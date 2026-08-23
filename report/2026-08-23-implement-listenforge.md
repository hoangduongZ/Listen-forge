```bash
which brew && brew --version
```
Xem máy có Homebrew để cài ffmpeg.

```bash
brew install ffmpeg
```
Cài ffmpeg — công cụ ghép và nén file MP3. Đây là lệnh duy nhất cài thêm vào máy.

```bash
which ffmpeg ffprobe; ffmpeg -encoders | grep -c libmp3lame
```
Xác nhận ffmpeg cài xong và có bộ mã hoá MP3.

```bash
find . -not -path '*/.git/*' -not -path './.venv/*' | sort
ls -la input output docs
```
Xem lại cây thư mục sau khi bạn đổi cấu trúc, để khớp code theo.

```bash
printf '' > src/listenforge/{audio,io,tts}/__init__.py
printf '' > tests/__init__.py
mkdir -p config tests/fixtures
```
Tạo các file/thư mục rỗng mà Python cần để nhận diện package.

```bash
uv sync
```
Cài thư viện của project vào môi trường ảo riêng, không ảnh hưởng Python hệ thống.

```bash
uv run listenforge --help
uv run listenforge init
uv run listenforge list
uv run listenforge doctor
```
Chạy thử CLI: xem trợ giúp, tạo 3 bài mẫu + config, liệt kê bài, kiểm tra ffmpeg và kết nối giọng đọc.

```bash
uv run listenforge generate 003-daily-conversation-dinner.md
uv run listenforge generate 003
uv run listenforge generate-all
uv run listenforge generate-all --force
uv run listenforge generate-all --dry-run
```
Sinh file MP3 thật để kiểm tra đúng yêu cầu, gồm cả chạy lại để xác nhận có bỏ qua file đã có.

```bash
ffprobe -v error -show_entries format=duration,bit_rate:stream=... output/*.mp3
```
Đọc thông tin file MP3 vừa tạo (thời lượng, chất lượng, thẻ tên bài) để đối chiếu.

```bash
uv run listenforge generate-all --input ./nope
uv run listenforge generate 999.md
```
Thử các trường hợp sai đường dẫn để chắc chắn tool báo lỗi rõ ràng.

```bash
hdiutil create -size 40m -fs "MS-DOS FAT32" -volname LFSD -o /tmp/lfsd.dmg
hdiutil attach /tmp/lfsd.dmg
touch input/._999-applefile.md input/.DS_Store
uv run listenforge generate-all --output /Volumes/LFSD/English
```
Tạo một thẻ nhớ giả để thử ghi MP3 ra ổ khác — đây là tình huống dễ lỗi nhất.
Hai file `._` và `.DS_Store` là file rác macOS, tạo ra để chắc chắn tool bỏ qua chúng.

```bash
uv run listenforge generate-all --output /tmp/lf-sdtest
```
Thử ghi ra một thư mục ngoài project.

```bash
uv run pytest -q
```
Chạy toàn bộ 69 bài kiểm thử tự động. Không cần mạng.

```bash
uv build
uv venv <tạm>/v && uv pip install <tạm> dist/listenforge-0.1.0-py3-none-any.whl
<tạm>/v/bin/listenforge --help
```
Đóng gói rồi cài thử vào môi trường sạch, chạy từ ngoài project để chắc chắn cài được thật.

```bash
hdiutil detach /Volumes/LFSD
rm -f /tmp/lfsd.dmg
rm -rf /tmp/lf-sdtest
```
Tháo thẻ nhớ giả và xoá file tạm.

```bash
rm input/003-daily-conversation-dinner.md && uv run listenforge init
```
Bài 003 bị tôi làm sai định dạng khi thử nghiệm, nên xoá và tạo lại từ mẫu.

---

Thay đổi duy nhất lên máy bạn: **cài `ffmpeg` qua Homebrew**.
Mọi thứ khác chỉ nằm trong project hoặc thư mục tạm, và đã được xoá.
