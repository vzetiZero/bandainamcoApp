"""CLI đổi tên tài khoản NAMCO Parks.

Logic thật (login, handoff Parks2, parse form, submit) nằm trong
app/infrastructure/bandai_name.py - file này chỉ lo tham số dòng lệnh và in tiến trình.
"""
import argparse
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.domain.names import kanji_overrides
from app.infrastructure.bandai_name import BandaiNameClient


def overrides_from_args(args):
    overrides = kanji_overrides(args.last_name, args.first_name)
    if args.last_kana:
        overrides["L_KANA"] = args.last_kana
    if args.first_kana:
        overrides["F_KANA"] = args.first_kana
    if args.nickname:
        overrides["NICKNAME"] = args.nickname
    return overrides


def main():
    parser = argparse.ArgumentParser(description="Đổi tên tài khoản NAMCO Parks")
    parser.add_argument("--email", required=True, help="Email đăng nhập")
    parser.add_argument("--password", required=True, help="Mật khẩu")
    parser.add_argument("--last-name", help="Họ mới (Kanji)")
    parser.add_argument("--first-name", help="Tên mới (Kanji)")
    parser.add_argument("--last-kana", help="Họ mới (Katakana)")
    parser.add_argument("--first-kana", help="Tên mới (Katakana)")
    parser.add_argument("--nickname", help="Biệt danh mới")

    args = parser.parse_args()
    overrides = overrides_from_args(args)
    if not overrides:
        parser.error("Không có trường nào để đổi - cần ít nhất một tuỳ chọn tên.")

    print("=" * 60)
    print("ĐỔI TÊN TÀI KHOẢN NAMCO PARKS")
    print("=" * 60)
    for field, value in overrides.items():
        print(f"  {field} -> {value}")

    # change_profile chạy trọn hai bước confirm/execute rồi đọc lại trang để xác minh;
    # gửi riêng bước một (submit) thì tên chưa đổi.
    outcome = BandaiNameClient().change_profile(
        args.email, args.password, overrides,
        on_progress=lambda percent: print(f"  ... {percent}%"))

    print("\n" + "=" * 60)
    print("✓ THÀNH CÔNG!" if outcome.success else "✗ THẤT BẠI!")
    print("=" * 60)
    print(outcome.message)
    return 0 if outcome.success else 1


if __name__ == "__main__":
    sys.exit(main())
