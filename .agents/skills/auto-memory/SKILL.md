---
name: auto-memory
description: Quản lý vòng đời ký ức và biên bản bàn giao (Handover / Session Memory) tự động cho Antigravity IDE, tránh mất dấu giữa các session.
---

# AUTO-MEMORY PROTOCOL CHO ANTIGRAVITY

## 1. Khi bắt đầu Session mới (Session Start - 3 tool calls đầu):
1. Đọc ngay file bàn giao gần nhất: `HANDOVER.md` và `Agent-Memory/session-*.md` mới nhất.
2. Kiểm tra các thay đổi gần nhất bằng `git status -s` hoặc `git log -n 3`.
3. Thông báo cho người dùng: `🧠 Đã tải ký ức các phiên trước của dự án`.

## 2. Khi kết thúc Session (Session End):
1. Cập nhật `HANDOVER.md` và tạo file `HANDOVER-YYYY-MM-DD-*.md`.
2. Tạo/cập nhật `Agent-Memory/session-YYYY-MM-DD-antigravity-{project}.md`.
3. Thông báo: `💾 Ký ức phiên làm việc đã được lưu vĩnh viễn vào dự án`.
