"""Định nghĩa cột của bảng danh sách tài khoản."""


# Cột của bảng tài khoản: (nhãn header, key trong dict account)
ACCOUNT_COLUMNS = [
    ("Email", "email"), ("Password", "__password__"),
    ("Status", "status"), ("Last check", "last_check"),
    ("Last name (Kanji)", "last_name_kanji"), ("First name (Kanji)", "first_name_kanji"),
    ("Last name (Kana)", "last_name_kana"), ("First name (Kana)", "first_name_kana"),
    ("Nickname", "nickname"), ("Gender", "gender"),
    ("Postal code", "postal_code"), ("Prefecture", "prefecture"), ("City", "city"),
    ("Address", "address_number"), ("Building", "building"), ("Phone", "phone"),
    ("Points", "current_points"), ("Bandai Namco ID", "bandai_namco_id_status"),
    ("Points terms", "points_terms_status"), ("Profile access", "profile_fetch_status"),
    ("Gender code", "gender_code"),
]
