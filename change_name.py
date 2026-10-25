"""CLI đổi tên tài khoản NAMCO Parks.

Logic thật (login, handoff Parks2, parse form, submit) nằm trong
app/infrastructure/bandai_name.py - file này chỉ lo tham số dòng lệnh và in tiến trình.
"""
import argparse
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.domain.names import NAME_FIELDS, kanji_overrides
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

    client = BandaiNameClient()
    print("\n[1/3] Đăng nhập và mở trang sửa hồ sơ...")
    session, headers, form, message = client.open_edit_page(
        args.email, args.password, on_progress=lambda percent: print(f"    ... {percent}%"))
    if form is None:
        print(f"\n✗ THẤT BẠI: {message}")
        return 1
    print("    ✓ Đăng nhập + handoff Parks2 thành công")

    print("\n[2/3] Giá trị hiện tại:")
    for field in NAME_FIELDS:
        print(f"    {field}: {form.current(field)}")

    print("\n[3/3] Gửi form...")
    outcome = client.submit(session, headers, form, overrides)
    for field, value in overrides.items():
        print(f"    {field} -> {value}")

    print("\n" + "=" * 60)
    print("✓ THÀNH CÔNG!" if outcome.success else "✗ THẤT BẠI!")
    print("=" * 60)
    print(outcome.message)
    return 0 if outcome.success else 1


if __name__ == "__main__":
    sys.exit(main())
